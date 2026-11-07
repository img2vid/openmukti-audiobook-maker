"""Optional OpenCL operations. Each thread owns its buffers, kernels and command queue."""
import os
import threading
import wave

from .acceleration import gpu_enabled

_local=threading.local()
SOURCE="""
__kernel void over(__global const uchar4 *bg, __global const uchar4 *fg, __global uchar4 *out) {
    int i=get_global_id(0);
    uint4 b=convert_uint4(bg[i]), f=convert_uint4(fg[i]);
    uint inv=255-f.w, denom=f.w*255+b.w*inv;
    if (f.w==0) {out[i]=bg[i];return;}
    if (denom==0) {out[i]=(uchar4)(0);return;}
    uint4 rgb=(f*f.w*255+b*b.w*inv+denom/2)/denom;
    rgb.w=(denom+127)/255;
    out[i]=convert_uchar4_sat(rgb);
}
__kernel void pcm(__global const short *s, __global short *dst, const int nc,
                  const float gl, const float gr, const float fade_start,
                  const float fade_step, const float phase) {
    int i=get_global_id(0);
    float level=nc==2 && (i&1) ? gr : gl;
    float fade=clamp(fade_start+((float)(i/nc)+phase)*fade_step,0.0f,1.0f);
    dst[i]=convert_short_sat_rte((float)s[i]*level*fade);
}
"""


def context():
    if not gpu_enabled():
        return None
    if hasattr(_local,'backend'):
        return _local.backend
    _local.backend=None
    try:
        import pyopencl as cl
    except (ImportError,OSError):
        return None
    try:
        platforms=cl.get_platforms()
    except cl.Error:
        return None
    for platform in platforms:
        try:
            devices=platform.get_devices(device_type=cl.device_type.GPU)
        except cl.Error:
            continue
        for device in devices:
            try:
                ctx=cl.Context([device])
                queue=cl.CommandQueue(ctx)
                program=cl.Program(ctx,SOURCE).build()
                _local.backend=(cl,queue,program,device.name.strip())
                return _local.backend
            except cl.Error:
                continue
    return None


def calculate(name,inputs,result,scalars,count):
    backend=context()
    if not backend:
        return False
    cl,queue,program,_=backend
    try:
        buffers=[cl.Buffer(queue.context,cl.mem_flags.READ_ONLY|cl.mem_flags.COPY_HOST_PTR,hostbuf=arr) for arr in inputs]
        dest=cl.Buffer(queue.context,cl.mem_flags.WRITE_ONLY,result.nbytes)
        kernel=cl.Kernel(program,name)
        kernel.set_args(*buffers,dest,*scalars)
        cl.enqueue_nd_range_kernel(queue,kernel,(count,),None)
        cl.enqueue_copy(queue,result,dest).wait()
        return True
    except (cl.Error,MemoryError,RuntimeError):
        _local.backend=None
        return False


def composite(base,layer,position=(0,0)):
    """Overlay a straight-alpha layer in place, including partially off-canvas layers."""
    x,y=position
    if layer.width*layer.height<65536 or not gpu_enabled():
        base.alpha_composite(layer,position)
        return
    from PIL import Image
    rect=(max(0,x),max(0,y),min(base.width,x+layer.width),min(base.height,y+layer.height))
    l,t,r,b=rect
    if r<=l or b<=t:
        return
    if not context():
        from .legacy_gl import accelerated_blend,may_work
        if not may_work():
            base.alpha_composite(layer,position)
            return
        result=accelerated_blend(r-l,b-t,base.crop(rect).tobytes(),layer.crop((l-x,t-y,r-x,b-y)).tobytes())
        if result is not None:
            base.paste(Image.frombytes('RGBA',(r-l,b-t),result),rect)
        else:
            base.alpha_composite(layer,position)
        return
    import numpy as np
    bg=np.array(base.crop(rect),dtype=np.uint8)
    fg=np.array(layer.crop((l-x,t-y,r-x,b-y)),dtype=np.uint8)
    dest=np.empty_like(bg)
    if calculate('over',[bg,fg],dest,[],(r-l)*(b-t)):
        base.paste(Image.fromarray(dest),rect)
    else:
        base.alpha_composite(layer,position)


def pcm_effect(source,destination,*,operation,gain,pan,fade_seconds,duration,control=None,status=None):
    """Accelerate like-for-like 16-bit PCM processing; leave other formats to FFmpeg."""
    if operation not in ('gain','pan','fade-in','fade-out') or not context():
        return False
    import numpy as np
    from .progress import emit
    try:
        audio=wave.open(str(source),'rb')
    except (wave.Error,EOFError):
        return False
    with audio:
        channels=audio.getnchannels()
        sr=audio.getframerate()
        if audio.getsampwidth()!=2 or channels not in (1,2) or audio.getcomptype()!='NONE' or (operation=='pan' and channels!=2):
            return False
        if operation=='fade-out' and duration<=0:
            return False
        if operation.startswith('fade') and fade_seconds<=0:
            return False
        gl=gr=10**(gain/20) if operation=='gain' else 1
        if operation=='pan':
            gl,gr=min(1,1-pan),min(1,1+pan)
        step=1/(fade_seconds*sr) if operation.startswith('fade') else 0
        if operation=='fade-out':
            step=-step
        origin=0 if operation=='fade-in' else (max(duration,fade_seconds)/fade_seconds if operation=='fade-out' else 1)
        done=0
        with wave.open(str(destination),'wb') as out:
            out.setparams(audio.getparams())
            while raw:=audio.readframes(65536):
                if control:
                    control.check()
                src=np.frombuffer(raw,dtype='<i2').astype(np.int16,copy=False)
                result=np.empty_like(src)
                args=[np.int32(channels),np.float32(gl),np.float32(gr),np.float32(origin+done*step),np.float32(step),np.float32(0)]
                if not calculate('pcm',[src],result,args,len(src)):
                    return False
                out.writeframesraw(result.astype('<i2',copy=False).tobytes())
                done+=len(src)//channels
                emit(status,done/max(1,audio.getnframes()),'Applying '+operation+' with OpenCL')
    return True
