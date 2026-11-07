from __future__ import annotations
import os
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PiperVoice:
    name: str
    model: Path
    config: Path



@dataclass(frozen=True)
class PiperSpeaker:
    id: int
    name: str = ''

    @property
    def label(self) -> str:
        return f'Speaker {self.id}' + (f' — {self.name}' if self.name else '')


def speaker_list(model_or_voice: str | Path = '') -> list[PiperSpeaker]:
    """Read *all* speaker IDs and optional names from a Piper sidecar config.

    Paths work for external ONNX files as well as installed library voices.
    An unselected model has one generic speaker; missing configs for a selected
    model are an error (never silently hide its additional voices).
    """
    selection = str(model_or_voice or '').strip()
    if not selection:
        return [PiperSpeaker(0)]
    path = Path(selection).expanduser()
    if path.suffix.lower() != '.onnx':
        installed = get_voice(selection)
        if installed is None:
            raise ValueError(f'Piper model is not installed: {selection}')
        path = installed.model
    config = Path(str(path) + '.json')
    try:
        data = json.loads(config.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Cannot read Piper speaker metadata from {config}: {exc}') from exc
    if not isinstance(data, dict):
        raise ValueError(f'Invalid Piper speaker metadata in {config}: expected JSON object')
    raw_count = data.get('num_speakers', 1)
    if type(raw_count) is not int or not 1 <= raw_count <= 100000:
        raise ValueError(f'Invalid num_speakers in {config}: {raw_count!r}')
    name_map = data.get('speaker_id_map', {})
    if not isinstance(name_map, dict):
        raise ValueError(f'Invalid speaker_id_map in {config}: expected a JSON object')
    names = {}
    for name, identifier in name_map.items():
        if isinstance(name, str) and type(identifier) is int and 0 <= identifier < raw_count:
            names.setdefault(identifier, name)
    return [PiperSpeaker(i, names.get(i, '')) for i in range(raw_count)]


def speaker_label(speaker_id: int, model_or_voice: str | Path = '') -> str:
    return next((sp.label for sp in speaker_list(model_or_voice) if sp.id == speaker_id), f'Speaker {speaker_id}')


def speaker_id_from_label(label: str) -> int:
    """Accept UI labels and plain integer IDs, but not arbitrary names."""
    import re
    match = re.fullmatch(r'\s*(?:Speaker\s+)?(\d+)(?:\s+—\s+.*)?\s*', label, re.IGNORECASE)
    if not match:
        raise ValueError(f'Choose a valid Piper speaker from the list, got {label!r}')
    return int(match.group(1))


def voice_directory() -> Path:
    if os.name == 'nt':
        root = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming')
        return root / 'Openmukti Audiobook Maker' / 'voices'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Openmukti Audiobook Maker' / 'voices'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'openmukti-audiobook-maker' / 'voices'


def search_directories() -> list[Path]:
    explicit = [os.environ.get('OPENMUKTI_PIPER_VOICES', ''), os.environ.get('PIPER_VOICES_DIR', '')]
    paths = [Path(p).expanduser() for p in explicit if p]
    paths += [voice_directory(), Path(sys.executable).resolve().parent / 'voices', Path(__file__).resolve().parents[1] / 'voices']
    unique = []
    for p in paths:
        if p not in unique:
            unique.append(p)
    return unique


def discover_voices() -> list[PiperVoice]:
    found = {}
    for folder in search_directories():
        if not folder.is_dir():
            continue
        try:
            models = sorted(folder.rglob('*.onnx'))
        except OSError:
            continue
        for model in models[:1000]:
            config = Path(str(model) + '.json')
            if model.is_file() and config.is_file() and model.stat().st_size > 0:
                found.setdefault(model.stem.casefold(), PiperVoice(model.stem, model, config))
    return sorted(found.values(), key=lambda item: item.name.casefold())


def get_voice(name: str='') -> PiperVoice | None:
    voices = discover_voices()
    if not name:
        return voices[0] if voices else None
    return next((v for v in voices if v.name.casefold() == name.casefold()), None)


def piper_binary() -> str | None:
    suffix = '.exe' if os.name == 'nt' else ''
    for folder in [Path(sys.executable).resolve().parent, Path(__file__).resolve().parents[1] / 'vendor' / 'piper']:
        file = folder / ('piper' + suffix)
        if file.is_file():
            return str(file)
    return shutil.which('piper')


def install_voice(model: str | Path) -> PiperVoice:
    source = Path(model).expanduser().resolve()
    config = Path(str(source) + '.json')
    if source.suffix.lower() != '.onnx' or not source.is_file():
        raise ValueError('Choose a Piper .onnx model file')
    if not config.is_file():
        raise ValueError(f'The matching configuration is missing: {config.name}')
    target = voice_directory()
    target.mkdir(parents=True, exist_ok=True)
    dest = target / source.name
    if source != dest:
        shutil.copy2(source, dest)
        shutil.copy2(config, target / config.name)
    return PiperVoice(dest.stem, dest, target / config.name)
