"""Offline Piper voice collection, tags, favorites, duplicate checks and portable packs.

Voice downloads are NEVER initiated by this module. Installation is explicit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .piper_models import discover_voices, voice_directory

SCHEMA = 'openmukti-voice-library'
PACK_SCHEMA = 'openmukti-voice-pack'
PACK_LIMIT = 8 * 1024 ** 3
MAX_MODELS = 500


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _model_name(name: str) -> str:
    if not re.fullmatch(r'[\w.+-]{1,160}', name, flags=re.UNICODE):
        raise ValueError('Invalid voice name')
    return name


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.openmukti-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def library_path() -> Path:
    return voice_directory() / 'voice-library.json'


class VoiceLibrary:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else library_path()
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('format') != SCHEMA or data.get('version') != 1:
                raise ValueError('Unsupported voice library metadata')
        else:
            data = {'format': SCHEMA, 'version': 1, 'voices': {}, 'collections': {}}
        self.voices: dict = data.get('voices', {})
        self.collections: dict = data.get('collections', {})
        if not isinstance(self.voices, dict) or not isinstance(self.collections, dict):
            raise ValueError('Invalid voice library metadata')

    def save(self) -> None:
        _atomic_json(self.path, {'format': SCHEMA, 'version': 1,
                                 'voices': self.voices, 'collections': self.collections})

    def set_favorite(self, name: str, enabled: bool) -> None:
        name = _model_name(name)
        record = self.voices.setdefault(name, {})
        record['favorite'] = bool(enabled)
        self.save()

    def set_tags(self, name: str, tags: list[str]) -> None:
        name = _model_name(name)
        normalized = sorted({t.strip().casefold() for t in tags if t.strip()})
        if len(normalized) > 50 or any(len(tag) > 80 for tag in normalized):
            raise ValueError('Voice tags exceed size limits')
        record = self.voices.setdefault(name, {})
        record['tags'] = normalized
        self.save()

    def set_collection(self, name: str, models: list[str]) -> None:
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError('Invalid collection name')
        if len(models) > MAX_MODELS:
            raise ValueError('Collection is too large')
        self.collections[name.strip()] = list(dict.fromkeys(_model_name(x) for x in models))
        self.save()

    def list_voices(self, *, favorites_only: bool = False, tag: str = '') -> list[dict]:
        result = []
        for voice in discover_voices():
            record = self.voices.get(voice.name, {})
            tags = record.get('tags', [])
            favorite = bool(record.get('favorite', False))
            if (favorites_only and not favorite) or (tag and tag.casefold() not in tags):
                continue
            result.append({'name': voice.name, 'model': str(voice.model),
                           'bytes': voice.model.stat().st_size,
                           'favorite': favorite, 'tags': tags})
        return result


def duplicate_models(roots: list[str | Path] | None = None) -> list[list[dict[str, Any]]]:
    from .piper_models import search_directories
    root_paths = [Path(p) for p in (roots if roots is not None else search_directories())]
    seen_paths: set[Path] = set()
    groups: dict[tuple[int, str], list[dict]] = {}
    for root in root_paths:
        if not root.is_dir():
            continue
        for path in root.rglob('*.onnx'):
            resolved = path.resolve()
            if resolved in seen_paths or not path.is_file():
                continue
            seen_paths.add(resolved)
            try:
                size = path.stat().st_size
                if size <= 0:
                    continue
                digest = _sha(path)
            except OSError:
                continue
            groups.setdefault((size, digest), []).append({'path': str(resolved), 'bytes': size, 'sha256': digest})
    return [group for group in groups.values() if len(group) > 1]


def export_voice_pack(destination: str | Path, names: list[str]) -> Path:
    """Package explicitly selected installed Piper model/config pairs with checksums."""
    by_name = {voice.name: voice for voice in discover_voices()}
    if not names or len(names) > MAX_MODELS:
        raise ValueError('Select between 1 and 500 installed voices')
    names = list(dict.fromkeys(_model_name(n) for n in names))
    resources = []
    total = 0
    for name in names:
        voice = by_name.get(name)
        if not voice:
            raise ValueError(f'Voice is not installed: {name}')
        for kind, path in [('model', voice.model), ('config', voice.config)]:
            size = path.stat().st_size
            total += size
            if total > PACK_LIMIT:
                raise ValueError('Voice pack exceeds the 8 GiB safety limit')
            resources.append({'name': name, 'kind': kind, 'archive': f'voices/{name}.onnx' + ('.json' if kind == 'config' else ''),
                              'sha256': _sha(path), 'bytes': size, 'file': path})
    dest = Path(destination).expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=dest.parent, prefix='.openmukti-pack-', suffix='.zip')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', allowZip64=True) as zipped:
            manifest = {'format': PACK_SCHEMA, 'version': 1, 'resources': [
                {key: row[key] for key in ('name', 'kind', 'archive', 'sha256', 'bytes')} for row in resources]}
            zipped.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
            for resource in resources:
                zipped.write(resource['file'], resource['archive'], compress_type=zipfile.ZIP_STORED)
        os.replace(temp, dest)
    finally:
        Path(temp).unlink(missing_ok=True)
    return dest


def import_voice_pack(source: str | Path, *, target: str | Path | None = None, overwrite: bool = False) -> list[Path]:
    """Verify the entire archive BEFORE installing; never follow untrusted ZIP paths."""
    dest = Path(target) if target is not None else voice_directory()
    source = Path(source)
    installed = []
    with zipfile.ZipFile(source) as pack:
        names = pack.namelist()
        if names.count('manifest.json') != 1 or len(names) != len(set(names)) or len(names) > 2 * MAX_MODELS + 1:
            raise ValueError('Malformed voice pack entries')
        manifest_info = pack.getinfo('manifest.json')
        if manifest_info.file_size > 1024 * 1024:
            raise ValueError('Voice pack manifest too large')
        manifest = json.loads(pack.read('manifest.json'))
        if manifest.get('format') != PACK_SCHEMA or manifest.get('version') != 1:
            raise ValueError('Not a supported Openmukti voice pack')
        resources = manifest.get('resources')
        if not isinstance(resources, list) or len(resources) > 2 * MAX_MODELS:
            raise ValueError('Invalid voice resource list')
        if set(names) != {'manifest.json'} | {x.get('archive') for x in resources if isinstance(x, dict)}:
            raise ValueError('Unexpected or missing voice files')
        if sum(info.file_size for info in pack.infolist()) > PACK_LIMIT:
            raise ValueError('Voice pack exceeds safety size limit')
        pairs: dict[str, set[str]] = {}
        for entry in resources:
            name, kind = _model_name(entry['name']), entry['kind']
            if kind not in ('model', 'config'):
                raise ValueError('Unknown voice file kind')
            archive = f'voices/{name}.onnx' + ('.json' if kind == 'config' else '')
            if entry['archive'] != archive or pack.getinfo(archive).file_size != entry['bytes']:
                raise ValueError('Unsafe or incorrect voice resource')
            if not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
                raise ValueError('Missing SHA-256 verification data')
            pairs.setdefault(name, set()).add(kind)
        if any(kinds != {'model', 'config'} for kinds in pairs.values()):
            raise ValueError('Every Piper model needs its corresponding JSON configuration')
        dest.mkdir(parents=True, exist_ok=True)
        if not overwrite:
            occupied = [str(dest / Path(e['archive']).name) for e in resources if (dest / Path(e['archive']).name).exists()]
            if occupied:
                raise FileExistsError('Voice pack would overwrite installed voices: ' + ', '.join(occupied))
        # Extract and checksum ALL files into a private staging folder, then install.
        with tempfile.TemporaryDirectory(prefix='.openmukti-voices-', dir=dest) as stage:
            staged = []
            for entry in resources:
                path = Path(stage) / Path(entry['archive']).name
                digest = hashlib.sha256()
                with pack.open(entry['archive']) as inp, path.open('wb') as out:
                    for block in iter(lambda: inp.read(1024 * 1024), b''):
                        digest.update(block)
                        out.write(block)
                if digest.hexdigest() != entry['sha256']:
                    raise ValueError('Voice pack checksum mismatch: ' + entry['archive'])
                if entry['kind'] == 'config':
                    info = json.loads(path.read_text(encoding='utf-8'))
                    if not isinstance(info, dict):
                        raise ValueError('Invalid Piper voice configuration JSON')
                staged.append(path)
            for stagefile in staged:
                final = dest / stagefile.name
                os.replace(stagefile, final)
                installed.append(final)
    return installed
