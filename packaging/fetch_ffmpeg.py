from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_API = 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest'


def target_platform() -> tuple[str, str]:
    if os.name == 'nt':
        family = 'windows'
        arch = sysconfig.get_platform().lower()
        arch = 'arm64' if 'arm64' in arch else 'x64' if 'amd64' in arch else 'unsupported'
    elif sys.platform.startswith('linux'):
        family = 'linux'
        machine = platform.machine().lower()
        arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x64' if machine in ('amd64', 'x86_64') else 'unsupported'
    else:
        raise RuntimeError('Automatic FFmpeg vendor downloads currently support Windows and Linux x64/ARM64 only. Supply verified platform binaries manually on other systems.')
    if arch == 'unsupported':
        raise RuntimeError('No compatible prebuilt FFmpeg release for this Python architecture')
    return family, arch


def target_directory(family: str, arch: str, root: Path = ROOT) -> Path:
    return root / 'vendor' / 'ffmpeg' / f'{family}-{arch}'


def executable_names(family: str) -> tuple[str, str]:
    suffix = '.exe' if family == 'windows' else ''
    return 'ffmpeg' + suffix, 'ffprobe' + suffix


def valid_install(path: Path, family: str) -> bool:
    return all((path / name).is_file() and (family == 'windows' or os.access(path / name, os.X_OK)) for name in executable_names(family))


def asset_filename(family: str, arch: str) -> str:
    code = {'windows': 'win', 'linux': 'linux'}[family] + ('arm64' if arch == 'arm64' else '64')
    return f'ffmpeg-master-latest-{code}-gpl' + ('.zip' if family == 'windows' else '.tar.xz')


def request_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Openmukti-Audiobook-Maker-Packager/1.0'})
    with urllib.request.urlopen(req, timeout=35) as stream:
        return json.load(stream)


def download_verified(url: str, destination: Path, sha256: str) -> None:
    if len(sha256) != 64 or any(c not in '0123456789abcdef' for c in sha256.lower()):
        raise ValueError('An authoritative SHA-256 checksum is required')
    digest = hashlib.sha256()
    req = urllib.request.Request(url, headers={'User-Agent': 'Openmukti-Audiobook-Maker-Packager/1.0', 'Accept': 'application/octet-stream'})
    with urllib.request.urlopen(req, timeout=60) as response, destination.open('wb') as target:
        size = 0
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > 800 * 1024 * 1024:
                raise RuntimeError('FFmpeg download exceeds permitted archive size')
            digest.update(block)
            target.write(block)
    if digest.hexdigest().lower() != sha256.lower():
        destination.unlink(missing_ok=True)
        raise RuntimeError('Downloaded FFmpeg archive SHA-256 does not match the release metadata')


def install_from_archive(archive: Path, destination: Path, family: str, metadata: dict) -> Path:
    suffix = '.exe' if family == 'windows' else ''
    needed = {f'ffmpeg{suffix}', f'ffprobe{suffix}'}
    chosen = {}
    notices = []
    destination.mkdir(parents=True, exist_ok=True)
    if archive.name.lower().endswith('.zip'):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                norm = entry.filename.replace('\\', '/')
                basename = norm.rsplit('/', 1)[-1]
                if entry.is_dir() or '..' in norm.split('/') or norm.startswith('/'):
                    continue
                if basename in needed and '/bin/' in '/' + norm:
                    if entry.file_size > 600 * 1024 * 1024:
                        raise ValueError('Unexpectedly large binary in FFmpeg archive')
                    with source.open(entry) as inp, (destination / basename).open('wb') as out:
                        shutil.copyfileobj(inp, out, 1024 * 1024)
                    chosen[basename] = destination / basename
                elif basename.upper() in ('LICENSE', 'LICENSE.TXT', 'LICENSE.MD', 'COPYING.GPLV3', 'README.TXT') and entry.file_size < 1024 * 1024:
                    notices.append(('UPSTREAM-' + basename, source.read(entry)))
    elif archive.name.lower().endswith('.tar.xz'):
        with tarfile.open(archive, 'r:xz') as source:
            for entry in source:
                norm = entry.name.replace('\\', '/')
                basename = norm.rsplit('/', 1)[-1]
                if not entry.isfile() or '..' in norm.split('/') or norm.startswith('/'):
                    continue
                if basename in needed and '/bin/' in '/' + norm:
                    if entry.size > 600 * 1024 * 1024:
                        raise ValueError('Unexpectedly large binary in FFmpeg archive')
                    stream = source.extractfile(entry)
                    if stream is not None:
                        with stream, (destination / basename).open('wb') as out:
                            shutil.copyfileobj(stream, out, 1024 * 1024)
                        chosen[basename] = destination / basename
                elif basename.upper() in ('LICENSE', 'LICENSE.TXT', 'LICENSE.MD', 'COPYING.GPLV3', 'README.TXT') and entry.size < 1024 * 1024:
                    stream = source.extractfile(entry)
                    if stream is not None:
                        notices.append(('UPSTREAM-' + basename, stream.read()))
    else:
        raise ValueError('Unsupported FFmpeg download archive')
    if set(chosen) != needed:
        raise RuntimeError('FFmpeg archive is missing FFmpeg or FFprobe executables')
    for filename in chosen:
        if family != 'windows':
            (destination / filename).chmod(0o755)
    for name, data in notices:
        (destination / name).write_bytes(data)
    (destination / 'FFMPEG-ORIGIN.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    (destination / 'REDISTRIBUTION.txt').write_text(
        'FFmpeg and FFprobe are separate third-party projects and NOT MIT licensed.\n'
        'This automatic download uses a GPL-enabled build of FFmpeg.\n'
        'Before publicly distributing these binaries, satisfy GPL obligations including\n'
        'providing the complete corresponding source for the exact FFmpeg build and\n'
        'its GPL-covered linked components, required license texts, and notices.\n'
        'Upstream: https://ffmpeg.org/\n'
        'Build project: https://github.com/BtbN/FFmpeg-Builds\n'
        'FFmpeg licensing: https://ffmpeg.org/legal.html\n', encoding='utf-8')
    check_runtime = family != 'windows' or os.environ.get('OPENMUKTI_BUILD_VERIFY_RUNTIME') != '0'
    for tool in executable_names(family) if check_runtime else ():
        try:
            result = subprocess.run([str(destination / tool), '-version'], capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f'Bundled media tool could not start: {tool}') from e
        if result.returncode:
            raise RuntimeError(f'Bundled media tool failed its self-check: {tool}')
    return destination


def prepare(*, root: Path = ROOT, download: bool = True) -> Path:
    family, arch = target_platform()
    destination = target_directory(family, arch, root)
    if valid_install(destination, family):
        print(f'Integrated media tools found: {destination}', flush=True)
        return destination
    if not download:
        raise FileNotFoundError(f'FFmpeg and FFprobe not staged in {destination}')
    selected = asset_filename(family, arch)
    print(f'Downloading integrated FFmpeg and FFprobe: {selected}', flush=True)
    release = request_json(RELEASE_API)
    asset = next((a for a in release.get('assets', []) if a.get('name') == selected), None)
    if asset is None:
        raise RuntimeError(f'No verified binary named {selected} in the chosen FFmpeg release')
    digest = str(asset.get('digest', ''))
    if not digest.startswith('sha256:'):
        raise RuntimeError('GitHub did not provide an SHA-256 digest for this binary. No unverified download will be used.')
    metadata = {'release': RELEASE_API, 'asset': selected, 'sha256': digest[7:], 'source_url': 'https://github.com/FFmpeg/FFmpeg', 'binary_build_source': 'https://github.com/BtbN/FFmpeg-Builds', 'release_tag': release.get('tag_name', '')}
    with tempfile.TemporaryDirectory(prefix='openvoice-ffmpeg-') as directory:
        archive = Path(directory) / selected
        download_verified(str(asset['browser_download_url']), archive, digest[7:])
        install_from_archive(archive, destination, family, metadata)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description='Stage verified FFmpeg/FFprobe for standalone Openmukti Audiobook Maker builds')
    parser.add_argument('--no-download', action='store_true', help='Require binaries previously placed in vendor/ffmpeg')
    args = parser.parse_args()
    print(prepare(download=not args.no_download))


if __name__ == '__main__':
    main()
