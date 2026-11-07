"""Portable narration scores. Voice selection is explicit and source text stays editable."""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import os
import random
import re
import tempfile
import wave
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from .audio import combine_wav, convert_wav
from .engines import SpeechSettings, get_engine
from .engines.base import Cancelled
from .fftools import find_binary
from .progress import emit
from .security_tools import staged_file
from .service import JobOptions, render_text
from .sound_studio import number
from .timeline_tags import parse_duration
from .video import _run

EMOTIONS={'neutral':(1,0,0),'calm':(.92,-.5,-1),'excited':(1.12,1.5,1.5),
          'sad':(.88,-1.2,-2),'angry':(1.06,.7,2),'whisper':(.93,-.3,-7)}
RATES={'x-slow':.65,'slow':.82,'medium':1,'fast':1.2,'x-fast':1.5,'default':1}
PITCH={'x-low':-5,'low':-2,'medium':0,'high':2,'x-high':5,'default':0}
VOLUME={'silent':-90,'x-soft':-12,'soft':-6,'medium':0,'loud':4,'x-loud':7,'default':0}


def scale(value,names,suffix,lo,hi):
    if value in names:
        return names[value]
    if not value.endswith(suffix):
        raise ValueError('Unsupported speech attribute '+value)
    n=float(value[:-len(suffix)])
    return number(n/100 if suffix=='%' else n,lo,hi,'prosody')


def parse_ssml(xml,context=None):
    if len(xml)>8*1024**2 or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper():
        raise ValueError('Speech markup exceeds limits or contains a document type')
    try:
        root=ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError('Invalid SSML: '+str(exc)) from exc
    if root.tag.rsplit('}',1)[-1]!='speak':
        raise ValueError('SSML needs a speak root')
    out=[]
    def walk(node,ctx,depth):
        if depth>32:
            raise ValueError('Speech markup is nested too deeply')
        ctx=dict(ctx)
        tag=node.tag.rsplit('}',1)[-1]
        attrs=node.attrib
        if tag not in ('speak','p','s','voice','lang','prosody','emphasis','phoneme','sub','break','mark','audio','emotion','say-as'):
            raise ValueError('Unsupported SSML element '+tag)
        if '{http://www.w3.org/XML/1998/namespace}lang' in attrs:
            ctx['language']=attrs['{http://www.w3.org/XML/1998/namespace}lang']
        if tag=='voice':
            ctx['profile']=attrs.get('name','Narrator')
        if tag=='emphasis':
            level=attrs.get('level','moderate')
            if level not in ('strong','moderate','reduced','none'):
                raise ValueError('Invalid emphasis level')
            ctx['gain_db']=ctx.get('gain_db',0)+{'strong':4,'moderate':2,'reduced':-3,'none':0}[level]
        if tag=='emotion':
            ctx['emotion']=attrs.get('name','neutral')
        if tag=='prosody':
            for key,table,suffix,lo,hi in [('rate',RATES,'%',.35,3),('pitch',PITCH,'st',-18,18),('volume',VOLUME,'dB',-90,12)]:
                if key in attrs:
                    field={'rate':'pace','pitch':'semitones','volume':'gain_db'}[key]
                    v=scale(attrs[key],table,suffix,lo,hi)
                    ctx[field]=ctx.get(field,1)*v if key=='rate' else ctx.get(field,0)+v
        if tag=='break':
            strengths={'none':0,'x-weak':80,'weak':160,'medium':300,'strong':550,'x-strong':900}
            ms=parse_duration(attrs['time']) if 'time' in attrs else strengths.get(attrs.get('strength','medium'))
            if ms is None:
                raise ValueError('Invalid pause strength')
            out.append({'pause':ms/1000})
            return
        if tag=='audio':
            out.append({'sound':attrs.get('src','')})
            return
        if tag=='mark':
            out.append({'mark':attrs.get('name','')})
            return
        content=''.join(node.itertext())
        if tag in ('phoneme','sub','say-as'):
            if tag=='phoneme':
                if attrs.get('alphabet','ipa')!='ipa' or not attrs.get('ph'):
                    raise ValueError('Use alphabet="ipa" and a nonempty phoneme string')
                content='<ipa:'+attrs['ph']+'|'+content+'>'
            elif tag=='sub':
                content=attrs.get('alias',content)
            elif attrs.get('interpret-as') in ('characters','spell-out','digits'):
                content=' '.join(content)
            else:
                raise ValueError('Supported say-as interpretations are characters, spell-out and digits')
            out.append(dict(ctx,text=content))
            return
        if node.text and node.text.strip():
            out.append(dict(ctx,text=node.text.strip()))
        for child in node:
            walk(child,ctx,depth+1)
            if child.tail and child.tail.strip():
                out.append(dict(ctx,text=child.tail.strip()))
        if tag in ('s','p'):
            out.append({'pause':.15 if tag=='s' else .35})
    walk(root,context or {},0)
    return out


def profiles(spec):
    raw=spec.get('profiles',{'Narrator':{'engine':'auto'}})
    result={}
    def resolve(name,ancestors=()):
        if name in result:
            return result[name]
        if name in ancestors or name not in raw or len(ancestors)>32:
            raise ValueError('Missing or cyclic cast profile: '+name)
        row=raw[name]
        if not isinstance(row,dict):
            raise ValueError('Cast profiles must be objects')
        inherited=resolve(row['extends'],ancestors+(name,)) if row.get('extends') else {}
        result[name]={**inherited,**row}
        return result[name]
    for name in raw:
        resolve(name)
    return result


def interpolate(points,t,default):
    if not points:
        return default
    x=[number(a,0,1,'curve position') for a,b in points]
    y=[float(b) for a,b in points]
    if x!=sorted(set(x)) or any(not math.isfinite(v) for v in y):
        raise ValueError('Curve positions must be unique and increasing')
    i=bisect.bisect_right(x,t)
    if i==0:
        return y[0]
    if i==len(x):
        return y[-1]
    return y[i-1]+(y[i]-y[i-1])*(t-x[i-1])/(x[i]-x[i-1])


def read_score(source):
    source=Path(source)
    if source.suffix.lower() in ('.xml','.ssml'):
        return {'scenes':[{'ssml':source.read_text(encoding='utf-8')}]}
    data=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('scenes'),list) or not data['scenes']:
        raise ValueError('A performance score needs a nonempty scenes list')
    return data


def plan_score(spec):
    cast=profiles(spec)
    out=[]
    for scene in spec['scenes']:
        default={'profile':scene.get('narrator','Narrator')}
        palette=spec.get('palettes',{}).get(scene.get('palette',''),{})
        if scene.get('ssml'):
            lines=parse_ssml(scene['ssml'],default)
        else:
            lines=[dict(default,**item) if 'profile' not in item else dict(item) for item in scene.get('passages',[])]
        for i,line in enumerate(lines):
            if 'text' in line:
                name=line.get('profile',default['profile'])
                if name not in cast:
                    raise ValueError('Undefined voice profile '+name)
                p={**cast[name],**scene.get('cast',{}).get(name,{}),**line}
                for key,base in [('pace',1),('semitones',0),('gain_db',0)]:
                    p[key]=interpolate(scene.get('curves',{}).get(key),i/max(1,len(lines)-1),p.get(key,base))
                for word,choices in spec.get('homographs',{}).items():
                    for r in choices:
                        if str(r['context']).casefold() in p['text'].casefold():
                            p['text']=re.sub(r'(?<!\w)'+re.escape(word)+r'(?!\w)',lambda m:'<ipa:'+r['ipa']+'|'+m[0]+'>',p['text'],flags=re.I)
                            break
                language_cast=spec.get('cast_by_language',{})
                if language_cast and '<ipa:' not in p['text']:
                    from .localization_tools import language_spans
                    for span in language_spans(p['text'],spec.get('language','en')):
                        name=language_cast.get(span['language'])
                        if name is not None and name not in cast:
                            raise ValueError('Unrecognized language voice '+name)
                        out.append({**p,**(cast[name] if name else {}),'text':span['text'],'language':span['language']})
                else:
                    out.append(p)
                if scene.get('breath_after_passages') and spec.get('breath_sound') and i+1<len(lines):
                    out.append({'sound':spec['breath_sound']})
            else:
                if 'sound' in line and line['sound'] in palette:
                    line=dict(line,sound=palette[line['sound']])
                out.append(line)
    if not out:
        raise ValueError('Score contains no passages')
    return out


def _silence(path,seconds):
    frames=round(number(seconds,0,86400,'pause')*24000)
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,24000,0,'NONE','not compressed'))
        data=bytes(65536)
        while frames:
            n=min(32768,frames)
            f.writeframesraw(data[:2*n])
            frames-=n


def render_score(source,output,*,cache_dir='',take='',status=None,control=None):
    source=Path(source).resolve(strict=True)
    target=Path(output).expanduser().resolve()
    if target.suffix.lower() not in ('.wav','.mp3','.m4a','.flac','.ogg','.opus'):
        raise ValueError('Unsupported performance output format')
    spec=read_score(source)
    if take:
        if take not in spec.get('takes',{}):
            raise ValueError('Unknown performance take '+take)
        spec=dict(spec,profiles={**spec.get('profiles',{}),**spec['takes'][take]})
    plan=plan_score(spec)
    cast=profiles(spec)
    rng=random.Random(str(spec.get('seed',0)))
    ff=find_binary('ffmpeg')
    if not ff:
        raise RuntimeError('Performance rendering requires FFmpeg')
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        files=[]
        for i,row in enumerate(plan):
            if control:
                control.check()
            emit(status,i/len(plan),'Rendering performance passage '+str(i+1))
            dest=tmp/f'{i:06}.wav'
            if 'mark' in row:
                continue
            if 'pause' in row:
                _silence(dest,row['pause'])
            elif 'sound' in row:
                name=row['sound']
                if name not in spec.get('sounds',{}):
                    raise ValueError('Sound is not in the approved local palette: '+name)
                path=(source.parent/spec['sounds'][name]).resolve(strict=True)
                _run([ff,'-nostdin','-loglevel','error','-y','-i',str(path),'-ar','24000','-ac','1','-c:a','pcm_s16le',str(dest)],control)
            else:
                raw=tmp/'raw.wav'
                choices=[row]+[cast[n] for n in row.get('backups',[])]
                for j,voice in enumerate(choices):
                    try:
                        model=voice.get('model','')
                        if model and (source.parent/model).is_file():
                            model=str((source.parent/model).resolve())
                        settings=SpeechSettings(voice=voice.get('voice',''),model=model,language=voice.get('language','auto'),speaker_id=voice.get('speaker_id'),
                                                rate=int(voice.get('rate',0)),pitch=int(voice.get('pitch',0)),volume=int(voice.get('volume',100)))
                        engine=get_engine(voice.get('engine','auto'),model,settings.voice)
                        render_text(row['text'],raw,engine,settings,JobOptions(cache_dir=cache_dir,pause_ms=0),control)
                        break
                    except Cancelled:
                        raise
                    except (RuntimeError,OSError) as exc:
                        if control:
                            control.check()
                        if j==len(choices)-1:
                            raise
                if row.get('emotion','neutral') not in EMOTIONS:
                    raise ValueError('Unknown emotion')
                pace,pitch,db=EMOTIONS[row.get('emotion','neutral')]
                pace=number(pace*row.get('pace',1),.35,3,'pace')
                pitch=2**(number(pitch+row.get('semitones',0),-18,18,'pitch')/12)
                db=number(db+row.get('gain_db',0),-90,18,'gain')
                tempo=pace/pitch
                filters=['aresample=24000',f'asetrate={round(24000*pitch)}','aresample=24000']
                while tempo<.5:
                    filters.append('atempo=0.5')
                    tempo*=2
                filters.extend([f'atempo={tempo}',f'volume={db}dB','afade=t=in:d=0.004',
                                'areverse','afade=t=in:d=0.004','areverse'])
                _run([ff,'-nostdin','-loglevel','error','-y','-i',str(raw),'-af',','.join(filters),'-ar','24000','-ac','1','-c:a','pcm_s16le',str(dest)],control)
                if row.get('prosody_curve'):
                    from .prosody import shape_recording
                    curved=tmp/'curved.wav'
                    shape_recording(dest,curved,row['prosody_curve'],control)
                    os.replace(curved,dest)
            files.append(dest)
            if 'text' in row and spec.get('pause_range') and i<len(plan)-1:
                lo,hi=spec['pause_range']
                lo=number(lo,0,15,'minimum pause')
                hi=number(hi,lo,15,'maximum pause')
                pause=tmp/f'p{i}.wav'
                _silence(pause,rng.uniform(lo,hi))
                files.append(pause)
        joined=tmp/'joined.wav'
        combine_wav(files,joined,control=control)
        with staged_file(target) as staged:
            if target.suffix.lower()=='.wav':
                import shutil
                shutil.copyfile(joined,staged)
            else:
                convert_wav(joined,staged,control=control)
    emit(status,1,'Performance saved')
    return target
