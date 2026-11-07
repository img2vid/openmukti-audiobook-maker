from __future__ import annotations
import argparse
import hashlib
import json
import platform
import sys
import sysconfig
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.platform_support import pe_arch
PROGRAMS = ('OpenmuktiAudiobookMaker', 'OpenmuktiAudiobookMakerCMD')
VERSION = '1.0.24'


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def components(folder: Path) -> list[tuple[Path, str]]:
    files = []
    for name in PROGRAMS:
        exe = folder / f'{name}.exe'
        valid = False
        if exe.is_file():
            with exe.open('rb') as stream:
                valid = stream.read(2) == b'MZ'
        if not valid:
            raise ValueError(f'Missing or invalid Windows executable: {exe}')
        if (folder / name).is_dir():
            raise ValueError(f'Unexpected folder-based executable: {folder / name}')
        files.append((exe, exe.name))
    return files


def architecture() -> str:
    value = sysconfig.get_platform().lower()
    if 'arm64' in value:
        return 'arm64'
    if 'amd64' in value or 'x86_64' in value:
        return 'x64'
    if 'win32' in value or 'x86' in value:
        return 'x86'
    return platform.machine().lower()


def build(folder: Path, *, validation_status=None) -> Path:
    folder = folder.resolve()
    files = components(folder)
    identities = {pe_arch(path) for path, _ in files}
    if len(identities) != 1:
        raise ValueError('The main EXEs must have the same native architecture')
    identity = identities.pop()
    arch = {'x86_64':'x64','aarch64':'arm64','i686':'x86'}.get(identity, identity)
    validation_file = folder / 'standalone-validation.json'
    validation = json.loads(validation_file.read_text(encoding='utf-8')) if validation_file.is_file() else {}
    status = validation_status or ('passed' if validation.get('ok') is True else
                                  'blocked_by_windows_policy' if validation.get('validation_status') == 'blocked_by_windows_policy' else
                                  'failed' if validation else 'not_run')
    if status not in {'passed','failed','not_run','blocked_by_windows_policy'}:
        raise ValueError('Unknown runtime validation status')
    if status == 'passed' and validation.get('ok') is not True:
        raise ValueError('A successful runtime report is required for a verified archive')
    suffix = 'Standalone-EXEs' if status == 'passed' else 'UNVERIFIED-Policy-Blocked' if status == 'blocked_by_windows_policy' else 'UNVERIFIED-EXEs'
    archive = folder / f'Openmukti-Audiobook-Maker-Windows-{arch}-{suffix}.zip'
    runtime_programs = list(validation.get('programs',{}).values())
    versions = {p.get('version') for p in runtime_programs if p.get('version')}
    if status == 'passed' and len(versions) > 1:
        raise ValueError('The two EXEs report different application versions')
    runtime_version = next(iter(versions)) if len(versions) == 1 else None
    python_versions = sorted({p.get('python') for p in runtime_programs if p.get('python')})
    notice = (
        f'Openmukti Audiobook Maker {runtime_version or "(version unverified; builder " + VERSION + ")"} — standalone Windows applications\n\n'
        f'Runtime validation: {status}.\n'
        'No code-signing certificate is required to build or package these EXEs.\n'
        + ('Compilation and packaging completed; runtime tests were not run. UNVERIFIED describes runtime testing, not a compilation failure.\n\n' if status == 'not_run' else
           'These files have not passed runtime validation. Windows policy permission is still required.\n\n' if status != 'passed' else 'Both EXEs passed standalone runtime validation.\n\n') +
        'Run OpenmuktiAudiobookMaker.exe to open the GUI.\n'
        'Run OpenmuktiAudiobookMakerCMD.exe --help for the command-line interface.\n'
        'Neither EXE needs an _internal folder, another EXE, Python, or a separate FFmpeg installation.\n'
        'Piper synthesis, FFmpeg, and FFprobe are bundled inside each EXE.\n'
        'Tesseract OCR, eng/osd OCR data, the imaging worker, and the English spelling dictionary are also embedded.\n'
        'The EXEs self-extract runtime files into a temporary folder while running.\n'
        'Keep write access to your Windows temporary directory and sufficient free disk space.\n'
        'Downloaded Piper ONNX voice models remain user-provided external data, not built into these EXEs.\n\n'
        + ('The main applications are native ARM64. Their x64 Piper/OCR/Tesseract helpers require Windows 11 x64 emulation.\n\n' if identity == 'aarch64' else '') +
        'SHA256SUMS.txt verifies the two executable files.\n'
        'FFmpeg binaries may carry GPL obligations; see THIRD_PARTY_NOTICES.md.\n'
        'A Windows Application Control block requires the applicable policy approval or trusted publisher signing. '
        'See README.md in the source. This archive does not grant execution permission.\n'
    )
    hashes = [f'{sha256(path)}  {name}' for path, name in files]
    build_info = {
        'application': 'Openmukti Audiobook Maker',
        'version': runtime_version,
        'builder_version': VERSION,
        'version_source': 'runtime_report' if runtime_version else 'source_metadata_unverified',
        'validation_status': status,
        'runtime_verified': status == 'passed',
        'signature_required': False,
        'signature_verification': 'not_performed',
        'platform': 'Windows',
        'architecture': arch,
        'main_binary_architecture': identity,
        'windows_x64_emulation_required': identity == 'aarch64',
        'native_helper_architecture': 'x86_64',
        'build_time_utc': datetime.now(timezone.utc).isoformat(),
        'python_version': python_versions[0] if len(python_versions) == 1 else None,
        'python_versions': python_versions,
        'packaging_python_version': sys.version,
        'format': 'PyInstaller onefile; no external _internal directory',
        'python_runtime': ('CPython ' + ' / '.join(python_versions) if python_versions else 'CPython (version unverified)') + ' embedded in each main EXE',
        'piper_helper_runtime': 'CPython 3.12 embedded in a onefile Piper helper nested within each main EXE',
        'media_tools': 'FFmpeg and FFprobe embedded in each main EXE',
        'ocr': 'Tesseract 5, eng/osd traineddata, and a Python 3.12 native imaging worker embedded in each main EXE',
        'files': len(files),
    }
    try:
        import PyInstaller
        build_info['pyinstaller_version'] = PyInstaller.__version__
    except ImportError:
        build_info['pyinstaller_version'] = 'unavailable'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as output:
        for path, name in files:
            output.write(path, name)
        output.writestr('README.txt', notice)
        output.writestr('SHA256SUMS.txt', '\n'.join(hashes) + '\n')
        output.writestr('BUILD_PROVENANCE.json', json.dumps(build_info, indent=2) + '\n')
        validation = folder / 'standalone-validation.json'
        if validation.is_file():
            output.write(validation, 'standalone-validation.json')
        block_report = folder / 'windows-policy-block.json'
        if status == 'blocked_by_windows_policy' and block_report.is_file():
            output.write(block_report, 'windows-policy-block.json')
        output.write(ROOT / 'LICENSE', 'LICENSE')
        for name in ('PROOFLOOM_LICENSE.txt', 'PROOFLOOM_DICTIONARY_LICENSE.txt', 'ENGLISH_DICTIONARY_LICENSE.txt', 'TESSERACT_LICENSE.txt'):
            output.write(ROOT / 'openvoice' / 'resources' / name, 'OCR-notices/' + name)
        output.write(ROOT / 'THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md')
        vendor = ROOT / 'vendor' / 'ffmpeg' / f'windows-{arch}'
        for path in sorted(vendor.glob('*')):
            if path.suffix.lower() in ('.txt', '.json'):
                output.write(path, f'FFmpeg-notices/{path.name}')
        tesseract = ROOT / 'vendor' / 'tesseract' / 'windows-x64'
        for path in sorted(tesseract.rglob('*')):
            if path.is_file() and path.suffix.lower() not in ('.exe','.dll','.traineddata'):
                output.write(path, 'Tesseract-notices/' + path.relative_to(tesseract).as_posix())
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description='Archive two independent standalone Windows EXE files')
    parser.add_argument('--folder', type=Path, default=Path('dist'))
    args = parser.parse_args()
    print(build(args.folder))


if __name__ == '__main__':
    main()
