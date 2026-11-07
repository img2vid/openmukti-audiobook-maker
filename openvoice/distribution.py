"""DAISY 2.02 navigation, illustrated MP3 chapters and destination preflight."""
import datetime
import json
import mimetypes
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as X

from .fftools import find_binary
from .security_tools import staged_file
from .video import audio_duration

PRESETS={'spoken-mp3':{'codec':['mp3'],'sample_rates':[44100,48000],'channels':[1,2],'min_kbps':64},
         'lossless-master':{'codec':['flac','pcm_s16le','pcm_s24le'],'sample_rates':[44100,48000,96000],'channels':[1,2]},
         'podcast-aac':{'codec':['aac'],'sample_rates':[44100,48000],'channels':[1,2],'min_kbps':64}}


def catalog(path):
    path=Path(path).resolve(strict=True)
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not data.get('title') or not isinstance(data.get('chapters'),list) or not data['chapters']:
        raise ValueError('Provide a book title and a nonempty chapters list')
    chapters=[]
    for row in data['chapters']:
        if not isinstance(row,dict) or not isinstance(row.get('audio'),str):
            raise ValueError('Each chapter needs an audio filename')
        chapter=dict(row,audio=(path.parent/row['audio']).resolve(strict=True))
        if row.get('cover'):
            chapter['cover']=(path.parent/row['cover']).resolve(strict=True)
        chapters.append(chapter)
    return data,chapters


def daisy(path,output):
    data,chapters=catalog(path)
    if not data.get('language') or not data.get('publisher'):
        raise ValueError('DAISY requires a language and publisher')
    if not all(c['audio'].suffix.lower()=='.mp3' for c in chapters):
        raise ValueError('Supply separate MP3 chapter recordings')
    durations=[audio_duration(c['audio']) for c in chapters]
    def clock(s):
        secs=round(s)
        return f'{secs//3600:02}:{secs//60%60:02}:{secs%60:02}'
    uid=str(data.get('id') or 'urn:uuid:'+str(uuid.uuid4()))
    ncc=X.Element('html',xmlns='http://www.w3.org/1999/xhtml')
    head=X.SubElement(ncc,'head')
    X.SubElement(head,'title').text=data['title']
    meta={'dc:title':data['title'],'dc:format':'Daisy 2.02','dc:identifier':uid,'dc:publisher':data['publisher'],
          'dc:date':data.get('date') or datetime.date.today().isoformat(),'dc:language':data['language'],
          'ncc:charset':'utf-8','ncc:pageFront':'0','ncc:pageNormal':'0','ncc:pageSpecial':'0','ncc:depth':'1',
          'ncc:multimediaType':'audioNcc','ncc:files':1+2*len(chapters),'ncc:tocItems':len(chapters),'ncc:totalTime':clock(sum(durations))}
    if data.get('author'):
        meta['dc:creator']=data['author']
    for k,v in meta.items():
        X.SubElement(head,'meta',name=k,content=str(v))
    body=X.SubElement(ncc,'body')
    xml=b'<?xml version="1.0" encoding="UTF-8"?>\n'
    with staged_file(output) as tmp, zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
        elapsed=0
        for i,(row,duration) in enumerate(zip(chapters,durations),1):
            base=f'chapter{i:04}'
            title=str(row.get('title') or f'Chapter {i}')
            h=X.SubElement(body,'h1',id=f'h{i}')
            X.SubElement(h,'a',href=base+'.smil#p1').text=title
            smil=X.Element('smil')
            sh=X.SubElement(smil,'head')
            for k,v in {'dc:format':'Daisy 2.02','dc:identifier':uid,'ncc:timeInThisSmil':clock(duration),'ncc:totalElapsedTime':clock(elapsed)}.items():
                X.SubElement(sh,'meta',name=k,content=v)
            X.SubElement(X.SubElement(sh,'layout'),'region',id='txtView')
            seq=X.SubElement(X.SubElement(smil,'body'),'seq',dur=f'{duration:.3f}s')
            par=X.SubElement(seq,'par',id='p1',endsync='last')
            X.SubElement(par,'text',src=f'ncc.html#h{i}',id='t1')
            audio=X.SubElement(par,'seq')
            X.SubElement(audio,'audio',{'src':base+'.mp3','clip-begin':'npt=0.000s','clip-end':f'npt={duration:.3f}s','id':'a1'})
            z.writestr(base+'.smil',xml+b'<!DOCTYPE smil PUBLIC "-//W3C//DTD SMIL 1.0//EN" "http://www.w3.org/TR/REC-smil/SMIL10.dtd">\n'+X.tostring(smil,encoding='utf-8'))
            z.write(row['audio'],base+'.mp3',compress_type=zipfile.ZIP_STORED)
            elapsed+=duration
        z.writestr('ncc.html',xml+b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n'+X.tostring(ncc,encoding='utf-8'))
    return Path(output)


def chapter_art(source,manifest,output):
    try:
        from mutagen.id3 import ID3,ID3NoHeaderError,CHAP,CTOC,APIC,TIT2
    except ImportError as exc:
        raise RuntimeError('Install mutagen for MP3 chapter artwork') from exc
    if Path(source).suffix.lower()!='.mp3' or Path(output).suffix.lower()!='.mp3':
        raise ValueError('Illustrated chapters require MP3 input and output')
    data,chapters=catalog(manifest)
    length=audio_duration(source)
    cursor=0
    entries=[]
    ids=[]
    from PIL import Image
    for n,row in enumerate(chapters,1):
        start=float(row.get('start',cursor))
        end=float(row['end']) if 'end' in row else start+audio_duration(row['audio'])
        if not 0<=cursor<=start<end<=length+.1:
            raise ValueError('Chapter timing is outside the complete recording')
        sub=[TIT2(encoding=3,text=[str(row.get('title',n))])]
        if row.get('cover'):
            cover=row['cover']
            if cover.stat().st_size>16*1024**2:
                raise ValueError('Cover exceeds 16 MiB')
            with Image.open(cover) as im:
                if im.format not in ('PNG','JPEG'):
                    raise ValueError('Chapter artwork must be JPEG or PNG')
                mime=Image.MIME[im.format]
            sub.append(APIC(encoding=3,mime=mime,type=3,desc='Chapter cover',data=cover.read_bytes()))
        key=f'ch{n:04}'
        ids.append(key)
        entries.append(CHAP(element_id=key,start_time=round(start*1000),end_time=round(min(length,end)*1000),
                            start_offset=0xffffffff,end_offset=0xffffffff,sub_frames=sub))
        cursor=end
    with staged_file(output) as tmp:
        shutil.copyfile(source,tmp)
        try:
            tags=ID3(tmp)
        except ID3NoHeaderError:
            tags=ID3()
        tags.delall('CHAP')
        tags.delall('CTOC')
        for e in entries:
            tags.add(e)
        tags.add(CTOC(element_id='toc',flags=3,child_element_ids=ids,sub_frames=[TIT2(encoding=3,text=[data['title']])]))
        tags.save(tmp)
    return Path(output)


def compliance(files,rules):
    rules=PRESETS[rules] if isinstance(rules,str) and rules in PRESETS else rules
    if not isinstance(rules,dict):
        raise ValueError('Choose a supplied or JSON export profile')
    report=[]
    for f in files:
        r=subprocess.run([find_binary('ffprobe'),'-v','error','-show_streams','-show_format','-of','json',str(f)],
                         capture_output=True,timeout=30)
        issues=[]
        stream={}
        if not r.returncode:
            detail=json.loads(r.stdout)
            stream=next((s for s in detail.get('streams',[]) if s.get('codec_type')=='audio'),{})
        if not stream:
            issues.append('No readable audio stream')
        else:
            for field,key,convert in [('codec_name','codec',str),('channels','channels',int),('sample_rate','sample_rates',int)]:
                if rules.get(key) and convert(stream.get(field) or 0) not in rules[key]:
                    issues.append('Outside preset: '+field)
            kbps=int(stream.get('bit_rate') or detail['format'].get('bit_rate') or 0)/1000
            if kbps<rules.get('min_kbps',0):
                issues.append('Bit rate below minimum')
        report.append({'file':str(f),'passed':not issues,'issues':issues})
    return report


def upload(file,remote):
    import re
    from .desktop_prefs import authorized
    authorized('network')
    authorized('external_tools')
    authorized('folders',file)
    path=Path(file).resolve(strict=True)
    tool=shutil.which('rclone')
    if not tool:
        raise RuntimeError('Configure the destination in rclone and add rclone to PATH')
    if not re.fullmatch(r'[\w][\w .-]*:[^\r\n]+',remote) or not path.is_file():
        raise ValueError('Use remote:path/filename as the destination')
    r=subprocess.run([tool,'copyto',str(path),remote],stdin=subprocess.DEVNULL,check=False)
    if r.returncode:
        raise RuntimeError('rclone upload failed with exit code '+str(r.returncode))
    return remote
