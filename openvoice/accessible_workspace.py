"""Loopback-only, keyboard and screen-reader oriented manuscript and playback workspace."""
from __future__ import annotations
import html
import io
import json
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

PAGE='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Openmukti accessible workspace</title><style>
:root{color-scheme:light dark}body{max-width:58rem;margin:1rem auto;padding:0 1rem;font:1.1rem/1.5 system-ui}textarea{font:inherit;width:98%;min-height:13rem}
button,input,a{font:inherit;padding:.5rem;margin:.2rem}*:focus-visible{outline:4px solid #ff9500}audio{width:100%;margin:1rem 0}label{display:block;font-weight:600}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
</style><a href="#manuscript">Skip to manuscript</a><main><h1>Openmukti accessible workspace</h1>
<p>Open a local text file, edit the manuscript, then generate audio. Use the media controls to play, pause, seek or change volume.</p>
<label for="local">Open UTF-8 text</label><input type="file" id="local" accept=".txt,.md">
<label for="manuscript">Manuscript</label><textarea id="manuscript" spellcheck="true">INITIAL_TEXT</textarea>
<p><button id="save">Download text</button><button id="generate">Generate narration</button></p>
<h2>Playback</h2><audio id="player" controls aria-label="Narration playback"></audio>
<a id="sound" download="narration.wav" hidden>Download narration WAV</a><p id="status" role="status" aria-live="polite">Ready</p>
</main><script>
const $=id=>document.getElementById(id), say=s=>$('status').textContent=s;
$('local').onchange=async()=>{const file=$('local').files[0];if(file){$('manuscript').value=await file.text();say('Loaded '+file.name);}};
$('save').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([$('manuscript').value],{type:'text/plain'}));a.download='manuscript.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);};
let previous;
$('generate').onclick=async()=>{const button=$('generate');button.disabled=true;say('Generating narration');try {
 const r=await fetch(location.pathname+'audio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('manuscript').value})});
 if(!r.ok)throw new Error(await r.text());const next=URL.createObjectURL(await r.blob());$('player').src=next;$('sound').href=next;$('sound').hidden=false;if(previous)URL.revokeObjectURL(previous);previous=next;say('Narration ready');$('player').focus();
}catch(e){say('Could not render: '+e.message);}finally{button.disabled=false;}};
</script></html>'''


def start_workspace(manuscript,engine,settings,options,bridge=None,locale='en'):
    from .service import render_text
    token=secrets.token_urlsafe(24)
    base='/'+token+'/'
    lock=threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass
        def reply(self,status,content,mime):
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def valid(self,path):
            return self.path==base+path and self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if bridge and self.valid('controls'):
                try:self.reply(200,json.dumps(bridge.request('list'),ensure_ascii=False).encode(),'application/json')
                except (ValueError,RuntimeError) as exc:self.reply(409,str(exc).encode(),'text/plain; charset=utf-8')
                return
            if not self.valid(''):
                self.send_error(404)
                return
            page=PAGE
            if bridge:
                from .access_bridge import CONTROLS_HTML
                page=page.replace('</html>',CONTROLS_HTML+'</html>')
            if locale!='en':
                from .interface_language import web_page
                page=web_page(page,locale)
            self.reply(200,page.replace('INITIAL_TEXT',html.escape(manuscript)).encode(),'text/html; charset=utf-8')
        def do_POST(self):
            control=bool(bridge and self.valid('control'))
            if not (self.valid('audio') or control) or self.headers.get('Origin') not in (None,f'http://127.0.0.1:{self.server.server_port}'):
                self.send_error(403)
                return
            if not lock.acquire(False):
                self.send_error(503,'A render is already running')
                return
            try:
                self.connection.settimeout(45)
                size=int(self.headers.get('Content-Length','0'))
                if not 1<=size<=512*1024 or self.headers.get_content_type()!='application/json':
                    raise ValueError('Send at most 512 KiB of JSON text')
                obj=json.loads(self.rfile.read(size))
                if not isinstance(obj,dict):raise ValueError('Expected a JSON object')
                if control:
                    self.reply(200,json.dumps(bridge.request('act',obj)).encode(),'application/json')
                    return
                if not isinstance(obj.get('text'),str) or not obj['text'].strip():
                    raise ValueError('Enter manuscript text')
                with tempfile.TemporaryDirectory() as tmp:
                    p=render_text(obj['text'],Path(tmp)/'speech.wav',engine() if callable(engine) else engine,settings,options)
                    self.send_response(200)
                    self.send_header('Content-Type','audio/wav')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Content-Length',str(p.stat().st_size))
                    self.end_headers()
                    import shutil
                    with p.open('rb') as f:
                        shutil.copyfileobj(f,self.wfile,1<<20)
            except (BrokenPipeError,ConnectionResetError):
                pass
            except (ValueError,OSError,RuntimeError,TypeError) as exc:
                self.reply(422,str(exc).encode(),'text/plain; charset=utf-8')
            finally:
                lock.release()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server,f'http://127.0.0.1:{server.server_port}{base}'
