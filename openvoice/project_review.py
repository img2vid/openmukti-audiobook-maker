"""Inspect saved projects without extracting media or voice models."""
from collections import defaultdict
from difflib import unified_diff
import json
from pathlib import Path
from zipfile import ZipFile

from .project_archive import MAX_MANIFEST_BYTES


def read_manifest(path):
    with ZipFile(path) as archive:
        if archive.getinfo('project.json').file_size > MAX_MANIFEST_BYTES:
            raise ValueError('Project metadata exceeds the size limit')
        data = json.loads(archive.read('project.json'))
    if data.get('format') != 'openmukti-project' or data.get('version') not in (1,2):
        raise ValueError('Unknown project format')
    return data


def resource_report(path):
    manifest = read_manifest(path)
    sizes = defaultdict(int)
    copies = defaultdict(list)
    rows = []
    with ZipFile(path) as archive:
        contents = {item.filename: item.file_size for item in archive.infolist()}
    for name, record in sorted(manifest['resources'].items()):
        size = record['size']
        suffix = Path(name).suffix.lower() or '(no extension)'
        sizes[suffix] += size
        copies[record['sha256']].append(name)
        status = 'present' if contents.get(name) == size else 'missing or size mismatch'
        rows.append(f'{name}  |  {size:,} bytes  |  {status}')
    return '\n'.join(['Storage by file type (uncompressed)', *[f'{ext}: {size:,} bytes' for ext,size in sorted(sizes.items())],
                      '', 'Bundled dependencies', *(rows or ['No bundled assets']), '', 'Duplicate assets (recorded SHA-256)',
                      *(', '.join(names) for names in copies.values() if len(names) > 1)])


def compare_projects(first, second):
    def lines(path):
        data = read_manifest(path)
        text = data.pop('text').splitlines()
        return text + ['--- Project settings, books and assets ---'] + json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False).splitlines()
    return '\n'.join(unified_diff(lines(first), lines(second), fromfile=str(first), tofile=str(second), lineterm='')) or 'Projects match.'
