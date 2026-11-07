"""Freeze the complete Windows GUI and CLI with their embedded runtimes."""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def run(*args, cwd=None):
    print('+', ' '.join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], cwd=cwd or ROOT, check=True)


def freeze():
    if shutil.which('pyinstaller') is None and subprocess.run([sys.executable, '-c', 'import PyInstaller'], capture_output=True).returncode:
        raise RuntimeError('PyInstaller not installed: run python -m pip install pyinstaller')
    mode = '--onefile' if os.name == 'nt' else '--onedir'
    options = ['--clean', '--noconfirm', mode, '--noupx', '--collect-data', 'openvoice', '--distpath', str(DIST), '--workpath', str(ROOT / '.pyinstaller-build'), '--specpath', str(ROOT / '.pyinstaller-spec')]
    # uv is bundled for first-run Python/CPU-neural dependency provisioning.
    uv = Path(sys.executable).parent / ('uv.exe' if os.name == 'nt' else 'uv')
    if not uv.is_file():
        raise RuntimeError('uv bootstrap binary is missing. Run the automatic build setup first.')
    options += ['--add-binary', str(uv) + os.pathsep + 'uv']
    from fetch_ffmpeg import prepare, target_platform
    vendor = prepare()
    family, arch = target_platform()
    for name in ('ffmpeg', 'ffprobe'):
        binary = vendor / (name + ('.exe' if family == 'windows' else ''))
        options += ['--add-binary', str(binary) + os.pathsep + 'ffmpeg']
    try:
        import importlib.util
        if importlib.util.find_spec('piper') is not None:
            options += ['--collect-all','piper']
        if importlib.util.find_spec('onnxruntime') is not None:
            options += ['--collect-all','onnxruntime']
    except (ImportError,ModuleNotFoundError,ValueError):
        pass
    options += ['--collect-all', 'PIL', '--collect-all', 'fontTools', '--collect-all', 'regex']
    # Collect optional installed Studio runtimes, including their package data
    # and loaded native libraries. Core CPU rendering has no dependency on them.
    import importlib.util
    for name in ('tkinterdnd2','cryptography','mutagen','psutil','babel','num2words','pyopencl','vosk','sounddevice'):
        if importlib.util.find_spec(name) is not None:
            options += ['--collect-all',name]
    from pillow_bundle import pillow_options
    options += pillow_options()
    if os.name == 'nt':
        # Vendored Pillow loads FriBiDi at runtime, so --collect-all PIL alone
        # cannot supply it. Include the architecture-matched verified DLL in
        # BOTH independent one-file applications, plus its LGPL license.
        sys.path.insert(0, str(ROOT / 'scripts'))
        from platform_support import windows_arch
        native = ROOT / '.build-assets' / 'text-layout' / windows_arch()
        dll = native / 'libfribidi-0.dll'
        license_file = native / 'FRIBIDI-LICENSE.txt'
        if not dll.is_file() or not license_file.is_file():
            raise RuntimeError('Required FriBiDi runtime is not staged; build with python build.py first')
        options += ['--add-binary', str(dll) + os.pathsep + 'text_layout']
        options += ['--add-data', str(license_file) + os.pathsep + 'text_layout']
    for notice in vendor.glob('*.txt'):
        options += ['--add-data', str(notice) + os.pathsep + 'ffmpeg']
    origin = vendor / 'FFMPEG-ORIGIN.json'
    if origin.is_file():
        options += ['--add-data', str(origin) + os.pathsep + 'ffmpeg']
    if os.name == 'nt':
        worker = ROOT / '.build-assets' / 'workers' / 'OpenmuktiPiperWorker.exe'
        if not worker.is_file():
            raise RuntimeError('A standalone Piper worker must be built before the Windows single-file applications')
        options += ['--add-binary', str(worker) + os.pathsep + 'piper_worker']
        ocr_worker = ROOT / '.build-assets' / 'workers' / 'OpenmuktiOCRWorker.exe'
        if not ocr_worker.is_file():
            raise RuntimeError('Build the standalone OCR worker with scripts/build_windows_py315.py first')
        options += ['--add-binary', str(ocr_worker) + os.pathsep + 'ocr_worker']
        from prepare_tesseract import prepare as prepare_ocr
        options += ['--add-data', str(prepare_ocr()) + os.pathsep + 'tesseract']
    else:
        # Native Linux bundles Python imaging libraries; Tesseract is supplied
        # by the host distribution with its matching shared libraries.
        options += ['--collect-all', 'PIL', '--collect-all', 'numpy', '--collect-all', 'cv2',
                    '--collect-all', 'pypdfium2', '--collect-all', 'pypdfium2_raw']
    outputs = []
    for name, entry, gui in [('OpenmuktiAudiobookMaker', 'openvoice_gui.py', True), ('OpenmuktiAudiobookMakerCMD', 'openvoice_cli.py', False)]:
        icon_options = ['--icon', str(ROOT / 'assets' / 'openmukti.ico')] if os.name == 'nt' else []
        info_options = ['--version-file', str(ROOT / 'packaging' / 'windows_version.txt')] if os.name == 'nt' else []
        run(sys.executable, '-m', 'PyInstaller', *(options + icon_options + info_options + ['--windowed' if gui else '--console', '--name', name, str(ROOT / entry)]))
        folder = DIST / name
        path = (DIST / (name + '.exe')) if os.name == 'nt' else folder / name
        if not path.exists():
            raise RuntimeError(f'PyInstaller did not create {path}')
        outputs.append(path if os.name == 'nt' else folder)
    if os.name == 'nt' and os.environ.get('OPENMUKTI_DEFER_WINDOWS_PACKAGE') != '1':
        from package_windows_exes import build
        outputs.append(build(DIST))
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser(description='Freeze Windows standalone EXEs')
    parser.add_argument('target', nargs='?', choices=['native'], default='native')
    parser.add_argument('--strict', action='store_true', help='Return failure when freezing fails')
    args = parser.parse_args(argv)
    DIST.mkdir(exist_ok=True)
    try:
        if os.name != 'nt':
            raise RuntimeError('Create Windows EXEs on Windows using build.py')
        built = freeze()
        result = {'status': 'built', 'files': [str(path.relative_to(DIST)) for path in built]}
    except (RuntimeError, FileNotFoundError, subprocess.CalledProcessError, OSError) as exc:
        print('BUILD FAILED:', exc, flush=True)
        result = {'status': 'unavailable', 'reason': str(exc)}
    report = DIST / 'release-report.json'
    report.write_text(json.dumps({'host': platform.platform(), 'architecture': platform.machine(),
                                  'results': {'native': result}}, indent=2) + '\n', encoding='utf-8')
    print('Build report:', report, flush=True)
    return 0 if result['status'] == 'built' else 1


if __name__ == '__main__':
    raise SystemExit(main())
