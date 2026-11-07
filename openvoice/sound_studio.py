"""Multitrack sound design. All times are seconds, gains are linear."""
from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from .fftools import find_binary
from .video import _run, audio_duration

ROLES = ('narration', 'music', 'effects', 'ambience')
SPACES = {'dry':'', 'small room':'aecho=0.8:0.65:32:0.18',
          'hall':'aecho=0.8:0.72:72|140:0.28|0.18',
          'telephone':'highpass=f=350,lowpass=f=3200',
          'underwater':'lowpass=f=600'}
AUDIO_TYPES = {'.wav', '.flac', '.mp3', '.m4a', '.aac', '.ogg', '.opus', '.aiff'}


def number(value, low, high, label):
    try:
        value = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'Invalid {label}') from exc
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be between {low} and {high}')
    return value


def envelope(points, duration):
    pairs = [(number(t, 0, duration, 'curve time'), number(g, 0, 8, 'gain')) for t,g in points]
    if not pairs or len(pairs) > 64 or any(a[0]>=b[0] for a,b in zip(pairs, pairs[1:])):
        raise ValueError('Use 1–64 increasing time and gain pairs')
    expr = str(pairs[-1][1])
    for (ta,ga),(tb,gb) in reversed(list(zip(pairs,pairs[1:]))):
        ramp = f'{ga}+({gb}-{ga})*(t-{ta})/({tb}-{ta})'
        expr = f'if(lt(t,{tb}),{ramp},{expr})'
    return f"volume='if(lt(t,{pairs[0][0]}),{pairs[0][1]},{expr})':eval=frame"


def read_session(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('tracks'),list) or not 1 <= len(data['tracks']) <= 128:
        raise ValueError('A sound session must contain 1–128 tracks')
    tracks = []
    for i,row in enumerate(data['tracks'], 1):
        if not isinstance(row, dict) or not isinstance(row.get('file'),str):
            raise ValueError(f'Track {i} needs an audio file')
        item = dict(row, file=(path.parent/row['file']).resolve())
        if not item['file'].is_file() or item.get('role','effects') not in ROLES:
            raise ValueError(f'Track {i} has an invalid source or role')
        if item.get('impulse'):
            item['impulse'] = (path.parent/item['impulse']).resolve(strict=True)
        tracks.append(item)
    markers = data.get('markers',[])
    for m in markers:
        number(m['time'],0,2592000,'marker time')
    return data, tracks


def mix_session(session, output, *, stem='', control=None, preview=0):
    data, tracks = read_session(session)
    with tempfile.TemporaryDirectory(prefix='openmukti-loop-') as room:
        for i,row in enumerate(tracks):
            if row.get('loop') and row.get('loop_crossfade',0):
                clip=Path(room)/f'loop-{i}.wav'
                cyclic_clip(row['file'],clip,row.get('offset',0),row['loop_crossfade'],control)
                row.update(file=clip,offset=0)
        return _render_mix(data,tracks,output,stem,control,preview)


def _render_mix(data,tracks,output,stem,control,preview):
    target = Path(output).expanduser().resolve()
    if target.suffix.lower() not in AUDIO_TYPES or any(target in (r['file'],r.get('impulse')) for r in tracks):
        raise ValueError('Choose a separate audio output')
    ff = find_binary('ffmpeg')
    if not ff:
        raise RuntimeError('Sound mixing requires FFmpeg')
    number(preview,0,2592000,'preview duration')
    args, graph, buses = [], [], {role:[] for role in ROLES}
    input_index = 0
    for i,row in enumerate(tracks):
        role = row.get('role','effects')
        if row.get('muted') or (stem and role != stem):
            continue
        src = row['file']
        if row.get('loop') and not row.get('duration'):
            raise ValueError('A looping track requires a duration')
        if row.get('loop'):
            args += ['-stream_loop','-1']
        args += ['-i',str(src)]
        slot = input_index
        input_index += 1
        start = number(row.get('start',0),0,2592000,'start time')
        offset = number(row.get('offset',0),0,2592000,'source offset')
        duration = number(row['duration'] if 'duration' in row else audio_duration(src)-offset, .0001,2592000,'clip duration')
        gain = number(row.get('gain',1),0,8,'gain')
        pan = number(row.get('pan',0),-1,1,'pan')
        filters = [f'atrim=start={offset}:duration={duration}', 'asetpts=PTS-STARTPTS',
                   'aresample=48000','aformat=sample_fmts=fltp:channel_layouts=stereo',f'volume={gain}']
        if pan:
            filters.append(f'pan=stereo|c0={min(1,1-pan)}*c0|c1={min(1,1+pan)}*c1')
        if row.get('curve'):
            filters.append(envelope(row['curve'],duration))
        for key, tag in [('fade_in','in'),('fade_out','out')]:
            if row.get(key):
                d=number(row[key],.0001,duration,key)
                filters.append(f'afade=t={tag}:st={duration-d if tag=="out" else 0}:d={d}')
        space=row.get('space','dry')
        if space not in SPACES:
            raise ValueError('Unknown acoustic space')
        if SPACES[space]:
            filters.append(SPACES[space])
        if 'target_lufs' in row:
            filters.append(f"loudnorm=I={number(row['target_lufs'],-40,-6,'loudness')}:TP=-1.5:LRA=11")
        chain = f'[{slot}:a]'+','.join(filters)
        if row.get('impulse'):
            args += ['-i',str(row['impulse'])]
            graph.extend([chain+f'[dry{i}]', f'[{input_index}:a]aresample=48000,aformat=channel_layouts=stereo[ir{i}]'])
            chain = f'[dry{i}][ir{i}]afir=dry=1:wet=1'
            input_index += 1
        graph.append(chain+f',adelay={round(1000*start)}:all=1[trk{i}]')
        buses[role].append(f'[trk{i}]')

    def combine(labels, name):
        if labels:
            graph.append(''.join(labels)+(f'amix=inputs={len(labels)}:duration=longest:normalize=0' if len(labels)>1 else 'anull')+'['+name+']')
            return '['+name+']'
        return ''
    labels = {role: combine(bus,role) for role,bus in buses.items() if bus}
    if not labels:
        raise ValueError('No active tracks for this mix')
    if data.get('duck_music') and 'narration' in labels and 'music' in labels:
        graph += ['[narration]asplit=2[voiceout][key0]', '[key0]apad[key]',
                  '[music][key]sidechaincompress=threshold=0.035:ratio=8:attack=20:release=320[ducked]']
        labels.update(narration='[voiceout]', music='[ducked]')
    combine(list(labels.values()),'premix')
    graph.append('[premix]alimiter=limit=0.96:level=0:latency=1[out]')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        staged = Path(tmp)/('mix'+target.suffix)
        graph_path = Path(tmp)/'filters.txt'
        graph_path.write_text(';'.join(graph),encoding='utf-8')
        cmd=[ff,'-nostdin','-loglevel','error','-y',*args,'-filter_complex_script',str(graph_path),'-map','[out]','-ar','48000']
        if preview:
            cmd+=['-t',str(preview)]
        _run([*cmd,str(staged)],control)
        os.replace(staged,target)
    return target


def export_stems(session, folder):
    _, tracks = read_session(session)
    return [str(mix_session(session,Path(folder)/(role+'.wav'),stem=role)) for role in ROLES
            if any(r.get('role','effects')==role and not r.get('muted') for r in tracks)]


def audio_picture(source, output, kind='waveform', width=1200, height=360):
    if kind not in ('waveform','spectrogram'):
        raise ValueError('Choose waveform or spectrogram')
    width=int(number(width,64,4096,'width'))
    height=int(number(height,64,2048,'height'))
    target=Path(output).resolve()
    source=Path(source).resolve(strict=True)
    if target.suffix.lower()!='.png' or target==source:
        raise ValueError('Choose a separate PNG file')
    filter_name='showwavespic' if kind=='waveform' else 'showspectrumpic'
    _run([find_binary('ffmpeg'),'-nostdin','-loglevel','error','-y','-i',str(source),'-lavfi',
          f'{filter_name}=s={width}x{height}','-frames:v','1',str(target)])
    return target


def cyclic_clip(source,destination,offset,fade,control=None):
    """Make a repeatable ambient bed by joining its tail to its head, preserving phase continuity."""
    duration=audio_duration(source)
    offset=number(offset,0,duration-.0001,'loop offset')
    usable=duration-offset
    fade=number(fade,.0001,usable*.45,'loop seam')
    end=duration
    graph=(f'[0:a]aresample=48000,asplit=3[tail][head][mid];'
           f'[tail]atrim=start={end-fade}:end={end},asetpts=PTS-STARTPTS[t];'
           f'[head]atrim=start={offset}:end={offset+fade},asetpts=PTS-STARTPTS[h];'
           f'[t][h]acrossfade=d={fade}:c1=tri:c2=tri[s];'
           f'[mid]atrim=start={offset+fade}:end={end-fade},asetpts=PTS-STARTPTS[m];'
           '[s][m]concat=n=2:v=0:a=1[out]')
    _run([find_binary('ffmpeg'),'-nostdin','-loglevel','error','-y','-i',str(source),'-filter_complex',graph,'-map','[out]','-c:a','pcm_s16le',str(destination)],control)


def transition_markers(file,spacing=2):
    from .audio_analysis import waveform
    d=audio_duration(file)
    points=waveform(file,max(32,min(12000,round(d*20))))['points']
    spacing=number(spacing,.1,max(1,d),'marker spacing')
    candidates=[(r[1],r[0]) for i,r in enumerate(points[1:-1],1) if r[1]<=points[i-1][1] and r[1]<points[i+1][1]]
    chosen=[]
    for _,t in sorted(candidates):
        if all(abs(t-p)>=spacing for p in chosen):
            chosen.append(t)
        if len(chosen)>=100:
            break
    return [{'time':t,'label':'Low-energy transition'} for t in sorted(chosen)]


def credits(session):
    data,tracks=read_session(session)
    return [{'file':r['file'].name,'scene':r.get('scene',''),'role':r.get('role','effects'),
             'credit':r.get('credit',''),'license':r.get('license','Unknown'),'source':r.get('source_url','')}
            for r in tracks]
