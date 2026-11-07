"""Explicit-download registry for CPU neural-model files.

No TTS model assets are retrieved by this module.  A GUI-confirmed download
runs via a separate neural worker and is recorded only after it succeeds.
Speech and speaker discovery require a matching completed download marker.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from .neural_runtime import (cache_home, NEURAL_ENGINES, DEFAULT_MODELS,
                             DEFAULT_VOICES, KOKORO_VOICES, KITTEN_VOICES,
                             POCKET_VOICES)

KITTEN_MODELS = (
    'KittenML/kitten-tts-nano-0.8',
    'KittenML/kitten-tts-micro-0.8',
    'KittenML/kitten-tts-mini-0.8',
)
POCKET_MODELS = (
    'english', 'english_18m_2026-10', 'english_7m_2026-10',
    'english_2m_2026-10', 'french', 'german', 'spanish',
    'portuguese', 'italian', 'dutch',
)
COQUI_MODELS = (
    'tts_models/en/ljspeech/tacotron2-DDC',
    'tts_models/en/vctk/vits',
    'tts_models/multilingual/multi-dataset/xtts_v2',
)
MODEL_OPTIONS = {
    'kokoro': ('hexgrad/Kokoro-82M',),
    'kitten': KITTEN_MODELS,
    'pocket': POCKET_MODELS,
    'coqui': COQUI_MODELS,
}
VOICE_OPTIONS = {
    'kokoro': KOKORO_VOICES,
    'kitten': KITTEN_VOICES,
    'pocket': POCKET_VOICES,
    'coqui': ('All speakers included with selected Coqui model',),
}
_POCKET_DEFAULTS = {
    'giovanni':'italian', 'lola':'spanish', 'juergen':'german',
    'rafael':'portuguese', 'estelle':'french',
}
_POCKET_LANG = {
    'en':'english', 'it':'italian', 'es':'spanish', 'de':'german',
    'fr':'french', 'pt':'portuguese', 'nl':'dutch',
}


def effective_model(engine: str, model: str = '', voice: str = '', language: str = '') -> str:
    if engine not in NEURAL_ENGINES:
        raise ValueError('Unknown engine: ' + engine)
    model = (model or '').strip()
    if model:
        return model
    if engine == 'pocket':
        lang = (language or '').lower().split('-')[0].split('_')[0]
        return _POCKET_LANG.get(lang) or _POCKET_DEFAULTS.get(voice) or 'english'
    return DEFAULT_MODELS[engine]


def effective_voice(engine: str, voice: str = '') -> str:
    if engine not in NEURAL_ENGINES:
        raise ValueError('Unknown engine: ' + engine)
    return (voice or '').strip() or DEFAULT_VOICES[engine]


def _record_voice(engine: str, voice: str) -> str:
    # Kitten's ONNX voicepack and all Coqui speakers ship with the whole model.
    return voice if engine in ('kokoro', 'pocket') else ''


def _key(engine: str, model: str, voice: str) -> dict:
    return {'engine':engine, 'model':model, 'voice':_record_voice(engine,voice)}


def marker_path(engine: str, model: str = '', voice: str = '', language: str = '') -> Path:
    model = effective_model(engine, model, voice, language)
    voice = effective_voice(engine, voice)
    key = _key(engine, model, voice)
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode('utf-8')).hexdigest()
    return cache_home() / 'approved-models' / engine / (digest + '.json')


def pocket_voice_state_path(model: str = '', voice: str = '', language: str = '') -> Path:
    """Local precomputed voice state (rather than a network preset URL)."""
    selected_voice = effective_voice('pocket', voice)
    selected_model = effective_model('pocket', model, selected_voice, language)
    digest = hashlib.sha256((selected_model + '\n' + selected_voice).encode('utf-8')).hexdigest()
    return cache_home() / 'models' / 'pocket-voices' / (digest + '.safetensors')


def is_downloaded(engine: str, model: str = '', voice: str = '', language: str = '') -> bool:
    path = marker_path(engine, model, voice, language)
    try:
        expected = _key(engine, effective_model(engine, model, voice, language),
                        effective_voice(engine, voice))
        record = json.loads(path.read_text(encoding='utf-8'))
        if record != expected:
            return False
        if engine == 'pocket':
            state = pocket_voice_state_path(model, voice, language)
            return state.is_file() and state.stat().st_size > 0
        return True
    except (OSError, UnicodeError, ValueError):
        return False


def require_downloaded(engine: str, model: str = '', voice: str = '', language: str = '') -> None:
    selected_model = effective_model(engine, model, voice, language)
    selected_voice = effective_voice(engine, voice)
    if not is_downloaded(engine, model, voice, language):
        what = f'{engine} model {selected_model!r}'
        if engine in ('kokoro', 'pocket'):
            what += f' / voice {selected_voice!r}'
        raise RuntimeError(f'{what} has not been downloaded through the voice manager. '
                           'Open Voices → Download Kokoro / Kitten / Pocket / Coqui voices, '
                           'choose the model and voice, then click Download Selected. '
                           'Preview/export will not download model files automatically.')


def mark_downloaded(engine: str, model: str = '', voice: str = '', language: str = '') -> Path:
    """Called ONLY after the explicit download worker returns successfully."""
    selected_model = effective_model(engine, model, voice, language)
    selected_voice = effective_voice(engine, voice)
    path = marker_path(engine, model, voice, language)
    record = _key(engine, selected_model, selected_voice)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.approved-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write('\n')
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return path


def model_environment(*, allow_network: bool = False) -> dict[str, str]:
    """The same controlled cache is used by confirmed downloads and inference."""
    if allow_network:
        from .desktop_prefs import authorized
        authorized('network')
    base = cache_home() / 'models'
    env = dict(os.environ)
    env['HF_HOME'] = str(base / 'huggingface')
    env['HF_HUB_CACHE'] = str(base / 'huggingface' / 'hub')
    env['TTS_HOME'] = str(base / 'coqui')
    env['XDG_CACHE_HOME'] = str(base / 'xdg-cache')
    env['OPENMUKTI_NEURAL_DOWNLOAD'] = '1' if allow_network else '0'
    env['HF_HUB_DISABLE_TELEMETRY'] = '1'
    if not allow_network:
        env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1')
    else:
        # Inference is offline; only a GUI-confirmed worker may opt back in.
        for key in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE'):
            env.pop(key, None)
    return env
