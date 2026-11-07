"""Reusable production pipelines, scene status, signal comparison and selective renders."""
from __future__ import annotations
import json
import math
import os
import sys
import subprocess
import tempfile
from pathlib import Path

from .security_tools import staged_file
from .voice_library import _atomic_json

STAGES={'render','video','audiobooks','multivoice','project-render','batch','transform','audio','captions','tag-audio','publish-book','subtitle-pack','read-along'}
STUDIO_STAGES={'import','review','localize','mix','stems','score','artwork','daisy','preflight','signal','chapter-art','compare','cast-map','audio-picture'}


def pipeline(file,*,dry=False):
    file=Path(file).resolve(strict=True)
    data=json.loads(file.read_text(encoding='utf-8'))
    steps=data.get('steps',[])
    if not 1<=len(steps)<=200:
        raise ValueError('A pipeline needs 1–200 steps')
    plan=[]
    for step in steps:
        if not isinstance(step,list) or not step or not all(isinstance(s,str) for s in step):
            raise ValueError('Each step must be a command argument list')
        if step[0] not in STAGES and not (step[0]=='studio' and len(step)>1 and step[1] in STUDIO_STAGES):
            raise ValueError('Unsupported pipeline operation')
        plan.append(step)
    if dry:
        return plan
    from .job_queue import cli_process
    cmd,env=cli_process()
    for i,step in enumerate(plan,1):
        result=subprocess.run(cmd+step,cwd=file.parent,env=env)
        if result.returncode:
            raise RuntimeError(f'Pipeline step {i} failed ({step[0]})')
    return plan


def passages(path,folder,*,indices=(),engine='auto',voice='',model=''):
    """One file per spoken unit and a manifest suitable for selective regeneration."""
    from .documents import read_document
    from .engines import get_engine,SpeechSettings
    from .service import JobOptions,prepared_speech_units,render_speech_unit
    from .render_cache import ChunkStore
    from .security_tools import file_digest
    from dataclasses import asdict
    import hashlib
    root=Path(folder).resolve()
    root.mkdir(parents=True,exist_ok=True)
    backend=get_engine(engine,model,voice)
    settings=SpeechSettings(voice=voice,model=model)
    units=prepared_speech_units(read_document(path),JobOptions())
    chosen=set(indices)
    if not units or any(i<1 or i>len(units) for i in chosen):
        raise ValueError('Passage index is out of range')
    manifest=root/'passages.json'
    store=ChunkStore(root/'cache')
    rows=[]
    from .render_cache import model_identity
    ident=model_identity(backend,settings)
    for i,unit in enumerate(units,1):
        name=f'passage-{i:06}.wav'
        dest=root/name
        key=hashlib.sha256(json.dumps([asdict(unit),asdict(settings),ident],sort_keys=True).encode()).hexdigest()
        if chosen and i not in chosen:
            rows.append({'index':i,'text':unit.text,'file':name,'expected_key':key})
            continue
        with staged_file(dest) as stage:
            store.render(render_speech_unit,unit,stage,backend,settings,refresh=bool(chosen))
        rows.append({'index':i,'text':unit.text,'file':name,'expected_key':key,'rendered_key':key,'sha256':file_digest(dest).hex()})
    old={r['index']:r for r in json.loads(manifest.read_text())['passages']} if manifest.exists() else {}
    for r in rows:
        if 'rendered_key' not in r:
            prior=old.get(r['index'],{})
            if prior.get('rendered_key')==r['expected_key'] and (root/r['file']).is_file():
                r.update(rendered_key=prior['rendered_key'],sha256=prior['sha256'])
                r['status']='reused'
            else:
                r['status']='needs render'
        else:
            r['status']='rendered'
    _atomic_json(manifest,{'passages':rows})
    return rows


def compare_mixes(a,b):
    from .audio_analysis import waveform
    left,right=(waveform(p,200) for p in (a,b))
    def metrics(r):
        peak=max((y[2] for y in r['points']),default=0)
        rms=math.sqrt(sum(y[1]**2 for y in r['points'])/max(1,len(r['points'])))
        return {'seconds':r['seconds'],'peak_dbfs':20*math.log10(max(1e-9,peak)),'rms_dbfs':20*math.log10(max(1e-9,rms)),
                'clipped_samples':r['clipped_samples'],'possible_clicks':len(r['possible_clicks'])}
    v1,v2=map(metrics,(left,right))
    return {'reference':v1,'candidate':v2,'difference':{k:v2[k]-v1[k] for k in v1}}


def transition(a,b,output,seconds):
    from .video import audio_duration,_run
    from .sound_studio import number
    from .fftools import find_binary
    d=number(seconds,.001,min(audio_duration(a),audio_duration(b)),'crossfade duration')
    with staged_file(output) as tmp:
        _run([find_binary('ffmpeg'),'-y','-nostdin','-loglevel','error','-i',str(a),'-i',str(b),
              '-filter_complex',f'[0:a]aresample=48000,aformat=channel_layouts=stereo[a];[1:a]aresample=48000,aformat=channel_layouts=stereo[b];[a][b]acrossfade=d={d}:c1=tri:c2=tri[out]',
              '-map','[out]',str(tmp)])
    return Path(output)


def distribution_metadata(source,out):
    from .distribution import catalog
    from xml.etree import ElementTree as X
    data,chapters=catalog(source)
    rows=[]
    for c in chapters:
        rows.append({k:v for k,v in c.items() if k not in ('audio','cover')}|{'file':c['audio'].name})
    data={k:v for k,v in data.items() if k!='chapters'}|{'chapters':rows}
    if Path(out).suffix.lower()=='.xml':
        dc='http://purl.org/dc/elements/1.1/'
        X.register_namespace('dc',dc)
        root=X.Element('book')
        for src,key in [('title','title'),('language','language'),('author','creator'),('publisher','publisher'),
                        ('date','date'),('id','identifier'),('rights','rights'),('description','description')]:
            if data.get(src):
                X.SubElement(root,'{'+dc+'}'+key).text=str(data[src])
        for chapter in rows:
            X.SubElement(root,'chapter',file=chapter['file']).text=chapter.get('title','')
        with staged_file(out) as tmp:
            X.ElementTree(root).write(tmp,encoding='utf-8',xml_declaration=True)
    else:
        _atomic_json(Path(out),data)
    return Path(out)
