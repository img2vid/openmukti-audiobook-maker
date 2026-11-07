"""Verified chunk storage shared by previews, chapter rendering and render workers."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import shutil
from contextlib import closing, contextmanager
from dataclasses import asdict
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from . import __version__


@lru_cache(maxsize=256)
def _digest_file(path, size, modified, changed):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def file_identity(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _digest_file(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def model_identity(engine, settings):
    from .piper_models import get_voice
    from .fftools import find_binary
    paths = []
    model = settings.model
    if engine.key == 'piper':
        if not (model and Path(model).is_file()):
            voice = get_voice(model or (settings.voice if not settings.voice.isdecimal() else ''))
            if voice:
                model = str(voice.model)
        if model and Path(model).is_file():
            paths += [model, model + '.json']
    elif model and Path(model).is_file():
        paths.append(model)
    if engine.key in ('kokoro', 'kitten', 'pocket', 'coqui'):
        from .neural_runtime import python_path
        from .neural_models import marker_path, model_environment, pocket_voice_state_path
        # Each confirmed installation has a registry record and isolated interpreter.
        python = python_path(engine.key)
        if python.is_file():
            paths.append(python)
        marker = marker_path(engine.key, model, settings.voice, settings.language)
        paths.append(marker)
        if engine.key == 'pocket':
            paths.append(pocket_voice_state_path(model, settings.voice, settings.language))
        env = model_environment()
        roots = [Path(env['TTS_HOME'])] if engine.key == 'coqui' else [Path(env['HF_HUB_CACHE'])]
        registry = [(str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime_ns)
                    for root in roots if root.is_dir() for p in sorted(root.rglob('*'))
                    if p.is_file() and not p.name.endswith(('.lock', '.incomplete'))]
    else:
        registry = {}
    binary = {'flite':'ffmpeg', 'espeak':'espeak-ng', 'macos':'say', 'piper':'piper'}.get(engine.key)
    resolved = find_binary(binary) if binary == 'ffmpeg' else shutil.which(binary) if binary else None
    if resolved:
        paths.append(resolved)
    try:
        engine_version = metadata.version(engine.__class__.__module__.split('.')[0])
    except metadata.PackageNotFoundError:
        engine_version = ''
    return [engine.key, engine.__class__.__module__, engine.__class__.__qualname__,
            engine_version, platform.platform(), __version__, os.getenv('OPENMUKTI_GPU_MODE', 'auto'),
            [(str(p), file_identity(p)) for p in paths if Path(p).is_file()], registry]


class ChunkStore:
    def __init__(self, folder):
        self.folder = Path(folder).expanduser()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.db = self.folder / 'speech-cache.sqlite3'
        self.identities = {}
        with self.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, digest TEXT, audio BLOB)')
        self.hits = 0

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.db, timeout=45)) as conn, conn:
            yield conn

    def render(self, renderer, unit, output, engine, settings, control=None, *, refresh=False):
        if control:
            control.check()
        settings_key = (type(engine), engine.key, settings)
        if settings_key not in self.identities:
            self.identities[settings_key] = model_identity(engine, settings)
        record = [2, asdict(unit), asdict(settings), self.identities[settings_key]]
        key = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
        if not refresh:
            with self.connect() as conn:
                row = conn.execute('SELECT digest,audio FROM chunks WHERE id=?', (key,)).fetchone()
            if row and hashlib.sha256(row[1]).hexdigest() == row[0]:
                Path(output).write_bytes(row[1])
                self.hits += 1
                return
        renderer(unit, output, engine, settings, control)
        data = Path(output).read_bytes()
        if len(data) <= 44 or data[:4] not in (b'RIFF', b'RF64') or data[8:12] != b'WAVE':
            raise ValueError('Speech engine returned an invalid WAV chunk')
        if control:
            control.check()
        with self.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO chunks VALUES (?,?,?)',
                         (key, hashlib.sha256(data).hexdigest(), data))


def renderer_for(options, renderer):
    lock=os.environ.get('OPENMUKTI_MODEL_LOCK')
    if lock:
        from .voice_assets import check_lock
        spec=json.loads(Path(lock).read_text(encoding='utf-8'))
        changed=check_lock((Path(lock).parent/spec['root']).resolve(),spec['files'])
        if changed:
            raise ValueError('Model version lock failed for '+changed[0]['path'])
    folder = options.cache_dir or os.environ.get('OPENMUKTI_RENDER_CACHE')
    if not folder:
        return renderer
    store = ChunkStore(folder)
    from functools import partial
    return partial(store.render, renderer, refresh=options.refresh_cache)
