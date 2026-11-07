"""Verify GitHub Actions artifacts and stage packages for GitHub Releases.

Keep output files under the 2 GiB release-asset limit; checksum every part.
Only native packages and verifiable distributions from successful jobs are used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

EXPECTED_ARTIFACTS = (
    'Openmukti-Windows-x64', 'Openmukti-Windows-arm64',
    'Openmukti-Linux-x86_64', 'Openmukti-Linux-aarch64',
    'Openmukti-Linux-i686-system-runtime', 'Openmukti-Linux-armv7-system-runtime',
    'Openmukti-Linux-ppc64le-system-runtime', 'Openmukti-Linux-s390x-system-runtime',
    'Openmukti-Linux-riscv64-system-runtime',
    'Openmukti-macOS-x86_64', 'Openmukti-macOS-aarch64',
    'Openmukti-FreeBSD-x86_64-system-runtime', 'Openmukti-FreeBSD-aarch64-system-runtime',
    'Openmukti-OpenBSD-x86_64-system-runtime', 'Openmukti-OpenBSD-aarch64-system-runtime',
    'Openmukti-NetBSD-x86_64-system-runtime', 'Openmukti-NetBSD-aarch64-system-runtime',
    'Openmukti-DragonFly-x86_64-system-runtime',
    'Openmukti-Solaris-x86_64-system-runtime', 'Openmukti-illumos-x86_64-system-runtime',
)
FORMATS = ('.tar.xz', '.tar.gz', '.tar.zst', '.tar', '.zip', '.whl',
           '.deb', '.rpm', '.appimage', '.flatpak', '.dmg', '.pkg',
           '.apk', '.xbps', '.tgz', '.txz', '.p5p')
CHUNK_LIMIT = 1_900_000_000
BUF_SIZE = 8 * 1024 * 1024


def eligible(path: Path) -> bool:
    return (path.is_file() and not path.is_symlink() and path.stat().st_size > 0
            and path.name.casefold().endswith(FORMATS)
            and 'unverified' not in path.name.casefold()
            and not path.name.startswith('.'))


def stage(source: Path, target: Path, artifact_name: str,
          *, chunk_limit: int = CHUNK_LIMIT) -> list[dict]:
    if artifact_name not in EXPECTED_ARTIFACTS:
        raise ValueError('Unexpected CI artifact: ' + artifact_name)
    if chunk_limit <= 0:
        raise ValueError('Chunk size must be positive')
    target.mkdir(parents=True, exist_ok=True)
    inputs = sorted(p for p in source.rglob('*') if eligible(p))
    if not inputs:
        raise RuntimeError('Artifact has no distributable packages')
    if len({p.name for p in inputs}) != len(inputs):
        raise RuntimeError('Duplicate package filenames in one artifact')
    results = []
    for original in inputs:
        size = original.stat().st_size
        pieces = (size + chunk_limit - 1) // chunk_limit
        whole_digest = hashlib.sha256()
        with original.open('rb') as source_file:
            for part in range(pieces):
                filename = artifact_name + '--' + original.name
                if pieces > 1:
                    filename += f'.part{part + 1:03}-of{pieces:03}'
                dest = target / filename
                digest = hashlib.sha256()
                remaining = min(chunk_limit, size - part * chunk_limit)
                if pieces == 1:
                    # Hard-link on the same filesystem to avoid doubling runner usage.
                    try:
                        dest.hardlink_to(original)
                    except OSError:
                        shutil.copy2(original, dest)
                    while data := source_file.read(BUF_SIZE):
                        digest.update(data)
                        whole_digest.update(data)
                else:
                    with dest.open('wb') as output:
                        while remaining:
                            data = source_file.read(min(remaining, BUF_SIZE))
                            if not data:
                                raise RuntimeError('Build package was truncated')
                            output.write(data)
                            digest.update(data)
                            whole_digest.update(data)
                            remaining -= len(data)
                results.append({'file': filename, 'source': original.name,
                                'bytes': dest.stat().st_size, 'sha256': digest.hexdigest(),
                                'part': part + 1, 'parts': pieces})
        if pieces > 1:
            results.append({'source_checksum': original.name,
                            'bytes': size, 'sha256': whole_digest.hexdigest(),
                            'parts': pieces})
    (target / (artifact_name + '--SHA256SUMS.txt')).write_text(
        ''.join(row['sha256'] + '  ' + row['file'] + '\n'
                for row in results if 'file' in row), encoding='utf-8')
    if any('source_checksum' in row for row in results):
        (target / (artifact_name + '--REASSEMBLY.txt')).write_text(
            'Join .partNNN-ofNNN files in numerical order and verify full SHA256.\n\n' +
            '\n'.join(f"{row['source_checksum']}  {row['sha256']}  {row['bytes']} bytes"
                      for row in results if 'source_checksum' in row) + '\n',
            encoding='utf-8')
    return results


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('artifact_name')
    args = parser.parse_args(argv)
    print(json.dumps(stage(args.source, args.destination, args.artifact_name), indent=2))


if __name__ == '__main__':
    main()
