"""CLI entry points shared with the desktop production tools."""
from __future__ import annotations

import argparse
import datetime
import getpass
import json
import os
import sys
from pathlib import Path


def _io(p,source='source',output='output'):
    p.add_argument(source)
    p.add_argument(output)


def _voice(p):
    p.add_argument('--engine',default='auto')
    p.add_argument('--voice',default='')
    p.add_argument('--model',default='')
    p.add_argument('--language',default='auto')
    p.add_argument('--gpu',action=argparse.BooleanOptionalAction,default=None)


def register(sub):
    from .distribution import PRESETS
    s=sub.add_parser('studio',help='Production tools for editorial review, casting, mixing, artwork and release engineering')
    group=s.add_subparsers(dest='tool',required=True)
    p=group.add_parser('import',help='Assemble documents using saved JSON import rules')
    p.add_argument('sources',nargs='+')
    p.add_argument('-w','--output',required=True)
    p.add_argument('--preset')
    p=group.add_parser('article',help='Import a public HTTP(S) article into UTF-8 text')
    _io(p,'url')
    p=group.add_parser('ocr-layout',help='Produce aligned word boxes, layout classification and correction view')
    _io(p)
    p.add_argument('--language',default='eng')
    p.add_argument('--psm',type=int,default=3)
    p.add_argument('--compare-psm',type=int,default=6)
    p.add_argument('--gpu',action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--margin-box',nargs=4,type=int,action='append',default=[],metavar=('LEFT','TOP','RIGHT','BOTTOM'))
    p.add_argument('--margin-language',help='Local traineddata for margin annotations, optionally a handwriting-specific model')
    p=group.add_parser('review',help='Apply project-specific grammar, style and OCR rules')
    p.add_argument('source')
    p.add_argument('--rules')
    p.add_argument('--apply',metavar='OUTPUT')
    p=group.add_parser('learn',help='Learn repeated OCR substitutions from paired source and corrected text')
    p.add_argument('original')
    p.add_argument('corrected')
    p.add_argument('rules')
    p=group.add_parser('compare',help='Create a side-by-side HTML manuscript comparison')
    p.add_argument('original')
    p.add_argument('edited')
    p.add_argument('output')
    p=group.add_parser('cast-map',help='Review speaker timeline, shared scenes and dialogue distribution')
    _io(p)
    p.add_argument('--name',action='append',default=[])
    p.add_argument('--rules')
    p=group.add_parser('localize',help='Prepare locale-specific punctuation, pronunciation and transliteration')
    _io(p)
    p.add_argument('--locale',required=True)
    p.add_argument('--dates',action='store_true')
    p.add_argument('--numbers',action='store_true')
    p.add_argument('--currency',default='')
    p.add_argument('--diacritics',choices=['preserve','strip'],default='preserve')
    p.add_argument('--romanization',default='')
    p=group.add_parser('language-test',help='Show or render a language-specific test passage')
    p.add_argument('locale')
    p.add_argument('--output')
    _voice(p)
    p=group.add_parser('score',help='Render a narration score or SSML file')
    _io(p)
    p.add_argument('--cache-dir',default='')
    p.add_argument('--take',default='')
    p.add_argument('--gpu',action=argparse.BooleanOptionalAction,default=None)
    p=group.add_parser('audition',help='Create offline voice samples, controls and listening comparisons')
    _io(p,'source','folder')
    p=group.add_parser('benchmark',help='Measure real synthesis speed, signal and process-tree memory')
    _voice(p)
    p.add_argument('--text',default='The first chapter begins on a quiet morning.')
    p.add_argument('--repeat',type=int,default=2)
    p.add_argument('--output')
    p=group.add_parser('serve',help='Start a loopback-only JSON-to-WAV /speak and /stream service')
    _voice(p)
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--cache-dir',default='')
    p=group.add_parser('stream',help='Play each speech chunk while preparing the next')
    _voice(p)
    p.add_argument('source')
    p.add_argument('--cache-dir',default='')
    p=group.add_parser('mix',help='Render a multitrack sound session')
    _io(p)
    p.add_argument('--stem',default='',choices=['','narration','music','effects','ambience'])
    p.add_argument('--preview',type=float,default=0)
    p=group.add_parser('stems',help='Export synchronized role stems from a sound session')
    _io(p)
    p=group.add_parser('signal',help='Analyze waveform, clipping, likely clicks and near-silent regions')
    p.add_argument('source')
    p.add_argument('--bins',type=int,default=640)
    p.add_argument('--output')
    p.add_argument('--gpu',action=argparse.BooleanOptionalAction,default=None)
    p=group.add_parser('audio-picture',help='Create a large waveform or spectrogram image')
    _io(p)
    p.add_argument('--kind',choices=['waveform','spectrogram'],default='waveform')
    p.add_argument('--width',type=int,default=1200)
    p.add_argument('--height',type=int,default=360)
    p=group.add_parser('design',help='Start a reusable cover or video template')
    p.add_argument('output')
    p.add_argument('--title',required=True)
    p.add_argument('--byline',default='')
    p.add_argument('--style',choices=['paperback','lecture','comic','notebook','chapter card','music'],default='paperback')
    p.add_argument('--palette',choices=['midnight','paper','chalk','contrast'],default='midnight')
    p=group.add_parser('artwork',help='Render a storyboard frame, cover or layout preview')
    _io(p)
    p.add_argument('--time',type=float,default=0)
    p.add_argument('--duration',type=float,default=10)
    p.add_argument('--guides',action='store_true')
    p.add_argument('--audio')
    p=group.add_parser('queue',help='Schedule and resume local productions')
    p.add_argument('db')
    q=p.add_subparsers(dest='action',required=True)
    a=q.add_parser('add')
    a.add_argument('--at',help='ISO 8601 local or offset-aware date and time')
    a.add_argument('--priority',type=int,default=0)
    a.add_argument('arguments',nargs=argparse.REMAINDER)
    q.add_parser('list')
    for action in ('cancel','retry','priority'):
        a=q.add_parser(action)
        a.add_argument('id',type=int)
        if action=='priority':
            a.add_argument('value',type=int)
    a=q.add_parser('work')
    a.add_argument('--follow',action='store_true')
    a.add_argument('--profile',choices=['low','balanced','fast'],default='balanced')
    a.add_argument('--timeout',type=float,default=0)
    a.add_argument('--parallel',type=int,default=1)
    a.add_argument('--energy-saving',action='store_true')
    a.add_argument('--idle-timeout',type=float,default=0)
    a.add_argument('--max-process-mb',type=float,default=0)
    for flag in ('min-disk-mb','min-memory-mb','max-temp','min-battery'):
        a.add_argument('--'+flag,type=float,default=0)
    for cmd,helptext in [('daisy','Package chapter recordings as a DAISY 2.02 navigation book'),('chapter-art','Embed MP3 chapter titles and artwork'),('backup','Create an authenticated encrypted backup'),('restore','Restore an authenticated encrypted backup'),('support','Create a redacted support bundle')]:
        p=group.add_parser(cmd,help=helptext)
        if cmd=='support':
            p.add_argument('output')
            p.add_argument('--log',action='append',default=[])
        else:
            _io(p)
        if cmd=='chapter-art':
            p.add_argument('--manifest',required=True)
    p=group.add_parser('preflight',help='Inspect actual audio headers against a destination profile')
    p.add_argument('files',nargs='+')
    p.add_argument('--preset',default='spoken-mp3',help=', '.join(PRESETS)+' or a JSON rules file')
    p=group.add_parser('upload',help='Send one finished file to an explicitly configured rclone remote')
    _io(p,'source','remote')
    p=group.add_parser('keygen',help='Generate an Ed25519 signing key and public verification key')
    _io(p,'private','public')
    for cmd in ('sign','verify'):
        p=group.add_parser(cmd,help=cmd.capitalize()+' a detached Ed25519 signature')
        p.add_argument('source')
        p.add_argument('key')
        p.add_argument('signature')
    p=group.add_parser('extension',help='Run a signed declarative text extension with restricted operations')
    _io(p)
    p.add_argument('--manifest',required=True)
    p.add_argument('--public-key',required=True)
    p.add_argument('--signature',required=True)
    p.add_argument('--allow',action='append',choices=['replace','normalize','case','trim'],default=[])
    from .studio_extra import register_extra
    register_extra(group)
    return group


def _json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if path else default


def _write(value,path=None):
    if path:
        from .security_tools import staged_file
        with staged_file(path) as tmp:
            tmp.write_text(value,encoding='utf-8')
    else:
        print(value)


def report(obj,path=None):
    _write(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n',path)


def run(a):
    from .documents import read_document
    t=a.tool
    if t=='import':
        from .import_studio import batch_read
        _write(batch_read(a.sources,_json(a.preset)),a.output)
    elif t=='article':
        from .import_studio import read_article
        _write(read_article(a.url),a.output)
    elif t=='ocr-layout':
        from .ocr import OCRSettings
        from .page_layout import write_review
        write_review(a.source,a.output,OCRSettings(language=a.language,psm=a.psm),a.compare_psm,margin_boxes=a.margin_box,margin_language=a.margin_language)
    elif t=='review':
        from .editorial_studio import suggestions,apply_suggestions
        text=read_document(a.source)
        issues=suggestions(text,_json(a.rules))
        if a.apply:
            _write(apply_suggestions(text,issues),a.apply)
        else:
            report(issues)
    elif t=='learn':
        from .editorial_studio import learn_edits
        rules=_json(a.rules) if Path(a.rules).exists() else {}
        report(learn_edits(read_document(a.original),read_document(a.corrected),rules),a.rules)
    elif t=='compare':
        from .editorial_studio import compare_html
        compare_html(read_document(a.original),read_document(a.edited),a.output)
    elif t=='cast-map':
        from .editorial_studio import script_report,write_script_view
        r=script_report(read_document(a.source),a.name,_json(a.rules))
        if Path(a.output).suffix.lower()=='.html':
            write_script_view(r,a.output)
        else:
            report(r,a.output)
    elif t=='localize':
        from .localization_tools import localized
        _write(localized(read_document(a.source),a.locale,numbers=a.numbers,dates=a.dates,currency=a.currency,arabic_marks=a.diacritics,romanization=a.romanization),a.output)
    elif t in ('serve','stream','language-test'):
        from .engines import get_engine,SpeechSettings
        from .service import JobOptions,render_text
        from .local_speech import serve,speech_chunks,play_wav
        from .localization_tools import TEST_PASSAGES
        opts=JobOptions(cache_dir=getattr(a,'cache_dir',''))
        if t=='language-test':
            text=TEST_PASSAGES.get(a.locale.lower().replace('_','-').split('-')[0])
            if not text:
                raise ValueError('Available test languages: '+', '.join(TEST_PASSAGES))
            if not a.output:
                print(text)
                return 0
        backend=get_engine(a.engine,a.model,a.voice)
        settings=SpeechSettings(voice=a.voice,model=a.model,language=a.locale if t=='language-test' else a.language)
        if t=='serve':
            serve(a.port,backend,settings,opts,ready=lambda server:print(f'Listening on 127.0.0.1:{server.server_port}',flush=True))
        elif t=='stream':
            for _,_,path in speech_chunks(read_document(a.source),backend,settings,opts):
                play_wav(path)
        else:
            render_text(text,a.output,backend,settings,opts)
    elif t=='score':
        from .performance import render_score
        render_score(a.source,a.output,cache_dir=a.cache_dir,take=a.take)
    elif t=='benchmark':
        from .inspection import benchmark
        report(benchmark(a.engine,a.voice,a.model,a.text,a.repeat),a.output)
    elif t=='audition':
        from .local_speech import audition
        print(audition(a.source,a.folder))
    elif t in ('mix','stems','audio-picture'):
        from .sound_studio import mix_session,export_stems,audio_picture
        if t=='mix':
            mix_session(a.source,a.output,stem=a.stem,preview=a.preview)
        elif t=='stems':
            report(export_stems(a.source,a.output))
        else:
            audio_picture(a.source,a.output,a.kind,a.width,a.height)
    elif t=='signal':
        from .audio_analysis import waveform
        report(waveform(a.source,a.bins),a.output)
    elif t in ('design','artwork'):
        from .storyboard import Storyboard,template
        if t=='design':
            report(template(a.style,a.title,a.byline,a.palette),a.output)
        else:
            Storyboard.load(a.source,a.audio).export_cover(a.output,a.time,a.duration,guides=a.guides)
    elif t=='queue':
        from .job_queue import enqueue,jobs,modify,worker
        if a.action=='add':
            argv=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
            print(enqueue(a.db,argv,a.priority,datetime.datetime.fromisoformat(a.at).timestamp() if a.at else 0))
        elif a.action=='list':
            report(jobs(a.db))
        elif a.action=='work':
            if not 1<=a.parallel<=min(32,os.cpu_count() or 1):
                raise ValueError('Worker count exceeds the available CPUs or the limit of 32')
            def work():
                return worker(a.db,follow=a.follow,profile=a.profile,timeout=a.timeout,idle_timeout=a.idle_timeout,max_process_mb=a.max_process_mb,energy_saving=a.energy_saving,min_disk_mb=a.min_disk_mb,min_memory_mb=a.min_memory_mb,max_temp=a.max_temp,min_battery=a.min_battery)
            if a.parallel==1:
                return int(bool(work()))
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=a.parallel) as pool:
                values=[pool.submit(work) for _ in range(a.parallel)]
                return int(any([f.result() for f in values]))
        else:
            modify(a.db,a.id,a.action,getattr(a,'value',0))
    elif t in ('daisy','preflight','chapter-art','upload'):
        from .distribution import daisy,compliance,chapter_art,upload,PRESETS
        if t=='daisy':
            daisy(a.source,a.output)
        elif t=='chapter-art':
            chapter_art(a.source,a.manifest,a.output)
        elif t=='upload':
            print(upload(a.source,a.remote))
        else:
            rows=compliance(a.files,a.preset if a.preset in PRESETS else _json(a.preset))
            report(rows)
            return int(any(not r['passed'] for r in rows))
    elif t=='support':
        from .inspection import support_bundle
        support_bundle(a.output,a.log)
    elif t in ('backup','restore','keygen','sign','verify','extension'):
        from .security_tools import backup,generate_key,signature,run_extension
        if t in ('backup','restore'):
            pw=getpass.getpass('Backup passphrase: ')
            if t=='backup' and pw!=getpass.getpass('Repeat passphrase: '):
                raise ValueError('Passphrases differ')
            backup(a.source,a.output,pw,decrypt=t=='restore')
        elif t=='keygen':
            generate_key(a.private,a.public)
        elif t=='extension':
            _write(run_extension(a.manifest,read_document(a.source),trusted_key=a.public_key,signature_file=a.signature,permissions=a.allow),a.output)
        else:
            signature(a.source,a.key,a.signature,verify=t=='verify')
    else:
        from .studio_extra import run_extra
        return run_extra(a)
    return 0
