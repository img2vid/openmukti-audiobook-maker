#!/usr/bin/env python3
"""Restore missing source assets from the original Openmukti distribution ZIP.

Usage (from the Git repository root):
    python scripts/restore_missing_assets_from_archive.py /path/to/original.zip

Safe-by-default: only openvoice/engines and openvoice/resources are restored,
existing differing files are kept unless --overwrite is explicitly passed.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path, PurePosixPath
import shutil
import sys
import zipfile


def restore(archive: Path, root: Path, overwrite: bool = False) -> int:
    if not archive.is_file():
        print(f"ERROR: ZIP archive does not exist: {archive}", file=sys.stderr)
        return 2
    if not (root / 'pyproject.toml').is_file() or not (root / 'openvoice' / '__init__.py').is_file():
        print(f"ERROR: Not the root of an Openmukti source checkout: {root}", file=sys.stderr)
        return 2

    added = 0
    same = 0
    skipped = []
    paths = set()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = PurePosixPath(info.filename).parts
            if not parts or '..' in parts or any(p in ('', '.') for p in parts):
                continue
            if 'openvoice' not in parts:
                continue
            index = parts.index('openvoice')
            relparts = parts[index:]
            if len(relparts) < 3 or relparts[1] not in ('engines', 'resources'):
                continue
            if '__pycache__' in relparts or relparts[-1].endswith(('.pyc', '.pyo')):
                continue
            relative_path = Path(*relparts)
            if relative_path in paths:
                print(f"ERROR: Duplicate ZIP member: {relative_path}", file=sys.stderr)
                return 2
            paths.add(relative_path)
            dest = root / relative_path
            data = z.read(info)
            if dest.is_file():
                if dest.read_bytes() == data:
                    same += 1
                    continue
                if not overwrite:
                    skipped.append(str(relative_path))
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            added += 1
    print(f'Restored/updated: {added} files; already identical: {same}; differing skipped: {len(skipped)}')
    if skipped:
        print('Different files were not overwritten (use --overwrite to replace them):')
        for path in skipped:
            print('  ' + path)
    if not paths:
        print('ERROR: Source ZIP contains no openvoice/engines or openvoice/resources files.', file=sys.stderr)
        return 2
    verifier = root / 'scripts' / 'verify_repository_assets.py'
    if verifier.exists():
        import subprocess
        result = subprocess.run([sys.executable, str(verifier)], cwd=str(root), check=False)
        return result.returncode
    return 1 if skipped else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='Path to the ORIGINAL full Openmukti ZIP archive')
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--overwrite', action='store_true', help='Replace differing existing source assets')
    args = parser.parse_args()
    return restore(args.archive, args.project_root.resolve(), args.overwrite)


if __name__ == '__main__':
    raise SystemExit(main())
