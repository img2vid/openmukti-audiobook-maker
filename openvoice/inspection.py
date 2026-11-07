"""Local diagnostics, measured benchmarks and redacted support archives."""
import hashlib
import json
import os
import platform
import re
import tempfile
import time
import zipfile
from pathlib import Path

from . import __version__
from .security_tools import staged_file


def benchmark(engine='flite',voice='',model='',text='The first chapter begins on a quiet morning.',repeat=2):
    from .engines import get_engine, SpeechSettings
    from .service import render_text
    from .video import audio_duration
    from .audio_analysis import waveform
    if not 1<=repeat<=20 or not text.strip():
        raise ValueError('Provide a sample passage and 1–20 runs')
    backend=get_engine(engine,model,voice)
    settings=SpeechSettings(voice=voice,model=model)
    results=[]
    try:
        import psutil
        process=psutil.Process()
    except ImportError:
        process=None
    with tempfile.TemporaryDirectory() as work:
        for n in range(repeat):
            path=Path(work)/'sample.wav'
            start=time.perf_counter()
            from .service import prepared_speech_units, render_speech_unit, JobOptions
            from .audio import combine_wav
            parts=[]
            rss=[]
            import threading
            stop=threading.Event()
            def measure():
                while not stop.is_set():
                    try:
                        total=process.memory_info().rss
                        for child in process.children(recursive=True):
                            try:
                                total+=child.memory_info().rss
                            except psutil.Error:
                                pass
                        rss.append(total)
                    except psutil.Error:
                        pass
                    stop.wait(.05)
            monitor=threading.Thread(target=measure,daemon=True) if process else None
            if monitor:
                monitor.start()
            try:
                for i,unit in enumerate(prepared_speech_units(text,JobOptions())):
                    part=Path(work)/f'{i}.wav'
                    render_speech_unit(unit,part,backend,settings)
                    parts.append(part)
                combine_wav(parts,path)
            finally:
                stop.set()
                if monitor:
                    monitor.join()
            elapsed=time.perf_counter()-start
            seconds=audio_duration(path)
            signal=waveform(path,32)
            results.append({'wall_seconds':elapsed,'speech_seconds':seconds,'real_time_factor':elapsed/seconds,
                            'peak_sampled_process_tree_bytes':max(rss,default=None),'clipped_samples':signal['clipped_samples'],
                            'peak':max((point[2] for point in signal['points']),default=0)})
    return {'engine':backend.key,'voice':voice,'model':model,'platform':platform.system(),
            'architecture':platform.machine(),'logical_cpus':os.cpu_count(),'runs':results}


def support_bundle(output, logs=()):
    from .hardware import hardware_status
    from .fftools import media_tools_status
    target=Path(output)
    with staged_file(target) as tmp, zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        system={'version':__version__,'system':platform.system(),'architecture':platform.machine(),
                'python':platform.python_version(),'hardware':hardware_status(),
                'media':{k:{'available':v['available'],'version':v['version']} for k,v in media_tools_status().items()}}
        z.writestr('diagnostics.json',json.dumps(system,indent=2))
        for i,log in enumerate(logs,1):
            # Only retain diagnostic severity, event code and timing. Free text may contain manuscript passages.
            selected=[]
            with Path(log).open(encoding='utf-8',errors='replace') as f:
                for n,line in enumerate(f):
                    if n>=50000:
                        break
                    try:
                        row=json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(row,dict):
                        level=row.get('level','')
                        stamp=str(row.get('at',''))
                        if level in ('debug','info','warning','error'):
                            selected.append({'at':stamp if re.fullmatch(r'[\dT:+.Z -]{5,40}',stamp) else '', 'level':level})
            z.writestr(f'logs/{i}.json',json.dumps(selected))
    return target
