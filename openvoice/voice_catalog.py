from __future__ import annotations
import hashlib
import sqlite3
from contextlib import closing
from functools import lru_cache
import json
import os
import re
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from .piper_models import voice_directory

CATALOG_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json'
VOICE_BASE_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/'
MAX_CATALOG_BYTES = 4_000_000

@dataclass(frozen=True)
class CatalogVoice:
    key: str
    language: str
    language_name: str
    region: str
    quality: str
    speakers: int
    model_path: str
    config_path: str
    model_bytes: int
    model_md5: str
    config_bytes: int
    config_md5: str

def parse_catalog(data: dict) -> list[CatalogVoice]:
    if not isinstance(data, dict):
        raise ValueError('Voice catalog is not a JSON object')
    output = []
    for key, record in data.items():
        if not isinstance(record, dict) or not isinstance(record.get('files'), dict):
            continue
        paths = record['files']
        model = next((p for p in paths if p.endswith('.onnx')), None)
        config = model + '.json' if model else None
        if not model or config not in paths or not re.fullmatch(r'[\w.-]+', key):
            continue
        if any(not _safe_path(x) for x in (model, config)):
            continue
        lang = record.get('language', {})
        if not isinstance(lang, dict):
            lang = {}
        m, c = paths[model], paths[config]
        try:
            output.append(CatalogVoice(key, str(lang.get('code', '')).replace('_', '-'), str(lang.get('name_english', 'Unknown')),
                                       str(lang.get('country_english', '')), str(record.get('quality', 'unknown')),
                                       max(1, int(record.get('num_speakers', 1))), model, config,
                                       int(m['size_bytes']), str(m['md5_digest']).lower(),
                                       int(c['size_bytes']), str(c['md5_digest']).lower()))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(output, key=lambda v: (v.language_name.casefold(), v.language, v.key))

def _safe_path(path: str) -> bool:
    parts = Path(path).parts
    return bool(parts) and not path.startswith('/') and '\\' not in path and all(part not in ('..', '.') for part in parts) and re.fullmatch(r'[\w./-]+', path) is not None

def catalog_cache() -> Path:
    return voice_directory().parent / 'piper-voices.json'

def fetch_catalog(*, force: bool = False, cache: Path | None = None, opener=None, max_age: int=7*86400) -> list[CatalogVoice]:
    cache = cache or catalog_cache()
    if not force and cache.is_file() and time.time() - cache.stat().st_mtime < max_age:
        try:
            return parse_catalog(json.loads(cache.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            pass
    from .desktop_prefs import authorized
    authorized('network')
    fetch = opener or urllib.request.urlopen
    try:
        with fetch(urllib.request.Request(CATALOG_URL, headers={'User-Agent':'Openmukti-Audiobook-Maker/1.0'}), timeout=30) as response:
            raw = response.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            raise ValueError('Catalog is unexpectedly large')
        data = json.loads(raw.decode('utf-8'))
        voices = parse_catalog(data)
        if not voices:
            raise ValueError('The online voice catalog contained no usable models')
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix('.download')
        temporary.write_bytes(raw)
        os.replace(temporary, cache)
        return voices
    except (OSError, ValueError, UnicodeError) as exc:
        if cache.is_file():
            try:
                voices = parse_catalog(json.loads(cache.read_text(encoding='utf-8')))
                if voices:
                    return voices
            except (OSError, ValueError):
                pass
        raise RuntimeError(f'Unable to load Piper voice catalog: {exc}') from exc

def catalog_languages(voices: list[CatalogVoice]) -> list[str]:
    return sorted({f'{v.language_name} ({v.language})' for v in voices})

def voice_download_size(voices: list[CatalogVoice]) -> int:
    return sum(v.model_bytes + v.config_bytes for v in voices)

def _download_verified(url: str, path: Path, size: int, digest: str, opener=None, progress=None) -> None:
    if size < 1 or size > 4_000_000_000 or not re.fullmatch(r'[0-9a-f]{32}', digest):
        raise ValueError('Missing or invalid catalog checksum or size')
    from .desktop_prefs import authorized
    authorized('network')
    fetch = opener or urllib.request.urlopen
    offset = path.stat().st_size if path.is_file() else 0
    if offset == size and _cached_md5(*_stamp(path)) == digest:
        if progress: progress(size,size)
        return
    if offset >= size:
        path.unlink(missing_ok=True)
        offset=0
    headers={'User-Agent':'Openmukti-Audiobook-Maker/1.0'}
    if offset:
        headers['Range']=f'bytes={offset}-'
    with fetch(urllib.request.Request(url,headers=headers),timeout=90) as response:
        status=getattr(response,'status',200)
        if status==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
            if not match or int(match[1])!=offset or int(match[3])!=size or int(match[2])!=size-1:
                raise ValueError('Server returned an inconsistent byte range')
        elif status==200:
            offset=0
        else:
            raise ValueError(f'Unexpected download response {status}')
        total=offset
        with path.open('ab' if offset else 'wb') as dest:
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>size:
                    dest.close();path.unlink(missing_ok=True)
                    raise ValueError('Downloaded file exceeds catalog size')
                dest.write(chunk)
                if progress: progress(total,size)
    if total!=size:
        raise ValueError('Download interrupted. Retry to resume this model')
    if _cached_md5(*_stamp(path))!=digest:
        path.unlink(missing_ok=True)
        raise ValueError('Downloaded file failed catalog size/checksum verification')


def _stamp(path):
    stat=path.stat()
    return str(path.resolve()),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


@lru_cache(maxsize=512)
def _cached_md5(path,size,modified,changed):
    digest=hashlib.md5()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def download_voice(voice: CatalogVoice, *, destination: Path | None=None, opener=None, progress=None) -> Path:
    destination=destination or voice_directory()
    if not re.fullmatch(r'[\w.-]+',voice.key) or not all(_safe_path(p) for p in (voice.model_path,voice.config_path)):
        raise ValueError('Invalid voice catalog entry')
    cache=destination/'.download-cache'
    cache.mkdir(parents=True,exist_ok=True)
    tasks=[(voice.model_path,destination/(voice.key+'.onnx'),voice.model_bytes,voice.model_md5),
           (voice.config_path,destination/(voice.key+'.onnx.json'),voice.config_bytes,voice.config_md5)]
    # SQLite releases this per-model lock even if the downloader process crashes.
    with closing(sqlite3.connect(cache/(voice.key+'.sqlite3'),timeout=120)) as lock:
        lock.execute('BEGIN IMMEDIATE')
        staged=[]
        completed=0
        for remote,target,size,digest in tasks:
            if not re.fullmatch('[0-9a-f]{32}',digest): raise ValueError('Invalid model checksum')
            total=voice.model_bytes+voice.config_bytes
            if target.is_file() and target.stat().st_size==size and _cached_md5(*_stamp(target))==digest:
                if progress: progress(completed+size,total)
            else:
                part=cache/(voice.key+'.'+digest+'.part')
                notify=(lambda done,_,offset=completed: progress(offset+done,total)) if progress else None
                _download_verified(VOICE_BASE_URL+urllib.parse.quote(remote,safe='/'),part,size,digest,opener,notify)
                staged.append((part,target))
            completed+=size
        # Make the model discoverable only after its verified config is in place.
        for part,target in reversed(staged):
            os.replace(part,target)
    return tasks[0][1]


def download_selected(voices: list[CatalogVoice], *, progress=None) -> list[Path]:
    paths = []
    for number, voice in enumerate(voices, 1):
        if progress:
            progress(number, len(voices), voice.key)
        paths.append(download_voice(voice))
    return paths

# The catalog is metadata only: reading it must never download ONNX weights.
# The GUI can display these entries before any voice has been installed.
import threading
from .piper_models import get_voice

_piper_download_locks_guard = threading.Lock()
_piper_download_locks: dict[str, threading.Lock] = {}


def cached_catalog(*, cache: Path | None = None) -> list[CatalogVoice]:
    """Read the locally cached official index without initiating a network request."""
    path = cache or catalog_cache()
    try:
        return parse_catalog(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError, UnicodeError):
        return []


def catalog_voice(name: str, *, allow_network: bool = False) -> CatalogVoice | None:
    """Look up a Piper model identifier, case-insensitively, using metadata only."""
    value = str(name or '').strip().casefold()
    if not value:
        return None
    voices = cached_catalog()
    match = next((v for v in voices if v.key.casefold() == value), None)
    if match or not allow_network:
        return match
    return next((v for v in fetch_catalog() if v.key.casefold() == value), None)


def installed_catalog_voice(voice: CatalogVoice, *, destination: Path | None = None) -> Path | None:
    """Check for both files before using a cached/downloaded model.

    Newly downloaded models are verified against published checksums by the
    downloader; checking sizes here avoids expensive rehashing on each phrase.
    """
    folder = destination or voice_directory()
    model = folder / (voice.key + '.onnx')
    config = folder / (voice.key + '.onnx.json')
    try:
        if (model.is_file() and config.is_file()
                and model.stat().st_size == voice.model_bytes
                and config.stat().st_size == voice.config_bytes
                and _cached_md5(*_stamp(model)) == voice.model_md5
                and _cached_md5(*_stamp(config)) == voice.config_md5):
            return model
    except OSError:
        pass
    return None


def ensure_piper_voice(name: str, *, report=None, control=None, progress=None) -> Path:
    """Resolve a selected installed/catalog Piper voice and download if needed.

    Safe to call concurrently from Speak, character preview, batch, and the
    GUI. Unknown identifiers and manually provided ONNX paths never trigger a
    guessed download. No Tk dialogs or network actions run until requested.
    """
    name = str(name or '').strip()
    if not name:
        raise ValueError('Choose a Piper voice from the Voice list.')
    # A manually specified external ONNX path is never a catalog download.
    if name.casefold().endswith('.onnx'):
        path = Path(name).expanduser()
        config = Path(str(path) + '.json')
        if not path.is_file() or not config.is_file():
            raise FileNotFoundError(f'Piper model or matching configuration not found: {path}')
        return path
    installed = get_voice(name)
    if installed is not None:
        return installed.model
    with _piper_download_locks_guard:
        lock = _piper_download_locks.setdefault(name.casefold(), threading.Lock())
    with lock:
        if control:
            control.check()
        installed = get_voice(name)
        if installed is not None:
            return installed.model
        item = catalog_voice(name, allow_network=True)
        if item is None:
            raise ValueError(f'Piper voice {name!r} does not exist in the official Piper catalog. '
                             'Check the spelling or add a local .onnx model.')
        if installed_catalog_voice(item):
            return voice_directory() / (item.key + '.onnx')
        if report:
            report(f'Downloading Piper voice {item.key}…')
        path = download_voice(item, progress=progress) if progress else download_voice(item)
        if control:
            control.check()
        if report:
            report(f'Piper voice ready: {item.key}')
        return path
