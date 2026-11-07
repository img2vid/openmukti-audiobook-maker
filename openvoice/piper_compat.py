from __future__ import annotations
from .acceleration import load_voice
import importlib.util
import json
import wave
from pathlib import Path
from .engines.base import EngineError


def inspect_config(path: str | Path) -> tuple[dict, dict[str, list[str]]]:
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EngineError(f'Piper voice configuration is unreadable: {path}. Download the matching .onnx.json again. Details: {exc}') from exc
    if not isinstance(config, dict):
        raise EngineError('Piper voice configuration must be a JSON object.')
    problems = {}
    for name in ('phoneme_id_map', 'phoneme_map'):
        mapping = config.get(name, {})
        if not isinstance(mapping, dict):
            raise EngineError(f'Invalid Piper configuration: {name} is not a map.')
        invalid = [key for key in mapping if len(key) != 1]
        if name == 'phoneme_map':
            invalid += [token for values in mapping.values() if isinstance(values, list) for token in values if not isinstance(token, str) or len(token) != 1]
        if invalid:
            problems[name] = invalid
    inference = config.get('inference', {})
    if isinstance(inference, dict):
        silence = inference.get('phoneme_silence', {})
        if isinstance(silence, dict):
            invalid = [key for key in silence if len(key) != 1]
            if invalid:
                problems['phoneme_silence'] = invalid
    return config, problems


def compatible_cli_config(config: dict, problems: dict[str, list[str]]) -> dict | None:
    if not problems:
        return None
    original_ids = config.get('phoneme_id_map')
    if not isinstance(original_ids, dict):
        return None
    ids = {key: value for key, value in original_ids.items() if len(key) == 1}
    if not ids:
        return None
    repaired = dict(config)
    repaired['phoneme_id_map'] = ids
    original_map = config.get('phoneme_map')
    if isinstance(original_map, dict):
        repaired['phoneme_map'] = {
            key: [token for token in values if isinstance(token, str) and len(token) == 1]
            for key, values in original_map.items()
            if len(key) == 1 and isinstance(values, list)
        }
    inference = config.get('inference')
    if isinstance(inference, dict) and isinstance(inference.get('phoneme_silence'), dict):
        repaired['inference'] = dict(inference)
        repaired['inference']['phoneme_silence'] = {key: value for key, value in inference['phoneme_silence'].items() if len(key) == 1}
    return repaired


def python_piper_available() -> bool:
    from .piper_sidecar import find_worker
    if find_worker() is not None:
        return True
    try:
        return importlib.util.find_spec('piper.voice') is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def render_python_piper(text: str, model: Path, config: Path, output: Path, length_scale: float, speaker_id: int | None = None) -> None:
    try:
        from piper.voice import PiperVoice
    except ImportError:
        from .piper_sidecar import render_with_worker, PiperSidecarError
        try:
            render_with_worker(mode='text', model=model, config=config, output=output,
                               text=text, length_scale=length_scale, speaker_id=speaker_id)
        except PiperSidecarError as exc:
            raise EngineError(str(exc)) from exc
        return
    try:
        voice = load_voice(PiperVoice, model, config)
        with wave.open(str(output), 'wb') as audio:
            if hasattr(voice, 'phoneme_ids_to_audio'):
                from piper.config import SynthesisConfig
                voice.synthesize_wav(text, audio, syn_config=SynthesisConfig(length_scale=length_scale, speaker_id=speaker_id))
            else:
                args = {'length_scale': length_scale}
                if speaker_id is not None:
                    args['speaker_id'] = speaker_id
                voice.synthesize_wav(text, audio, **args)
    except Exception as exc:
        raise EngineError(f'Piper Python compatibility backend failed for {model.name}: {exc}') from exc


def incompatibility_message(model: Path, problems: dict[str, list[str]]) -> str:
    sample = next(iter(problems.values()))[:4]
    return (f'Piper voice configuration is incompatible with the installed legacy Piper executable: {model.name}. '
            f'Non-single-codepoint phoneme keys: {", ".join(repr(x) for x in sample)}. '
            'This is a voice/runtime compatibility problem, not an error in the text. '
            'For this voice, install the Python Piper backend using "python -m pip install piper-tts" '
            'and run the Python application, or select a voice with a compatible configuration. '
            'For portable Windows EXEs, rebuild with the optional Piper Python backend included. '
            'Original model files have not been changed.')
