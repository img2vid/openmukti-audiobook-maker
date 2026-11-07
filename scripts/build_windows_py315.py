from __future__ import annotations
import os
import argparse
import contextlib
import json
import shutil
import struct
import subprocess
import sys
import sysconfig
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
if __package__:
    from .windows_policy import WindowsPolicyBlocked, is_policy_block, write_block_report, collect_diagnostics, POLICY_EXIT_CODE
    from .platform_support import pe_arch, windows_arch
else:
    from windows_policy import WindowsPolicyBlocked, is_policy_block, write_block_report, collect_diagnostics, POLICY_EXIT_CODE
    from platform_support import pe_arch, windows_arch

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
VENV = ROOT / '.build-venv'
PIPER_VENV = ROOT / '.piper-build-venv'
PYINSTALLER = 'pyinstaller==6.22.3'
PIPER_VERSION = 'piper-tts==1.8.0'
ASSETS = ROOT / '.build-assets'
WORKERS = ASSETS / 'workers'
STATUS = ROOT / 'build-logs' / 'windows-build-status.json'


def checkpoint(phase: str, *, command=None, exit_code=None, detail=None):
    """Durable last-step marker, useful even if Windows ends Python abruptly.

    This file is independent of the line-oriented build log; it is updated
    before invoking expensive child programs and after they finish.
    """
    payload = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'phase': phase,
        'last_command': [str(x) for x in command] if command is not None else None,
        'exit_code': exit_code,
        'detail': str(detail) if detail is not None else None,
        'next_step': 'If interrupted, read build-logs/windows-build.log and run py -3 build.py --repair',
    }
    try:
        STATUS.parent.mkdir(parents=True, exist_ok=True)
        temp = STATUS.with_suffix('.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(STATUS)
    except OSError as exc:
        print(f'Build status checkpoint unavailable: {exc}', file=sys.stderr, flush=True)


def stage(name: str):
    print(f'\n=== {name} ===', flush=True)
    checkpoint(name)



def run(*args, cwd=ROOT):
    print('+', ' '.join(str(arg) for arg in args), flush=True)
    command = [str(arg) for arg in args]
    checkpoint('running command', command=command)
    try:
        process = subprocess.Popen(command, cwd=str(cwd), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    except OSError as exc:
        checkpoint('could not launch command', command=command, detail=exc)
        if is_policy_block(exc):
            raise WindowsPolicyBlocked(command, exc) from exc
        raise
    for line in process.stdout:
        print(line, end='', flush=True)
    process.stdout.close()
    code = process.wait()
    if code:
        checkpoint('command failed', command=command, exit_code=code)
        raise subprocess.CalledProcessError(code, command)
    checkpoint('command completed', command=command, exit_code=0)


def executable(venv: Path) -> Path:
    return venv / 'Scripts' / 'python.exe'


def matching_binary(path, architecture):
    try:
        return pe_arch(path) == architecture
    except (OSError, ValueError):
        return False


def clean_environment(path: Path):
    if path.exists():
        shutil.rmtree(path)
        if path.exists():
            raise RuntimeError(f'Unable to remove previous build environment: {path}')


def ensure_python315():
    """Historical entry point; accept supported x64 build interpreters."""
    if os.name != 'nt':
        raise RuntimeError('Build on a Windows computer; PyInstaller cannot cross-compile Windows EXEs from Linux')
    if not (3, 10) <= sys.version_info[:2] <= (3, 15):
        raise RuntimeError(f'Use 64-bit CPython 3.10–3.15; found {sys.version.split()[0]}. Python 3.12 is recommended for building.')
    if sys.implementation.name != 'cpython' or struct.calcsize('P') * 8 != 64:
        raise RuntimeError('A 64-bit CPython interpreter is required')
    if windows_arch() not in {'x86_64','aarch64'}:
        raise RuntimeError('Use a native Windows x64 or ARM64 Python interpreter')


def build_main_environment(*, reuse=False) -> Path:
    if not (reuse and matching_binary(executable(VENV), windows_arch())):
        clean_environment(VENV)
        run(sys.executable, '-m', 'venv', VENV)
    else:
        print('Repair: reusing the existing main build environment.', flush=True)
    python = executable(VENV)
    from scripts.auto_dependencies import ensure_pip
    ensure_pip(python)
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:', PYINSTALLER)
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', str(ROOT) + '[pdf,rtf,video]')
    # Keep optional desktop adapters independent: a missing wheel on an older
    # architecture must not prevent building the CPU-capable application.
    for extra in ('psutil', 'cryptography', 'mutagen', 'tkinterdnd2', 'Babel', 'num2words', 'pyopencl'):
        try:
            run(python, '-m', 'pip', 'install', '--only-binary=:all:', extra)
        except subprocess.CalledProcessError:
            print(f'Optional Studio provider {extra} has no installable wheel in this build environment.',flush=True)
    # The official Windows Pillow wheels intentionally load FriBiDi at runtime.
    # Installing fonts alone, or requesting RAQM without its native DLL, fails.
    # Install a checksum-pinned, architecture-matched DLL before the first PIL
    # FreeType import; it is embedded into both standalone EXEs below.
    stage('Installing the native Windows Unicode text shaping library')
    if sys.version_info[:2] < (3, 14):
        run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
            'zstandard>=0.25,<1')
    os.environ.pop('OPENMUKTI_FRIBIDI_DLL', None)
    # Extract via the venv interpreter, so Python 3.12 can use zstandard.
    # No network operation occurs on --repair if the pinned archive is cached.
    destination = ASSETS / 'text-layout'
    run(python, ROOT / 'packaging' / 'fribidi_bundle.py', windows_arch(), destination)
    dll = destination / windows_arch() / 'libfribidi-0.dll'
    if not dll.is_file():
        raise RuntimeError(f'Native FriBiDi DLL missing after preparation: {dll}')
    os.environ['OPENMUKTI_FRIBIDI_DLL'] = str(dll)
    try:
        # Do not distribute a Windows executable that cannot shape Bengali/
        # Indic or Arabic. Historical version 1 did not verify this.
        run(python, '-c',
            'from openvoice.text_layout import raqm_available; '
            'assert raqm_available(), '
            '"FriBiDi was installed but Pillow RAQM is still unavailable; check DLL architecture and native wheel"; '
            'from PIL import ImageFont; from openvoice.animated_video import pick_font; '
            'f=pick_font("বাংলা ভাষা",32); '
            'p=f.primary if hasattr(f,"primary") else f; '
            'assert p.layout_engine==ImageFont.Layout.RAQM, "Bengali RAQM font missing"; '
            'print("Complex-script preflight PASSED:",p.path)')
    finally:
        # Piper/OCR workers may be x64 under Windows ARM64. Never leak an ARM
        # DLL override into those independent x64 helper processes.
        os.environ.pop('OPENMUKTI_FRIBIDI_DLL', None)
    run(python, '-c', 'import PyInstaller; print("Windows main Python:", __import__("sys").version)')
    return python


def build_worker(main_python: Path, *, reuse=False, check_runtime=True) -> Path:
    run(main_python, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:', 'uv>=0.9,<1')
    uv = VENV / 'Scripts' / 'uv.exe'
    if not uv.exists():
        raise RuntimeError('uv could not be installed to fetch the build-only Python 3.12 runtime')
    if not (reuse and matching_binary(executable(PIPER_VENV), 'x86_64')):
        clean_environment(PIPER_VENV)
        print('Installing an isolated Python 3.12 to build a portable Piper companion; it will be bundled with the application.', flush=True)
        # Piper/OpenCV publish x64 Windows wheels. On Windows 11 ARM, keep
        # the main applications native ARM64 and use isolated x64 helpers.
        request = 'cpython-3.12-windows-x86_64' if windows_arch() == 'aarch64' else '3.12'
        run(uv, 'venv', '--python', request, '--managed-python', PIPER_VENV)
    else:
        print('Repair: reusing the existing native-worker build environment.', flush=True)
    python = executable(PIPER_VENV)
    run(uv, 'pip', 'install', '--python', python, '--only-binary=:all:', PYINSTALLER, PIPER_VERSION,
        'Pillow>=10.4', 'numpy>=1.26', 'opencv-python-headless>=4.10,<5', 'pypdfium2>=4.30')
    run(uv, 'pip', 'install', '--python', python, '--no-deps', ROOT)
    run(python, '-c', 'from piper.voice import PiperVoice; import onnxruntime, sys; assert sys.version_info[:2] == (3,12); print("Piper runtime ready:", onnxruntime.__version__)')
    work = ROOT / '.piper-pyinstaller-work'
    spec = ROOT / '.piper-pyinstaller-spec'
    WORKERS.mkdir(parents=True, exist_ok=True)
    exe = WORKERS / 'OpenmuktiPiperWorker.exe'
    if reuse and matching_binary(exe, 'x86_64'):
        if not check_runtime:
            print('Repair: reused the existing Piper worker; its launch check is deferred to optional verification.', flush=True)
            return exe
        try:
            run(exe, '--health')
            print('Repair: verified and reused the unchanged Piper worker.', flush=True)
            return exe
        except (OSError, subprocess.CalledProcessError):
            print('Cached Piper worker failed its health check; rebuilding it.', flush=True)
    run(python, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onefile', '--noupx',
        '--paths', ROOT, '--console', '--name', 'OpenmuktiPiperWorker', '--collect-all', 'piper',
        '--collect-all', 'onnxruntime', '--distpath', WORKERS,
        '--workpath', work, '--specpath', spec, ROOT / 'scripts' / 'piper_worker.py')
    exe = WORKERS / 'OpenmuktiPiperWorker.exe'
    if not exe.exists():
        raise RuntimeError('Piper worker executable was not generated')
    if pe_arch(exe) != 'x86_64':
        raise RuntimeError('Piper worker must contain the x64 Python runtime')
    if check_runtime:
        run(exe, '--health')
    return exe


def build_ocr_worker(*, check_runtime=True) -> Path:
    python = executable(PIPER_VENV)
    run(python, '-m', 'PyInstaller', '--clean', '--noconfirm', '--onefile', '--noupx',
        '--console', '--name', 'OpenmuktiOCRWorker', '--paths', ROOT,
        '--collect-all', 'PIL', '--collect-all', 'numpy', '--collect-all', 'cv2',
        '--collect-all', 'pypdfium2', '--collect-all', 'pypdfium2_raw',
        '--collect-data', 'openvoice', '--distpath', WORKERS,
        '--workpath', ROOT / '.ocr-pyinstaller-work', '--specpath', ROOT / '.ocr-pyinstaller-spec',
        ROOT / 'scripts' / 'ocr_worker.py')
    worker = WORKERS / 'OpenmuktiOCRWorker.exe'
    if not worker.is_file():
        raise RuntimeError('Portable OCR worker was not generated')
    if pe_arch(worker) != 'x86_64':
        raise RuntimeError('OCR worker must contain the x64 Python runtime')
    if check_runtime:
        run(worker, '--health')
    return worker


def preflight_ocr(worker: Path, runtime: Path):
    """Catch recognition/configuration failures before freezing both large EXEs."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    request, result, cancel = (ASSETS / name for name in ('ocr-preflight-request.json','ocr-preflight-result.json','ocr-preflight-cancel'))
    result.unlink(missing_ok=True)
    cancel.unlink(missing_ok=True)
    request.write_text(json.dumps({
        'source':str(ROOT / 'openvoice' / 'resources' / 'portable-ocr-check.png'),
        'settings':{'language':'eng','psm':6,'auto_rotate':False,'deskew':False},
        'result':str(result),'cancel':str(cancel),
        'tesseract':str(runtime / 'tesseract.exe'),
    }), encoding='utf-8')
    run(worker, '--request', request)
    if not result.is_file():
        raise RuntimeError('OCR preflight did not produce a recognition report')
    data = json.loads(result.read_text(encoding='utf-8'))
    text = '\n'.join(page.get('text','') for page in data.get('pages',[]))
    if 'modern world' not in text.casefold():
        raise RuntimeError('OCR preflight failed to read the sample image: ' + text[:200])
    print('OCR preflight passed: the staged runtime recognized the sample image.', flush=True)


def check_single_file_outputs():
    programs = ('OpenmuktiAudiobookMaker', 'OpenmuktiAudiobookMakerCMD')
    for name in programs:
        exe = DIST / f'{name}.exe'
        if not exe.is_file() or exe.stat().st_size < 1024 * 1024:
            raise RuntimeError(f'Standalone executable was not generated: {exe}')
        if pe_arch(exe) != windows_arch():
            raise RuntimeError(f'Wrong main EXE architecture: {exe}; expected {windows_arch()}')
        if (DIST / name).is_dir():
            raise RuntimeError(f'Unexpected folder-based build: {DIST / name}')


def package_existing_release(*, validation_status=None) -> Path:
    """Check layout and archive existing EXEs without launching or changing them."""
    check_single_file_outputs()
    sys.path.insert(0, str(ROOT / 'packaging'))
    from package_windows_exes import build
    archive = build(DIST, validation_status=validation_status)
    programs = ('OpenmuktiAudiobookMaker', 'OpenmuktiAudiobookMakerCMD')
    with zipfile.ZipFile(archive) as package:
        bad = package.testzip()
        if bad:
            raise RuntimeError(f'Standalone ZIP contains a corrupt member: {bad}')
        exe_names = {n for n in package.namelist() if n.lower().endswith('.exe')}
        expected = {f'{name}.exe' for name in programs}
        if exe_names != expected:
            raise RuntimeError(f'Unexpected executable inventory: {sorted(exe_names)}')
        if any('_internal' in n.casefold() or 'piper_worker/' in n.casefold() for n in package.namelist()):
            raise RuntimeError('Portable ZIP unexpectedly contains a runtime folder')
    return archive


def verify_single_file_release(worker: Path, main_python: Path) -> Path:
    check_single_file_outputs()
    run(DIST / 'OpenmuktiAudiobookMakerCMD.exe', '--help')
    if __package__:
        from .verify_windows_standalone import verify
    else:
        from verify_windows_standalone import verify
    validation = verify(DIST)
    (DIST / 'standalone-validation.json').write_text(json.dumps(validation, indent=2), encoding='utf-8')
    return package_existing_release()


def main(*, repair=False, verify_existing=False, diagnose_policy=False, package_existing=False, verify_runtime=False) -> int:
    ensure_python315()
    sys.path.insert(0, str(ROOT / 'packaging'))
    if diagnose_policy:
        print('Policy diagnostics:', collect_diagnostics(DIST), flush=True)
        return 0
    if package_existing:
        archive = package_existing_release()
        print('Existing standalone EXEs packaged without launching, rebuilding or signing:', archive, flush=True)
        return 0
    if verify_existing:
        archive = verify_single_file_release(None, None)
        print('Existing EXEs passed validation:', archive, flush=True)
        return 0
    # Creating unsigned EXEs does not require executing them. A Windows policy
    # denial during an optional launch test must not prevent compilation/archiving.
    os.environ['OPENMUKTI_BUILD_VERIFY_RUNTIME'] = '1' if verify_runtime else '0'
    stage('Preparing Windows build')
    stage('Installing main application dependencies and Unicode shaping support')
    main_python = build_main_environment(reuse=repair)
    stage('Preparing the offline Tesseract OCR runtime')
    from prepare_tesseract import prepare
    tesseract = prepare(check_runtime=verify_runtime)
    stage('Building Piper speech worker (CPU compatible)')
    worker = build_worker(main_python, reuse=repair, check_runtime=verify_runtime)
    stage('Building standalone OCR worker')
    ocr_worker = build_ocr_worker(check_runtime=verify_runtime)
    if verify_runtime:
        preflight_ocr(ocr_worker, tesseract)
    if not worker.is_file():
        raise RuntimeError('Built-in Piper worker is missing')
    stage('Cleaning old final EXEs; all build dependencies are prepared')
    clean_old_outputs()
    stage('Freezing Windows GUI and CLI executables')
    os.environ['OPENMUKTI_DEFER_WINDOWS_PACKAGE'] = '1'
    run(main_python, ROOT / 'packaging' / 'build_release.py', 'native', '--strict')
    if verify_runtime:
        stage('Checking standalone EXEs on Windows')
        run(DIST / 'OpenmuktiAudiobookMakerCMD.exe', 'ocr', '--status')
        archive = verify_single_file_release(worker, main_python)
    else:
        stage('Packaging executable ZIP without optional launch verification')
        archive = package_existing_release(validation_status='not_run')
    checkpoint('build completed', detail=archive)
    print('\nPORTABLE WINDOWS BUILD COMPLETE', flush=True)
    print(f'Main application: Python {sys.version.split()[0]}; Piper/OCR companions: bundled Python 3.12.', flush=True)
    print(f'Download/distribute this file: {archive}', flush=True)
    print('Each EXE contains its own runtime; no neighboring _internal folder or installed Python is needed.', flush=True)
    print('Piper, Tesseract OCR, English OCR data, imaging runtime, FFmpeg and FFprobe are embedded and extracted temporarily at runtime.', flush=True)
    print('No code-signing certificate is required. The builder does not sign the EXEs.', flush=True)
    if windows_arch() == 'aarch64':
        print('Main EXEs are native ARM64. Piper/OCR and Tesseract x64 helpers require Windows 11 x64 emulation.', flush=True)
    if not verify_runtime:
        print('Compilation and ZIP checks passed; runtime launch tests were not run. The UNVERIFIED ZIP contains the compiled portable EXEs.', flush=True)
        print('Optional: py -3 build.py --verify-existing tests the completed files without recompiling. Windows policy still controls whether unsigned EXEs may run.', flush=True)
    return 0


def clean_old_outputs():
    DIST.mkdir(parents=True, exist_ok=True)
    for name in ('OpenmuktiAudiobookMaker', 'OpenmuktiAudiobookMakerCMD'):
        folder = DIST / name
        if folder.is_symlink():
            folder.unlink()
        elif folder.is_dir():
            shutil.rmtree(folder)
        (DIST / f'{name}.exe').unlink(missing_ok=True)
    (DIST / 'standalone-validation.json').unlink(missing_ok=True)
    for archive in DIST.glob('Openmukti-Audiobook-Maker-Windows-*-Standalone-EXEs.zip'):
        archive.unlink()


def entrypoint(argv=None):
    parser = argparse.ArgumentParser(description='Build unsigned portable standalone Windows EXEs; runtime launch tests are optional')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--repair', action='store_true', help='Reuse build environments and the existing Piper worker; refresh source and rebuild OCR plus both main EXEs')
    mode.add_argument('--verify-existing', action='store_true', help='Validate and package the existing EXEs after policy approval, without deleting or rebuilding them')
    mode.add_argument('--diagnose-policy', action='store_true', help='Read file hashes and recent Windows Code Integrity events without running the generated EXEs')
    mode.add_argument('--package-existing', action='store_true', help='Archive the already compiled EXEs without launching, signing or rebuilding them')
    parser.add_argument('--verify-runtime', action='store_true', help='Also launch generated workers/EXEs and test real OCR and GUI; optional and subject to Windows application policy')
    args = parser.parse_args(argv)
    if args.verify_runtime and (args.verify_existing or args.diagnose_policy or args.package_existing):
        parser.error('--verify-runtime applies to a build or repair; --verify-existing already performs runtime checks')
    logs = ROOT / 'build-logs'
    logs.mkdir(exist_ok=True)
    log_path = logs / ('windows-verification.log' if args.verify_existing else 'windows-policy-diagnostics.log' if args.diagnose_policy else 'windows-packaging.log' if args.package_existing else 'windows-build.log')
    class Tee:
        def __init__(self, console, logfile):
            self.console, self.logfile = console, logfile
        def write(self, text):
            if self.console is not None:
                self.console.write(text)
            self.logfile.write(text)
        def flush(self):
            if self.console is not None:
                self.console.flush()
            self.logfile.flush()
    # Preserve the previous log if a new attempt starts after an interruption.
    if log_path.exists():
        try:
            shutil.copy2(log_path, log_path.with_suffix('.previous.log'))
        except OSError:
            pass
    with log_path.open('w', encoding='utf-8', buffering=1) as log:
        with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
            try:
                print('Windows build log:', log_path, flush=True)
                print('Last-step status:', STATUS, flush=True)
                print('Python:', sys.version, flush=True)
                print('For interrupted builds: py -3 build.py --repair', flush=True)
                checkpoint('build started', detail=f'python {sys.version.split()[0]}')
                return main(repair=args.repair, verify_existing=args.verify_existing, diagnose_policy=args.diagnose_policy,
                            package_existing=args.package_existing, verify_runtime=args.verify_runtime)
            except WindowsPolicyBlocked as exc:
                checkpoint('windows policy blocked', detail=exc)
                report = write_block_report(DIST, exc)
                print(f'\nWINDOWS POLICY BLOCK: {exc}\nCompiled files were retained in: {DIST}\nDiagnostic report: {DIST / "windows-policy-block.json"}', file=sys.stderr)
                if report['build_status'] == 'compiled':
                    try:
                        sys.path.insert(0, str(ROOT / 'packaging'))
                        from package_windows_exes import build
                        archive = build(DIST, validation_status='blocked_by_windows_policy')
                        print('Unverified archive for review:', archive, file=sys.stderr)
                    except Exception as packaging_error:
                        print('EXEs remain available; diagnostic archive could not be made:', packaging_error, file=sys.stderr)
                print('Obtain the applicable policy approval or trusted publisher signing, then run py -3 build.py --verify-existing. Rebuilding the same unsigned app does not grant policy permission.', file=sys.stderr)
                return POLICY_EXIT_CODE
            except KeyboardInterrupt:
                checkpoint('build interrupted by keyboard', detail='Pressing Ctrl+C stops the build safely')
                print('Build interrupted; run py -3 build.py --repair to reuse compatible build files.', file=sys.stderr)
                return 130
            except Exception as exc:
                checkpoint('build failed', detail=repr(exc))
                traceback.print_exc()
                print(f'BUILD FAILED: {exc}\nFull log: {log_path}', file=sys.stderr)
                return 1


if __name__ == '__main__':
    raise SystemExit(entrypoint())
