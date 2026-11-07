"""Isolated neural TTS process. Run with its own venv Python, never import Tk.

Only the standard library is imported at module load time. Data arrives as JSON
on stdin; WAV is written to the path passed in the request. Upstream model
weights are downloaded ONLY by a separately approved GUI download action.
"""
from __future__ import annotations
import json
import os
import sys
import wave
from pathlib import Path

_MODEL_CACHE = {}
_VOICE_CACHE = {}
_FAILED_DEVICES = set()


def _espeak_library():
    try:
        import espeakng_loader
        getter = getattr(espeakng_loader, 'get_library_path', None)
        if callable(getter):
            os.environ.setdefault('PHONEMIZER_ESPEAK_LIBRARY', str(getter()))
        data = getattr(espeakng_loader, 'get_data_path', None)
        if callable(data):
            os.environ.setdefault('ESPEAK_DATA_PATH', str(data()))
    except ImportError:
        pass


def _preferred_torch_device():
    """Probe the framework in the engine environment unless CPU was requested."""
    if os.environ.get('OPENMUKTI_GPU_MODE', 'auto') != 'auto':
        return 'cpu'
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda'
        if hasattr(torch, 'xpu') and torch.xpu.is_available():
            return 'xpu'
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return 'mps'
    except (ImportError, RuntimeError, OSError):
        pass
    return 'cpu'


def _kitten_session(tts, accelerated):
    """Keep Kitten's own tokenizer/voice state while replacing its ONNX session."""
    try:
        import onnxruntime as ort
    except (ImportError, OSError):
        return
    backend = getattr(tts, 'model', tts)
    key = next((name for name in ('session','sess','ort_session')
                if isinstance(getattr(backend,name,None),ort.InferenceSession)), None)
    if not key:
        return
    original = getattr(backend,key)
    if not accelerated:
        if original.get_providers() != ['CPUExecutionProvider']:
            original.set_providers(['CPUExecutionProvider'])
        return
    model = getattr(original,'_model_path',None) or getattr(backend,'model_path',None)
    if not model:
        return
    choices = ('CUDAExecutionProvider','ROCMExecutionProvider','MIGraphXExecutionProvider',
               'DmlExecutionProvider','CoreMLExecutionProvider','OpenVINOExecutionProvider',
               'TensorrtExecutionProvider','WebGpuExecutionProvider')
    available = ort.get_available_providers()
    for name in choices:
        if name not in available:
            continue
        opts=ort.SessionOptions()
        if name=='DmlExecutionProvider':
            opts.enable_mem_pattern=False
            opts.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        provider=(name,{'device_type':'GPU'}) if name=='OpenVINOExecutionProvider' else name
        try:
            session=ort.InferenceSession(str(model),sess_options=opts,providers=[provider,'CPUExecutionProvider'])
            if name in session.get_providers():
                setattr(backend,key,session)
                return
        except Exception as exc:
            print(f'Kitten could not initialize {name}: {exc}',file=sys.stderr)
    original.set_providers(['CPUExecutionProvider'])


def synthesize(payload):
    engine = payload['engine']
    if engine == 'kitten':
        device = 'onnx' if os.environ.get('OPENMUKTI_GPU_MODE', 'auto') == 'auto' else 'cpu'
    else:
        device = _preferred_torch_device()
    key=(engine,payload.get('model',''),device)
    if key in _FAILED_DEVICES:
        device='cpu'
    try:
        _synthesize(payload, device)
    except (RuntimeError, OSError, TypeError, ValueError, NotImplementedError) as exc:
        if device == 'cpu':
            raise
        print(f'{device} synthesis failed. Retrying on CPU: {exc}', file=sys.stderr)
        _synthesize(payload, 'cpu')
        _FAILED_DEVICES.add(key)


def _synthesize(payload, device):
    engine = payload['engine']
    output = Path(payload['output'])
    text = payload['text'].strip()
    if not text:
        raise ValueError('Cannot synthesize empty text')
    voice = payload.get('voice') or {'kokoro':'af_heart', 'kitten':'Bella', 'pocket':'alba', 'coqui':''}[engine]
    model = payload.get('model') or ''
    rate = max(0.5, min(2, 1 + int(payload.get('rate', 0)) * 0.06))
    output.parent.mkdir(parents=True, exist_ok=True)
    if engine == 'kokoro':
        _espeak_library()
        from kokoro import KPipeline
        import numpy as np
        import soundfile as sf
        # Language is encoded in the Kokoro voice prefix; forcing 'a' produces
        # incorrect language output for e.g. Japanese or Hindi voices.
        code = voice.split('_', 1)[0][:1]
        if code not in 'abefhijp z'.replace(' ', ''):
            raise ValueError('Invalid Kokoro voice language prefix: ' + voice)
        pipeline = _MODEL_CACHE.setdefault(('kokoro', code, device), None)
        if pipeline is None:
            try:
                pipeline = KPipeline(lang_code=code, device=device)
            except (RuntimeError, ValueError, OSError):
                if device == 'cpu':
                    raise
                pipeline = KPipeline(lang_code=code, device='cpu')
            _MODEL_CACHE[('kokoro', code, device)] = pipeline
        chunks = [np.asarray(audio.detach().cpu() if hasattr(audio, 'detach') else audio, dtype=np.float32).reshape(-1)
                  for _, _, audio in pipeline(text, voice=voice, speed=rate)]
        if not chunks:
            raise RuntimeError('Kokoro produced no audio')
        sf.write(str(output), np.concatenate(chunks), 24000)
    elif engine == 'kitten':
        _espeak_library()
        from kittentts import KittenTTS
        import soundfile as sf
        selected = model or 'KittenML/kitten-tts-nano-0.8'
        if not (selected.startswith('KittenML/kitten-tts-') or Path(selected).exists()):
            raise ValueError('Invalid KittenTTS model identifier: ' + selected)
        tts = _MODEL_CACHE.get(('kitten',selected,device))
        if tts is None:
            tts = KittenTTS(selected)
            _kitten_session(tts,device != 'cpu')
            _MODEL_CACHE[('kitten',selected,device)] = tts
        available = list(getattr(tts, 'available_voices', ()) or ())
        if available and voice not in available:
            raise ValueError('Unsupported KittenTTS voice: ' + voice)
        samples = tts.generate(text, voice=voice, speed=rate)
        sf.write(str(output), samples, 24000)
    elif engine == 'pocket':
        from pocket_tts import TTSModel
        import scipy.io.wavfile as wavfile
        import numpy as np
        language = (payload.get('language') or '').lower().split('-')[0].split('_')[0]
        matched = {'en':'english', 'it':'italian', 'es':'spanish', 'de':'german',
                   'fr':'french', 'pt':'portuguese', 'nl':'dutch'}
        preset_languages = {'giovanni':'italian','lola':'spanish','juergen':'german',
                            'rafael':'portuguese','estelle':'french'}
        selected_model = model or matched.get(language) or preset_languages.get(voice) or 'english'
        tts = _MODEL_CACHE.get(('pocket', selected_model, device))
        if tts is None:
            import inspect
            load_args={'language':selected_model}
            if 'device' in inspect.signature(TTSModel.load_model).parameters:
                load_args['device']=device
            tts = TTSModel.load_model(**load_args)
            if device != 'cpu' and 'device' not in load_args:
                if not callable(getattr(tts,'to',None)):
                    raise RuntimeError('This Pocket TTS model exposes no accelerator interface')
                tts=tts.to(device)
            _MODEL_CACHE[('pocket', selected_model, device)] = tts
        voice_file = payload.get('voice_state_path') or voice
        if payload.get('voice_state_path') and not Path(voice_file).is_file():
            raise FileNotFoundError('Pocket voice was not explicitly downloaded: ' + voice)
        prompt = _VOICE_CACHE.get(('pocket',selected_model,voice_file,device))
        if prompt is None:
            prompt = tts.get_state_for_audio_prompt(voice_file)
            _VOICE_CACHE[('pocket',selected_model,voice_file,device)] = prompt
        samples = tts.generate_audio(prompt, text).detach().cpu().numpy()
        wavfile.write(str(output), tts.sample_rate, np.asarray(samples, dtype=np.float32))
    elif engine == 'coqui':
        from TTS.api import TTS
        model = model or 'tts_models/en/ljspeech/tacotron2-DDC'
        tts = _MODEL_CACHE.get(('coqui',model,device))
        if tts is None:
            try:
                tts = TTS(model).to(device)
            except (RuntimeError, ValueError, OSError):
                if device == 'cpu':
                    raise
                tts = TTS(model).to('cpu')
            _MODEL_CACHE[('coqui',model,device)] = tts
        kwargs = {'text':text, 'file_path':str(output)}
        available_speakers = list(getattr(tts, 'speakers', None) or [])
        available_languages = list(getattr(tts, 'languages', None) or [])
        if available_speakers:
            selected = voice or available_speakers[0]
            if selected not in available_speakers:
                raise ValueError(f'Invalid Coqui speaker {selected!r}; try {available_speakers[:12]}')
            kwargs['speaker'] = selected
        elif voice:
            raise ValueError('The selected Coqui model is single-speaker; leave Voice empty.')
        if available_languages:
            language = payload.get('language', 'en')
            if language in ('','auto','und'):
                language = 'en'
            if language not in available_languages:
                language = available_languages[0]
            kwargs['language'] = language
        tts.tts_to_file(**kwargs)
    else:
        raise ValueError('Unknown neural engine: ' + str(engine))
    if not output.is_file() or output.stat().st_size <= 44:
        raise RuntimeError(f'{engine} did not create a valid WAV file')


def download_assets(payload):
    """Called only in the dedicated, GUI-confirmed network-enabled subprocess."""
    if os.environ.get('OPENMUKTI_NEURAL_DOWNLOAD') != '1':
        raise PermissionError('Neural downloads require an explicit GUI download operation.')
    engine = payload['engine']
    voice = payload.get('voice', '')
    model = payload.get('model', '')
    if engine == 'kokoro':
        from huggingface_hub import hf_hub_download
        if model != 'hexgrad/Kokoro-82M':
            raise ValueError('Unsupported Kokoro model repository: ' + model)
        if not voice or not voice.replace('_', '').isalnum():
            raise ValueError('Choose a valid Kokoro voice first')
        for filename in ('config.json', 'kokoro-v1_0.pth', f'voices/{voice}.pt'):
            hf_hub_download(repo_id=model, filename=filename)
        # Prepare language-specific G2P assets while downloads are permitted.
        from kokoro import KPipeline
        pipeline = KPipeline(lang_code=voice[0], device='cpu', repo_id=model)
        pipeline.load_single_voice(voice)
    elif engine == 'kitten':
        from kittentts import KittenTTS
        tts = KittenTTS(model)
        if voice and voice not in (getattr(tts, 'available_voices', ()) or ()):
            raise ValueError('Unknown KittenTTS voice: ' + voice)
    elif engine == 'pocket':
        from pocket_tts import TTSModel
        from pocket_tts import export_model_state
        tts = TTSModel.load_model(language=model)
        prompt = tts.get_state_for_audio_prompt(voice)
        voice_path = Path(payload['voice_state_path'])
        voice_path.parent.mkdir(parents=True, exist_ok=True)
        # A locally stored voice state avoids re-fetching remote sample audio.
        export_model_state(prompt, voice_path)
        if not voice_path.is_file() or voice_path.stat().st_size <= 0:
            raise RuntimeError('Pocket did not save the requested voice state')
    elif engine == 'coqui':
        from TTS.api import TTS
        # Model downloads can be large and some licenses have separate terms.
        # The caller must explicitly approve this selected model in the GUI.
        TTS(model).to('cpu')
    else:
        raise ValueError('Unknown neural engine: ' + str(engine))
    return {'engine':engine, 'model':model, 'voice':voice}


def forbid_network():
    """Block network sockets in workers used for ordinary synthesis/discovery.

    Library-level offline flags alone do not cover Coqui and URL voice presets.
    """
    import socket
    def blocked(*_args, **_kwargs):
        raise OSError('Model network access is disabled. Download voices in the Openmukti GUI first.')
    socket.socket.connect = blocked
    socket.socket.connect_ex = blocked
    socket.create_connection = blocked


def process(payload):
    if payload.get('action') == 'download':
        return download_assets(payload)
    if os.environ.get('OPENMUKTI_NEURAL_DOWNLOAD') == '1':
        raise PermissionError('Download workers do not synthesize audio or discover speakers.')
    if payload.get('action') == 'voices':
        if payload.get('engine') != 'coqui':
            raise ValueError('Only Coqui discovers speakers by model')
        from TTS.api import TTS
        model = payload.get('model') or 'tts_models/en/ljspeech/tacotron2-DDC'
        device = _preferred_torch_device()
        tts = _MODEL_CACHE.get(('coqui',model,device))
        if tts is None:
            device = _preferred_torch_device()
            try:
                tts = TTS(model).to(device)
            except (RuntimeError, ValueError, OSError):
                if device == 'cpu':
                    raise
                tts = TTS(model).to('cpu')
            _MODEL_CACHE[('coqui',model,device)] = tts
        return {'voices': list(getattr(tts, 'speakers', ()) or ())}
    synthesize(payload)
    return {}


def _protocol_output():
    """Reserve the pipe for JSON before libraries can write to native fd 1.

    contextlib.redirect_stdout only catches Python's ``print``.  Many TTS,
    PyTorch, tokenizer and model-download dependencies use native writes or
    subprocesses, which can emit non-JSON text directly to stdout.  Keep a
    duplicate of the original pipe for protocol messages, then redirect the
    process-level stdout descriptor to stderr (the parent's worker.log).
    """
    try:
        sys.stdout.flush()
        protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w',
                             encoding='utf-8', buffering=1)
        try:
            os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        except (OSError, ValueError, AttributeError):
            protocol.close()
            raise
        return protocol
    except (OSError, ValueError, AttributeError):
        # In unusual embedded/testing contexts where descriptors are not
        # available, Python-level logging is still redirected below.
        return sys.stdout


def main():
    import contextlib
    import traceback
    protocol = _protocol_output()
    if os.environ.get('OPENMUKTI_NEURAL_DOWNLOAD') != '1':
        forbid_network()
    # Only the duplicated protocol fd may write to the parent's JSON pipe.
    # All Python/native-library/subprocess chatter goes to worker.log.
    try:
        for raw in sys.stdin:
            try:
                request = json.loads(raw)
                with contextlib.redirect_stdout(sys.stderr):
                    result = process(request)
                response = {'ok':True, **result}
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                response = {'ok':False,'error':str(exc)}
            protocol.write(json.dumps(response, ensure_ascii=False) + '\n')
            protocol.flush()
    finally:
        if protocol is not sys.stdout:
            protocol.close()


if __name__ == '__main__':
    main()
