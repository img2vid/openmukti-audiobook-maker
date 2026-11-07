"""Sample editable pitch, pace and intensity envelopes over a spoken passage."""
from pathlib import Path
from .performance import interpolate
from .sound_studio import number
from .fftools import find_binary
from .video import _run,audio_duration


def shape_recording(source,out,curves,control=None):
    if not isinstance(curves,dict) or set(curves)-{'semitones','pace','gain_db'}:
        raise ValueError('Unsupported prosody curve')
    seconds=audio_duration(source)
    import math
    count=max(2,min(48,math.ceil(seconds*5)))
    branches=[]
    labels=[]
    for i in range(count):
        a=seconds*i/count
        b=seconds*(i+1)/count
        t=(i+.5)/count
        pitch=2**(number(interpolate(curves.get('semitones'),t,0),-12,12,'curve pitch')/12)
        rate=number(interpolate(curves.get('pace'),t,1),.5,2,'curve pace')/pitch
        gain=number(interpolate(curves.get('gain_db'),t,0),-60,16,'curve gain')
        tempo=[]
        while rate<.5:
            tempo.append('atempo=0.5')
            rate*=2
        tempo.append(f'atempo={rate}')
        filters=[f'atrim=start={a}:end={b}','asetpts=PTS-STARTPTS','aresample=24000',f'asetrate={round(24000*pitch)}',
                 'aresample=24000',*tempo,f'volume={gain}dB']
        branches.append(f'[p{i}]'+','.join(filters)+f'[b{i}]')
        labels.append(f'[b{i}]')
    graph='[0:a]asplit='+str(count)+''.join(f'[p{i}]' for i in range(count))+';'+';'.join(branches)+';'+''.join(labels)+f'concat=n={count}:v=0:a=1[out]'
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        script=Path(temp)/'curves.ffscript'
        script.write_text(graph,encoding='ascii')
        _run([find_binary('ffmpeg'),'-nostdin','-loglevel','error','-y','-i',str(source),'-filter_complex_script',str(script),'-map','[out]','-c:a','pcm_s16le',str(out)],control)
