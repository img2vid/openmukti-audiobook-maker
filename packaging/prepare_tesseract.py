"""Collect a build-time Tesseract installation into a portable runtime tree."""
from __future__ import annotations
import os
import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAMBA_URL = 'https://github.com/mamba-org/micromamba-releases/releases/download/2.10.0-0/micromamba-win-64.exe'
MAMBA_SHA256 = 'f8b4284bd4eb1134122eaf93b3ea6c7be567e596de5829e1a6f478e34e41974a'


def download_micromamba(destination):
    if destination.is_file() and hashlib.sha256(destination.read_bytes()).hexdigest() == MAMBA_SHA256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.partial')
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(MAMBA_URL, headers={'User-Agent': 'Openmukti-Portable-Builder/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open('wb') as output:
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > 32 * 1024 * 1024:
                    raise RuntimeError('Unexpected micromamba download size')
                digest.update(block)
                output.write(block)
        if digest.hexdigest() != MAMBA_SHA256:
            raise RuntimeError('The OCR build-tool checksum did not match the pinned release')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def stage_conda_runtime(prefix, target, cache):
    binaries = prefix / 'Library' / 'bin'
    data = next((p for p in (prefix / 'Library' / 'share' / 'tessdata', prefix / 'share' / 'tessdata', binaries / 'tessdata') if all((p / f'{lang}.traineddata').is_file() for lang in ('eng','osd'))), None)
    if not (binaries / 'tesseract.exe').is_file() or data is None:
        raise RuntimeError('The downloaded Tesseract environment is missing its executable or eng/osd data')
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copy2(binaries / 'tesseract.exe', target / 'tesseract.exe')
    # Conda resolves Leptonica, image codecs, compression and VC runtime DLLs.
    for folder in (prefix, binaries):
        for dll in folder.glob('*.dll'):
            shutil.copy2(dll, target / dll.name)
    (target / 'tessdata').mkdir()
    for language in ('eng','osd'):
        shutil.copy2(data / f'{language}.traineddata', target / 'tessdata' / f'{language}.traineddata')
    for subdir in ('configs','tessconfigs'):
        if (data / subdir).is_dir():
            shutil.copytree(data / subdir, target / 'tessdata' / subdir)
    # Keep the licenses of the exact resolved packages with the runtime.
    for folder in (prefix / 'Library' / 'share' / 'licenses', prefix / 'share' / 'licenses'):
        if folder.is_dir():
            shutil.copytree(folder, target / 'licenses', dirs_exist_ok=True)
    for folder in (cache / 'pkgs').glob('*/info/licenses'):
        shutil.copytree(folder, target / 'licenses' / folder.parent.parent.name, dirs_exist_ok=True)
    records = []
    for record in sorted((prefix / 'conda-meta').glob('*.json')):
        data_record = json.loads(record.read_text(encoding='utf-8'))
        records.append({key: data_record.get(key) for key in ('name','version','build','url','sha256','license')})
    (target / 'TESSERACT-ORIGIN.json').write_text(json.dumps({'channel':'conda-forge','packages':records,'micromamba_sha256':MAMBA_SHA256}, indent=2), encoding='utf-8')
    return target


def bootstrap_tesseract(target):
    if os.name != 'nt':
        raise RuntimeError('Automatic portable Tesseract staging runs on Windows x64')
    assets = ROOT / '.build-assets'
    tool = download_micromamba(assets / 'micromamba.exe')
    prefix, cache = assets / 'tesseract-env', assets / 'mamba-root'
    print('Preparing portable Tesseract and its DLL dependencies; no administrator installation is needed.', flush=True)
    command = [str(tool), '--no-rc', '--root-prefix', str(cache), 'create', '--yes',
        '--prefix', str(prefix), '--override-channels', '--channel', 'conda-forge',
        '--strict-channel-priority', '--platform', 'win-64', 'tesseract>=5.5,<6']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=1800, check=False)
    print(result.stdout, flush=True)
    if result.returncode:
        raise RuntimeError('Automatic OCR runtime download failed: ' + (result.stderr or result.stdout)[-2000:])
    return stage_conda_runtime(prefix, target, cache)


def prepare(*, download=True, check_runtime=None):
    if check_runtime is None:
        check_runtime = os.environ.get('OPENMUKTI_BUILD_VERIFY_RUNTIME') != '0'
    override = os.environ.get('OPENMUKTI_TESSERACT_DIR', '').strip()
    target = ROOT / 'vendor' / 'tesseract' / 'windows-x64'
    candidates = [Path(override).expanduser()] if override else []
    candidates.append(target)
    if shutil.which('tesseract'):
        candidates.append(Path(shutil.which('tesseract')).resolve().parent)
    for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        if os.environ.get(key):
            candidates.append(Path(os.environ[key]) / 'Tesseract-OCR')
    source = next((p.resolve() for p in candidates if (p / 'tesseract.exe').is_file() and all((p / 'tessdata' / f'{lang}.traineddata').is_file() for lang in ('eng', 'osd'))), None)
    if source is None:
        if override:
            raise RuntimeError('OPENMUKTI_TESSERACT_DIR does not contain tesseract.exe and tessdata/eng.traineddata plus osd.traineddata. Correct or unset this optional override.')
        if not download:
            raise RuntimeError('No staged Tesseract runtime; enable automatic download or supply OPENMUKTI_TESSERACT_DIR.')
        source = bootstrap_tesseract(target).resolve()
    if source != target.resolve():
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for path in source.iterdir():
            if path.is_file() and (path.suffix.lower() in {'.dll', '.txt', '.md', '.html'} or path.name.lower().startswith(('license', 'copying', 'authors')) or path.name.lower() == 'tesseract.exe'):
                shutil.copy2(path, target / path.name)
        (target / 'tessdata').mkdir()
        for lang in ('eng', 'osd'):
            shutil.copy2(source / 'tessdata' / f'{lang}.traineddata', target / 'tessdata' / f'{lang}.traineddata')
        for subdir in ('configs', 'tessconfigs'):
            if (source / 'tessdata' / subdir).is_dir():
                shutil.copytree(source / 'tessdata' / subdir, target / 'tessdata' / subdir)
        for subdir in ('doc', 'licenses'):
            if (source / subdir).is_dir():
                shutil.copytree(source / subdir, target / subdir)
    shutil.copy2(ROOT / 'openvoice' / 'resources' / 'TESSERACT_LICENSE.txt', target / 'TESSERACT_LICENSE.txt')
    # Some conda distributions omit optional output profiles.
    configs = target / 'tessdata' / 'configs'
    configs.mkdir(parents=True, exist_ok=True)
    if not (configs / 'tsv').is_file():
        (configs / 'tsv').write_text('tessedit_create_tsv 1\n', encoding='ascii')
    if check_runtime:
        result = subprocess.run([str(target / 'tesseract.exe'), '--list-langs', '--tessdata-dir', str(target / 'tessdata')], capture_output=True, text=True, timeout=30, check=True)
        if not all(lang in result.stdout.split() for lang in ('eng', 'osd')):
            raise RuntimeError('Bundled Tesseract is missing eng / osd language data')
    return target
