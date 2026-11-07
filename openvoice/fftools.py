from __future__ import annotations
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def architecture() -> str:
    name = platform.machine().lower()
    if name in ('amd64', 'x86_64', 'x64'):
        return 'x64'
    if name in ('aarch64', 'arm64'):
        return 'arm64'
    if name in ('i386', 'i686', 'x86'):
        return 'x86'
    return name


def family() -> str:
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform.startswith('linux'):
        return 'linux'
    if sys.platform == 'darwin':
        return 'macos'
    if sys.platform.startswith(('freebsd', 'openbsd', 'netbsd')):
        return 'bsd'
    return sys.platform


def bundled_locations() -> list[Path]:
    roots = []
    override = os.environ.get('OPENVOICE_FFMPEG_DIR', '').strip()
    if override:
        roots.append(Path(override).expanduser())
    if getattr(sys, '_MEIPASS', None):
        roots.append(Path(sys._MEIPASS))
    if getattr(sys, 'frozen', False):
        roots.append(Path(sys.executable).resolve().parent)
    if sys.argv and sys.argv[0].endswith('.pyz'):
        roots.append(Path(sys.argv[0]).resolve().parent)
    roots.append(Path(__file__).resolve().parent.parent)
    roots.append(Path(__file__).resolve().parent)
    roots.append(Path(sys.executable).resolve().parent)
    prefix = f'{family()}-{architecture()}'
    result = []
    for root in roots:
        for dirname in ('ffmpeg', 'bin', '', f'vendor/ffmpeg/{prefix}', 'vendor/ffmpeg'):
            candidate = root / dirname
            if candidate not in result:
                result.append(candidate)
    return result


def find_binary(name: str, allow_system: bool = True) -> str:
    if name not in ('ffmpeg', 'ffprobe'):
        raise ValueError('Only ffmpeg and ffprobe may be resolved')
    suffix = '.exe' if os.name == 'nt' else ''
    for folder in bundled_locations():
        candidate = folder / (name + suffix)
        if candidate.is_file() and (os.name == 'nt' or os.access(candidate, os.X_OK)):
            return str(candidate.resolve())
    return (shutil.which(name) or '') if allow_system else ''


def media_tools_status() -> dict:
    result = {}
    for name in ('ffmpeg', 'ffprobe'):
        found = find_binary(name)
        embedded = find_binary(name, allow_system=False)
        version = ''
        if found:
            try:
                output = subprocess.run([found, '-version'], capture_output=True, text=True, timeout=8, check=False)
                if output.returncode == 0:
                    version = output.stdout.splitlines()[0].strip()[:160]
            except (OSError, subprocess.TimeoutExpired):
                pass
        result[name] = {'available': bool(found), 'bundled': bool(embedded), 'path': found, 'version': version}
    return result
