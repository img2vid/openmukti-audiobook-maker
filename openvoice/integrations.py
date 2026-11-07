"""User-initiated local illustration and speech-command adapters."""
import base64
import http.client
import io
import json
import queue
import time
from pathlib import Path
from .desktop_prefs import authorized
from .security_tools import staged_file


def illustration(prompt,output,port=7860,width=768,height=768,steps=24):
    from PIL import Image
    authorized('network')
    if not prompt.strip() or len(prompt)>8000 or not 1<=port<=65535 or not 1<=steps<=150 or any(n<64 or n>2048 or n%8 for n in (width,height)):
        raise ValueError('Supply a prompt and dimensions divisible by 8 between 64 and 2048')
    if Path(output).suffix.lower()!='.png':
        raise ValueError('Choose a PNG image output')
    req=json.dumps({'prompt':prompt,'width':width,'height':height,'steps':steps,'batch_size':1,'n_iter':1})
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=600)
    try:
        conn.request('POST','/sdapi/v1/txt2img',req.encode('utf-8'),{'Content-Type':'application/json'})
        response=conn.getresponse()
        if response.status!=200:
            raise RuntimeError(f'Local illustration service returned HTTP {response.status}')
        raw=response.read(40*1024**2+1)
        if len(raw)>40*1024**2:
            raise ValueError('Generated image is too large')
        data=json.loads(raw)
        img64=data['images'][0].split(',')[-1]
        with Image.open(io.BytesIO(base64.b64decode(img64,validate=True))) as im:
            if im.width*im.height>16*1024**2:
                raise ValueError('Generated image exceeds pixel limit')
            with staged_file(output) as tmp:
                im.convert('RGB').save(tmp,'PNG')
    finally:
        conn.close()
    return Path(output)


def microphone_command(model_folder,allowed,seconds=6):
    authorized('microphone')
    if not 1<=seconds<=20 or not allowed:
        raise ValueError('Invalid listening interval or empty command vocabulary')
    try:
        import vosk,sounddevice as sd
    except (ImportError,OSError) as exc:
        raise RuntimeError('Install the voice-control extra and select a local Vosk model') from exc
    model=vosk.Model(str(Path(model_folder).resolve(strict=True)))
    grammar=[*allowed,'[unk]']
    rate=int(sd.query_devices(kind='input')['default_samplerate'])
    rec=vosk.KaldiRecognizer(model,rate,json.dumps(grammar))
    q=queue.Queue(maxsize=128)
    def callback(indata,frames,timing,status):
        try:
            q.put_nowait(bytes(indata))
        except queue.Full:
            pass
    with sd.RawInputStream(samplerate=rate,blocksize=max(400,rate//12),dtype='int16',channels=1,callback=callback):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            try:
                block=q.get(timeout=.2)
            except queue.Empty:
                continue
            if rec.AcceptWaveform(block):
                text=json.loads(rec.Result()).get('text','')
                if text in allowed:
                    return text
    text=json.loads(rec.FinalResult()).get('text','')
    return text if text in allowed else ''
