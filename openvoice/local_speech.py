"""Loopback-only speech service and one-chunk lookahead for streaming playback."""
from __future__ import annotations

import base64
import html
import json
import os
import socket
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engines import SpeechSettings, get_engine
from .engines.builtin import play_wav
from .service import JobOptions, prepared_speech_units, render_speech_unit, render_text
from .render_cache import renderer_for


def speech_chunks(text,engine,settings,options):
    units=prepared_speech_units(text,options)
    if not units:
        raise ValueError('Speech input is empty')
    render=renderer_for(options,render_speech_unit)
    with tempfile.TemporaryDirectory() as root, ThreadPoolExecutor(max_workers=1) as executor:
        def make(index):
            path=Path(root)/f'{index:06}.wav'
            render(units[index],path,engine,settings)
            return path
        current=executor.submit(make,0)
        for i,unit in enumerate(units):
            path=current.result()
            if i+1<len(units):
                current=executor.submit(make,i+1)
            yield i+1,unit.text,path
            path.unlink(missing_ok=True)


def serve(port,engine,settings,options,*,ready=None):
    lock=threading.Semaphore(1)
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.0'
        def log_message(self,*args):
            pass
        def do_POST(self):
            if self.headers.get('Host','').split(':')[0].lower() not in ('127.0.0.1','localhost') or self.headers.get('Origin'):
                self.send_error(403,'Local application requests only')
                return
            if self.path not in ('/speak','/stream'):
                self.send_error(404)
                return
            if self.headers.get_content_type()!='application/json':
                self.send_error(415)
                return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=128*1024:
                    raise ValueError('Limit is 128 KiB')
                self.connection.settimeout(30)
                payload=json.loads(self.rfile.read(size))
                if not isinstance(payload,dict) or not isinstance(payload.get('text'),str) or not payload['text'].strip():
                    raise ValueError('Send a JSON object with a text field')
                text=payload['text']
            except (ValueError,OSError) as exc:
                self.send_error(400,str(exc))
                return
            if not lock.acquire(False):
                self.send_error(503,'Speech engine is busy')
                return
            started=False
            try:
                if self.path=='/stream':
                    records=speech_chunks(text,engine,settings,options)
                    try:
                        for index,words,path in records:
                            if not started:
                                self.send_response(200)
                                self.send_header('Content-Type','application/x-ndjson')
                                self.end_headers()
                                started=True
                            record={'index':index,'text':words,'wav':base64.b64encode(path.read_bytes()).decode()}
                            self.wfile.write(json.dumps(record).encode()+b'\n')
                            self.wfile.flush()
                        self.wfile.write(b'{"complete":true}\n')
                    finally:
                        records.close()
                else:
                    with tempfile.TemporaryDirectory() as root:
                        path=render_text(text,Path(root)/'speech.wav',engine,settings,options)
                        self.send_response(200)
                        self.send_header('Content-Type','audio/wav')
                        self.send_header('Content-Length',str(path.stat().st_size))
                        self.end_headers()
                        started=True
                        import shutil
                        with path.open('rb') as f:
                            shutil.copyfileobj(f,self.wfile)
            except (BrokenPipeError,ConnectionResetError):
                pass
            except (ValueError,RuntimeError,OSError) as exc:
                if not started:
                    self.send_error(422,'Speech generation failed: '+str(exc)[:200])
                else:
                    self.wfile.write(json.dumps({'error':str(exc)[:500]}).encode()+b'\n')
            finally:
                lock.release()
    with ThreadingHTTPServer(('127.0.0.1',int(port)),Handler) as server:
        if ready:
            ready(server)
        server.serve_forever()


def audition(spec_path,folder):
    from .audio_analysis import waveform
    from .security_tools import staged_file
    from .performance import profiles
    spec=json.loads(Path(spec_path).read_text(encoding='utf-8'))
    cast=profiles(spec)
    text=spec.get('test_text','')
    if not text.strip():
        raise ValueError('Include a test_text passage in the cast file')
    root=Path(folder)
    root.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,(name,p) in enumerate(cast.items(),1):
        model=p.get('model','')
        if model and (Path(spec_path).parent/model).is_file():
            model=str((Path(spec_path).parent/model).resolve())
        voice=p.get('voice','')
        backend=get_engine(p.get('engine','auto'),model,voice)
        settings=SpeechSettings(voice=voice,model=model,speaker_id=p.get('speaker_id'),language=p.get('language','auto'),
                                rate=int(p.get('rate',0)),pitch=int(p.get('pitch',0)),volume=int(p.get('volume',100)))
        file=root/f'voice-{i}.wav'
        render_text(text,file,backend,settings,JobOptions(cache_dir=spec.get('cache_dir','')))
        report=waveform(file,32)
        rows.append(f'<tr><th>{html.escape(name)}</th><td>{html.escape(backend.key)} / {html.escape(voice)}</td><td><audio controls preload="none" src="{file.name}"></audio></td><td>{report["seconds"]:.2f} s, {report["clipped_samples"]} samples at full scale</td></tr>')
    with staged_file(root/'auditions.html') as tmp:
        tmp.write_text('<!doctype html><meta charset="utf-8"><title>Voice auditions</title><h1>Voice auditions</h1><p>'+html.escape(text)+'</p><table><tr><th>Profile</th><th>Voice</th><th>Listen</th><th>Measurement</th></tr>'+''.join(rows)+'</table>',encoding='utf-8')
    return root/'auditions.html'
