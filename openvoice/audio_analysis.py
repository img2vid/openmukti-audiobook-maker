"""Bounded-memory waveform, click and dropout analysis with optional OpenCL 1.x."""
from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from .acceleration import gpu_enabled
from .fftools import find_binary
from .video import audio_duration

KERNEL = """
__kernel void levels(__global const float *x, __global float4 *y, const int n,
                     const float previous, const float next) {
    int i = get_global_id(0);
    if (i >= n) return;
    float a = i ? x[i-1] : previous;
    float b = i+1 < n ? x[i+1] : next;
    float click = fabs(x[i]-(a+b)*0.5f) > 0.45f && fabs(a-b)<0.12f;
    y[i] = (float4)(fabs(x[i]), x[i]*x[i], click, fabs(x[i])>=0.999f);
}
"""


class LevelAnalyzer:
    def __init__(self):
        self.device='CPU'
        self.queue=None
        from .compute import context
        backend=context()
        if backend:
            cl,queue,_,device=backend
            try:
                self.kernel=cl.Kernel(cl.Program(queue.context,KERNEL).build(),'levels')
                self.cl,self.queue,self.device=cl,queue,device
            except cl.Error:
                pass

    def levels(self, x, before, after):
        import numpy as np
        if self.queue is not None:
            cl=self.cl
            try:
                inp=cl.Buffer(self.queue.context,cl.mem_flags.READ_ONLY|cl.mem_flags.COPY_HOST_PTR,hostbuf=x)
                result=np.empty((len(x),4),dtype=np.float32)
                out=cl.Buffer(self.queue.context,cl.mem_flags.WRITE_ONLY,result.nbytes)
                self.kernel.set_args(inp,out,np.int32(len(x)),np.float32(before),np.float32(after))
                cl.enqueue_nd_range_kernel(self.queue,self.kernel,(len(x),),None)
                cl.enqueue_copy(self.queue,result,out).wait()
                return result.T
            except (cl.Error, MemoryError, RuntimeError):
                self.queue=None
                self.device='CPU'
        a=np.empty_like(x)
        b=np.empty_like(x)
        a[0],a[1:],b[-1],b[:-1]=before,x[:-1],after,x[1:]
        magnitude=np.abs(x)
        return magnitude,x*x,(np.abs(x-(a+b)*.5)>.45)&(np.abs(a-b)<.12),magnitude>=.999


def waveform(source,bins=800):
    """Each point contains start time, RMS and peak as fractions of full scale."""
    import numpy as np
    source=Path(source).resolve(strict=True)
    if not 8<=bins<=16384:
        raise ValueError('Waveform resolution must be 8–16384 bins')
    rate=24000
    duration=audio_duration(source)
    period=max(1,math.ceil(duration*rate/bins))
    analyzer=LevelAnalyzer()
    points,clicks,dropouts=[],[],[]
    clip_count=total=0
    low=None
    previous_tile=None
    repeat_count=0
    tiles_done=0
    buffer_tail=np.empty(0,dtype=np.float32)
    repetitions=[]
    energy=peak=n_bin=0
    chunk=32768*4
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen([find_binary('ffmpeg'),'-nostdin','-loglevel','error','-i',str(source),
                               '-vn','-ac','1','-ar',str(rate),'-f','f32le','pipe:1'],
                              stdout=subprocess.PIPE,stderr=errors) as proc:
            try:
                block=proc.stdout.read(chunk)
                before=None
                while block:
                    nextblock=proc.stdout.read(chunk)
                    x=np.frombuffer(block,dtype='<f4')
                    after=np.frombuffer(nextblock[:4],dtype='<f4')[0] if nextblock else x[-1]
                    magn,squares,spikes,clipped=analyzer.levels(x,x[0] if before is None else before,after)
                    before=x[-1]
                    combined=np.concatenate((buffer_tail,x))
                    tile_size=rate//10
                    limit=len(combined)//tile_size*tile_size
                    for tile in combined[:limit].reshape(-1,tile_size):
                        repeated=(previous_tile is not None and float(np.max(np.abs(tile)))>.04
                                  and float(np.max(np.abs(tile-previous_tile)))<.001)
                        if repeated:
                            repeat_count+=1
                        elif repeat_count>=2:
                            repetitions.append([(tiles_done-repeat_count-1)/10,tiles_done/10])
                            repeat_count=0
                        else:
                            repeat_count=0
                        previous_tile=tile.copy()
                        tiles_done+=1
                    buffer_tail=combined[limit:].copy()
                    clip_count+=int(np.count_nonzero(clipped))
                    if len(clicks)<2000:
                        clicks.extend((total+int(i))/rate for i in np.flatnonzero(spikes)[:2000-len(clicks)])
                    cursor=0
                    while cursor<len(x):
                        end=min(len(x),cursor+period-n_bin)
                        length=end-cursor
                        energy+=float(np.sum(squares[cursor:end],dtype=np.float64))
                        peak=max(peak,float(np.max(magn[cursor:end])))
                        n_bin+=length
                        if n_bin==period:
                            stamp=(total+end-n_bin)/rate
                            points.append([round(stamp,5),math.sqrt(energy/n_bin),peak])
                            if peak<.0001 and low is None:
                                low=stamp
                            elif peak>=.0001 and low is not None:
                                if stamp-low>=.15:
                                    dropouts.append([round(low,4),round(stamp,4)])
                                low=None
                            energy=peak=n_bin=0
                        cursor=end
                    total+=len(x)
                    block=nextblock
                if proc.wait():
                    errors.seek(0)
                    raise RuntimeError('Cannot decode audio: '+errors.read(2048).decode(errors='replace'))
            finally:
                if proc.poll() is None:
                    proc.kill()
    if n_bin:
        points.append([round((total-n_bin)/rate,5),math.sqrt(energy/n_bin),peak])
    if low is not None and total/rate-low>=.15:
        dropouts.append([round(low,4),round(total/rate,4)])
    if repeat_count>=2:
        repetitions.append([(tiles_done-repeat_count-1)/10,tiles_done/10])
    return {'repeating_audio_candidates':repetitions,'seconds':total/rate,'analysis_rate':rate,'analysis_device':analyzer.device,
            'points':points,'possible_clicks':clicks,'near_silent_regions':dropouts,
            'clipped_samples':clip_count}
