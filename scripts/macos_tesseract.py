"""Isolate Tesseract's Homebrew dylibs from the PyInstaller OpenCV bundle.

PyInstaller may rebind the Tesseract executable to cv2/.dylibs/libtesseract,
which is not ABI compatible with the Homebrew executable on Apple Silicon.
Re-stage its dependency closure privately after freezing and re-sign binaries.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

_SYSTEM_ROOTS = ('/usr/lib/', '/System/Library/', '/Library/Apple/System/Library/')


def _otool(path: Path, option: str) -> str:
    return subprocess.check_output(['otool', option, str(path)], text=True)


def _linked_libraries(path: Path) -> list[str]:
    result = []
    for line in _otool(path, '-L').splitlines()[1:]:
        match = re.match(r'^\s+(\S+)\s+\(', line)
        if match:
            result.append(match.group(1))
    return result


def _rpaths(path: Path) -> list[str]:
    return re.findall(r'\bcmd LC_RPATH\b.*?\bpath\s+(.*?)\s+\(offset',
                      _otool(path, '-l'), re.S)


def _resolve_library(reference: str, owner: Path, executable: Path) -> Path:
    if reference.startswith(_SYSTEM_ROOTS):
        return Path(reference)
    if reference.startswith('/'):
        candidate = Path(reference)
        if candidate.is_file():
            return candidate.resolve()
    if reference.startswith('@loader_path/'):
        candidate = owner.parent / reference.removeprefix('@loader_path/')
        if candidate.is_file():
            return candidate.resolve()
    if reference.startswith('@executable_path/'):
        candidate = executable.parent / reference.removeprefix('@executable_path/')
        if candidate.is_file():
            return candidate.resolve()
    if reference.startswith('@rpath/'):
        name = reference.removeprefix('@rpath/')
        for entry in _rpaths(owner):
            root = entry.replace('@loader_path', str(owner.parent))
            root = root.replace('@executable_path', str(executable.parent))
            if root.startswith('/'):
                candidate = Path(root) / name
                if candidate.is_file():
                    return candidate.resolve()
        # Deliberately exclude the frozen cv2/.dylibs folder.
        for prefix in (Path('/opt/homebrew/opt'), Path('/usr/local/opt')):
            if prefix.is_dir():
                matches = sorted(prefix.glob('*/lib/' + name))
                if matches:
                    return matches[0].resolve()
    raise RuntimeError(f'Unable to stage Tesseract dependency {reference!r} from {owner}')


def isolate_tesseract(payload: Path, original: Path) -> Path:
    """Embed a private, re-linked Homebrew Tesseract executable and its dylibs."""
    original = Path(original).resolve()
    if not original.is_file():
        raise RuntimeError(f'Missing installed Tesseract executable: {original}')
    target = payload / '_internal' / 'tesseract' / 'tesseract'
    if not target.is_file():
        raise RuntimeError('PyInstaller did not include the Tesseract executable')
    private_libs = target.parent / 'lib'
    private_libs.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)

    queued = [(original, target, True)]
    seen: dict[str, Path] = {}
    edited: list[Path] = []
    while queued:
        source, destination, executable = queued.pop(0)
        replacements = []
        for dependency in _linked_libraries(source):
            if dependency.startswith(_SYSTEM_ROOTS):
                continue
            resolved = _resolve_library(dependency, source, original)
            if resolved == source.resolve():
                continue  # A dylib's own LC_ID_DYLIB, not a dependency.
            name = Path(dependency).name
            existing = seen.get(name)
            if existing is not None and existing != resolved:
                raise RuntimeError(f'Conflicting Tesseract dependency {name}: {existing} / {resolved}')
            if existing is None:
                seen[name] = resolved
                copy = private_libs / name
                shutil.copy2(resolved, copy)
                queued.append((resolved, copy, False))
            relative = ('@loader_path/lib/' if executable else '@loader_path/') + name
            replacements.append((dependency, relative))
        for old, new in replacements:
            subprocess.run(['install_name_tool', '-change', old, new, str(destination)], check=True)
        if not executable:
            subprocess.run(['install_name_tool', '-id',
                            '@loader_path/' + destination.name, str(destination)], check=True)
        edited.append(destination)

    for binary in edited:
        subprocess.run(['codesign', '--force', '--sign', '-', str(binary)], check=True)
    return target
