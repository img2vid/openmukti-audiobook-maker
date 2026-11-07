"""Acquire and validate the Windows FriBiDi runtime needed by Pillow's RAQM.

Pillow's official Windows wheels use a vendored libraqm that loads FriBiDi
separately at runtime. The build must supply it *before* importing PIL's
FreeType extension; merely collecting pillow.libs does not fix this.

The binary archives below come from the official MSYS2 package repository.
The SHA256 values are pinned to the exact published 1.0.17-1 artifacts.
Only one approved native DLL and its license are extracted; no executables
or files from the package are installed or executed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

PACKAGES = {
    'x86_64': {
        'url': 'https://mirror.msys2.org/mingw/mingw64/mingw-w64-x86_64-fribidi-1.0.17-1-any.pkg.tar.zst',
        'sha256': '707f6a2f9a49c83938271bfd92a11f80bd4c18c4837210173fcb39e9d841e5ac',
        'prefix': 'mingw64',
        'machine': 0x8664,
    },
    'aarch64': {
        'url': 'https://mirror.msys2.org/mingw/clangarm64/mingw-w64-clang-aarch64-fribidi-1.0.17-1-any.pkg.tar.zst',
        'sha256': '85e3a9d74124676618081c2d8a57548342d83a76ac8e4f7daaa0263d0caecbef',
        'prefix': 'clangarm64',
        'machine': 0xaa64,
    },
}


def file_sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _pe_machine(path: Path) -> int:
    with path.open('rb') as stream:
        if stream.read(2) != b'MZ':
            raise ValueError('FriBiDi file is not a Windows PE DLL')
        stream.seek(0x3c)
        offset = int.from_bytes(stream.read(4), 'little')
        if not 0x40 <= offset < 1024 * 1024:
            raise ValueError('Invalid FriBiDi PE header offset')
        stream.seek(offset)
        if stream.read(4) != b'PE\0\0':
            raise ValueError('FriBiDi PE signature is missing')
        return int.from_bytes(stream.read(2), 'little')


def _download(url: str, target: Path, expected_sha256: str):
    temporary = target.with_suffix(target.suffix + '.partial')
    try:
        with urllib.request.urlopen(urllib.request.Request(
                url, headers={'User-Agent': 'Openmukti-Windows-Builder/1.0'}), timeout=90) as response, \
                temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        observed = file_sha256(temporary)
        if observed != expected_sha256:
            raise ValueError('MSYS2 FriBiDi archive SHA256 mismatch; refusing the download. '
                             f'Expected {expected_sha256}, received {observed}')
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _zstd_stream(archive: Path):
    # Python 3.14+ has a standard-library Zstandard decoder. Python 3.10-3.13
    # can use the small build-only zstandard dependency installed by build.py.
    try:
        from compression import zstd
    except ImportError:
        try:
            import zstandard as zstd
        except ImportError as exc:
            raise RuntimeError('Zstandard decompression is required to unpack the trusted '
                               'FriBiDi DLL; install zstandard in the build environment') from exc
    return zstd.open(archive, 'rb')


def _extract(archive: Path, folder: Path, package: dict):
    wanted = {
        f"{package['prefix']}/bin/libfribidi-0.dll": 'libfribidi-0.dll',
        f"{package['prefix']}/share/licenses/fribidi/COPYING": 'FRIBIDI-LICENSE.txt',
    }
    collected: dict[str, bytes] = {}
    with _zstd_stream(archive) as decompressed:
        with tarfile.open(fileobj=decompressed, mode='r|') as contents:
            for member in contents:
                name = member.name.removeprefix('./')
                if name not in wanted:
                    continue
                if not member.isfile() or member.size > 2_000_000:
                    raise ValueError('FriBiDi archive contains an unexpected DLL/license entry')
                source = contents.extractfile(member)
                if source is None:
                    raise ValueError(f'Could not extract {name}')
                collected[wanted[name]] = source.read(2_000_001)
    if set(collected) != set(wanted.values()):
        raise ValueError('The verified MSYS2 archive did not contain the expected DLL and license')
    folder.mkdir(parents=True, exist_ok=True)
    for filename, data in collected.items():
        if not data:
            raise ValueError(f'Empty FriBiDi package entry: {filename}')
        path = folder / filename
        temporary = path.with_suffix(path.suffix + '.partial')
        temporary.write_bytes(data)
        temporary.replace(path)


def prepare(architecture: str, root: Path) -> Path:
    """Return native FriBiDi DLL, only after hash and PE verification.

    `root` is the ignored .build-assets/text-layout directory. An unchanged
    verified archive works offline on later --repair runs.
    """
    if architecture not in PACKAGES:
        raise ValueError(f'Unsupported FriBiDi Windows architecture: {architecture}')
    package = PACKAGES[architecture]
    folder = Path(root).resolve() / architecture
    folder.mkdir(parents=True, exist_ok=True)
    archive = folder / 'fribidi-1.0.17-1.pkg.tar.zst'
    if archive.is_file() and file_sha256(archive) != package['sha256']:
        archive.unlink()  # stale or damaged cache is not a trustworthy source
    if not archive.is_file():
        try:
            _download(package['url'], archive, package['sha256'])
        except Exception as exc:
            raise RuntimeError('Unable to download/verify the required FriBiDi Windows DLL '
                               f'from the official MSYS2 mirror ({package["url"]}). '
                               'Internet access is needed on the first build; '
                               'use --repair to reuse downloaded files.') from exc
    dll = folder / 'libfribidi-0.dll'
    license_file = folder / 'FRIBIDI-LICENSE.txt'
    if not dll.is_file() or not license_file.is_file():
        _extract(archive, folder, package)
    if _pe_machine(dll) != package['machine']:
        # A corrupted cache must not be frozen into an otherwise valid EXE.
        dll.unlink(missing_ok=True)
        raise RuntimeError(f'FriBiDi DLL has the wrong PE architecture for {architecture}')
    if not license_file.stat().st_size:
        raise RuntimeError('FriBiDi license is missing')
    marker = folder / 'source.json'
    marker.write_text(json.dumps({
        'source_url': package['url'], 'archive_sha256': package['sha256'],
        'dll_sha256': file_sha256(dll), 'license': 'LGPL-2.1-or-later',
        'architecture': architecture,
    }, indent=2) + '\n', encoding='utf-8')
    return dll


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Verify and stage the official Windows FriBiDi DLL')
    parser.add_argument('architecture', choices=sorted(PACKAGES))
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print('Ready:', prepare(args.architecture, args.root), flush=True)
