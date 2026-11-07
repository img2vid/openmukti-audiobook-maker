"""Native Unix bundles and package-manager archives; only report outputs actually produced."""
from __future__ import annotations
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipapp
import zipfile
from pathlib import Path
from .platform_support import architecture, elf_arch, macho_arch, system

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / '.build-native'
DIST = ROOT / 'dist'
APP_ID = 'io.github.img2vid.Openmukti'
APP_NAME = 'OpenmuktiAudiobookMakerCMD'
FORMATS = {
    # Portable archives and Python distributions are available on every
    # host for which this system-runtime builder can run. Native installers
    # remain restricted to their own operating systems.
    'linux': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'deb', 'rpm', 'appimage', 'flatpak', 'arch', 'slack-txz', 'slack-tgz', 'apk', 'xbps'],
    'macos': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'dmg', 'mac-pkg'],
    'freebsd': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'pkg'],
    'dragonfly': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'pkg'],
    'openbsd': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'bsd-tgz'],
    'netbsd': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'bsd-tgz'],
    'solaris': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'ips', 'svr4'],
    'illumos': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist', 'ips', 'svr4'],
    'aix': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist'],
    'haiku': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist'],
    'gnu': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist'],
    'minix': ['tar', 'zip', 'tar-gz', 'tar-zst', 'wheel', 'sdist'],
}
NATIVE_ARCHES = {'windows': ['x86_64', 'aarch64 (x64 speech/OCR helpers)'],
                'linux': ['x86_64', 'aarch64'], 'macos': ['x86_64', 'aarch64']}
DESCRIPTION = 'Offline audiobook maker with GUI, neural and system voices, image/PDF OCR and English spelling correction.'


def run(*command, cwd=None, env=None, capture=False):
    command = [str(x) for x in command]
    print('+', shlex.join(command), flush=True)
    return subprocess.run(command, cwd=cwd or ROOT, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None)


def require(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} is required on the build host; install it using the native package manager')
    return Path(path).resolve()


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)


def version():
    # Read source metadata without importing optional application dependencies.
    return re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (ROOT / 'openvoice/__init__.py').read_text())[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def desktop(exec_command='openmukti-gui'):
    return (f'[Desktop Entry]\nType=Application\nName=Openmukti Audiobook Maker\nComment={DESCRIPTION}\n'
            f'Exec={exec_command}\nIcon={APP_ID}\nTerminal=false\nCategories=AudioVideo;Audio;Education;\n')


def notices(destination):
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, destination / name)
    target = destination / 'licenses'
    target.mkdir(exist_ok=True)
    for path in (ROOT / 'openvoice/resources').glob('*LICENSE.txt'):
        shutil.copy2(path, target / path.name)


def tesseract_data(binary):
    # Ubuntu 22.04 ships traineddata under 4.00 despite running Tesseract 5.
    # Other distributions and Homebrew use a versioned or unversioned tree.
    candidates = [binary.parent / 'tessdata', binary.parent.parent / 'share/tessdata',
                  Path('/usr/share/tessdata'), Path('/usr/local/share/tessdata'),
                  Path('/opt/homebrew/share/tessdata')]
    for prefix in (Path('/usr/share/tesseract-ocr'),
                   Path('/usr/local/share/tesseract-ocr'),
                   Path('/opt/homebrew/share/tesseract-ocr')):
        if prefix.is_dir():
            candidates.extend(sorted(prefix.glob('*/tessdata')))
    configured = os.environ.get('TESSDATA_PREFIX')
    if configured:
        parent = Path(configured).expanduser()
        candidates[:0] = [parent, parent / 'tessdata']
    for directory in candidates:
        if all((directory / f'{lang}.traineddata').is_file() for lang in ('eng', 'osd')):
            return directory
    raise RuntimeError('The build host needs Tesseract eng and osd language data (or set TESSDATA_PREFIX)')


def freeze():
    family, arch = system(), architecture()
    if arch not in NATIVE_ARCHES.get(family, []):
        raise RuntimeError(f'Bundled native dependencies are not configured for {family}/{arch}; use --profile system on that native host')
    python = WORK / 'venv/bin/python'
    if not python.exists():
        run(sys.executable, '-m', 'venv', WORK / 'venv')
    from .auto_dependencies import ensure_pip
    ensure_pip(python)
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
        'pyinstaller==6.22.3', 'piper-tts==1.8.0', 'Pillow>=10.4', 'numpy>=1.26',
        'opencv-python-headless>=4.10,<5', 'pypdfium2>=4.30')
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', 'uv>=0.9,<1', str(ROOT) + '[pdf,rtf,video]')
    tesseract = require('tesseract')
    data = tesseract_data(tesseract)
    if family == 'linux':
        sys.path.insert(0, str(ROOT / 'packaging'))
        from fetch_ffmpeg import prepare
        media = prepare()
    else:
        media = require('ffmpeg').parent
        require('ffprobe')
    options = ['--clean', '--noconfirm', '--noupx', '--onedir', '--console', '--name', APP_NAME,
               '--distpath', str(WORK / 'freeze'), '--workpath', str(WORK / 'pyinstaller'),
               '--specpath', str(WORK / 'spec'), '--paths', str(ROOT), '--collect-submodules', 'openvoice',
               '--collect-all', 'piper', '--collect-all', 'onnxruntime', '--collect-all', 'PIL', '--collect-all', 'fontTools', '--collect-all', 'regex',
               '--collect-all', 'numpy', '--collect-all', 'cv2', '--collect-all', 'pypdfium2',
               '--collect-all', 'pypdfium2_raw', '--collect-data', 'openvoice',
               '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.ttk']
    uv = python.parent / 'uv'
    if not uv.is_file():
        raise RuntimeError('The bundled uv dependency bootstrap was not installed into the frozen build environment')
    options += ['--add-binary', str(uv) + ':uv']
    options += json.loads(subprocess.check_output([str(python),str(ROOT / 'packaging' / 'pillow_bundle.py')],text=True))
    for name in ('ffmpeg', 'ffprobe'):
        options += ['--add-binary', str(media / name) + ':ffmpeg']
    options += ['--add-binary', str(tesseract) + ':tesseract']
    for lang in ('eng', 'osd'):
        options += ['--add-data', str(data / f'{lang}.traineddata') + ':tesseract/tessdata']
    for name in ('configs', 'tessconfigs'):
        if (data / name).is_dir():
            options += ['--add-data', str(data / name) + ':tesseract/tessdata/' + name]
    if family == 'linux':
        for path in media.iterdir():
            if path.suffix in ('.txt', '.json'):
                options += ['--add-data', str(path) + ':ffmpeg']
    run(python, '-m', 'PyInstaller', *options, ROOT / 'openvoice_cli.py')
    payload = WORK / 'freeze' / APP_NAME
    binary = payload / APP_NAME
    if not binary.is_file():
        raise RuntimeError('The native freezer did not create the application')
    if family == 'linux' and elf_arch(binary) != arch:
        raise RuntimeError('The frozen executable architecture differs from the native host')
    if family == 'macos' and macho_arch(binary) != arch:
        raise RuntimeError('The macOS executable architecture differs from the native host')
    if family == 'macos':
        # PyInstaller can bind the Tesseract CLI to cv2's incompatible dylib.
        # Restore the Homebrew dependency closure in an isolated private tree.
        from .macos_tesseract import isolate_tesseract
        isolate_tesseract(payload, tesseract)
    # This launcher works from any extraction directory, including paths containing spaces.
    write(payload / 'openmukti', '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit\nexec "$HERE/' + APP_NAME + '" "$@"\n', 0o755)
    write(payload / 'openmukti-gui', '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit\nexec "$HERE/' + APP_NAME + '" gui "$@"\n', 0o755)
    notices(payload)
    return payload


def system_payload(python=None):
    """Portable Python application; explicitly not a frozen, self-contained executable."""
    payload = WORK / 'system-payload'
    app = WORK / 'zipapp'
    if payload.exists(): shutil.rmtree(payload)
    if app.exists(): shutil.rmtree(app)
    payload.mkdir(parents=True)
    shutil.copytree(ROOT / 'openvoice', app / 'openvoice', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    vendor_pure_libraries(app)
    write(app / '__main__.py', 'from openvoice.cli import main\nraise SystemExit(main())\n')
    zipapp.create_archive(app, payload / 'openmukti.pyz', interpreter='/usr/bin/env python3', compressed=True)
    command = shlex.split(python or 'python3')
    if not command:
        raise RuntimeError('A Python command is required')
    # Validate the command, while retaining PATH resolution for portable Unix archives.
    require(command[0])
    run(*command, '-c', 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ is required"')
    launch = '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit\nexec ' + shlex.join(command) + ' "$HERE/openmukti.pyz"'
    write(payload / 'openmukti', launch + ' "$@"\n', 0o755)
    write(payload / 'openmukti-gui', launch + ' gui "$@"\n', 0o755)
    write(payload / 'RUNTIME-REQUIREMENTS.txt',
          'System-runtime package: Python 3.10+ and Tk; Pillow, NumPy and OpenCV; '
          'Tesseract 5 with eng/osd data; FFmpeg/FFprobe; PDFium or Poppler for scanned PDFs; '
          'Piper/ONNX for neural voices, and eSpeak NG or OS voices.\n'
          'No feature code is removed. Native providers must be installed on this OS/architecture.\n')
    notices(payload)
    return payload


def vendor_pure_libraries(destination):
    """Include pure-Python importers without requiring pip on a BSD/Solaris builder."""
    packages = [
        ('pypdf', '5.9.0', 'be10a4c54202f46d9daceaa8788be07aa8cd5ea8c25c529c50dd509206382c35'),
        ('striprtf', '0.0.29', '0fc6a41999d015358d19627776b616424dd501ad698105c81d76734d1e14d91b'),
    ]
    # Offline copies of the previously shipped, RECORD-verified pure-Python files.
    offline_pins = {'pypdf': 'a7e75ee03fef6e394737665dd45431b720c571eac285f360389c67937e3916e2', 'striprtf': '01510a1f050c77676a7892284b6a09f6f3a0e2fd4b6d3c3c4812fe50ca1e9281'}
    for package, release, expected in packages:
        cache = WORK / f'{package}-{release}.whl'
        bundled = ROOT / 'vendor' / 'python' / f'{package}-{release}.zip'
        if bundled.is_file() and digest(bundled) == offline_pins[package]:
            cache = bundled
        elif not cache.exists() or digest(cache) != expected:
            request = urllib.request.Request(f'https://pypi.org/pypi/{package}/{release}/json',
                                             headers={'User-Agent': 'Openmukti-Native-Builder'})
            with urllib.request.urlopen(request, timeout=45) as response:
                info = json.load(response)
            wheel = next(x for x in info['urls'] if x['filename'].endswith('py3-none-any.whl') and x['digests']['sha256'] == expected)
            with urllib.request.urlopen(wheel['url'], timeout=60) as response:
                data = response.read(15 * 1024 * 1024 + 1)
            if len(data) > 15 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f'Invalid pure-Python dependency download: {package}')
            cache.write_bytes(data)
        with zipfile.ZipFile(cache) as source:
            for member in source.infolist():
                path = Path(member.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in member.filename:
                    raise RuntimeError('Unsafe dependency wheel member')
                if not member.is_dir():
                    target = destination / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read(member))


def verify(payload, profile, gui, strict=True):
    if profile == 'frozen':
        env = os.environ.copy()
        env['OPENMUKTI_VERIFY_GUI'] = '1' if gui else '0'
        report = DIST / 'runtime-check.json'
        # Only the frozen program can attest that its libraries and OCR engine are embedded.
        run(payload / APP_NAME, '--portable-check', report, env=env)
        value = json.loads(report.read_text(encoding='utf-8'))
        if not value.get('ok'):
            failed = {name: status for name, status in value.get('checks', {}).items()
                      if not status.get('ok')}
            raise RuntimeError('Native bundled runtime verification failed: '
                               + json.dumps(failed, ensure_ascii=False))
        return value
    env = os.environ.copy()
    # Import from the staged ZIP, not the checkout. Report every unavailable provider.
    code = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
            'from openvoice.portable import check_system_runtime;'
            f'print(json.dumps(check_system_runtime(exercise={strict!r},gui={gui!r})))')
    launch = shlex.split((payload / 'openmukti').read_text().split('exec ', 1)[1].split(' "$HERE/', 1)[0])
    result = json.loads(run(*launch, '-c', code, payload / 'openmukti.pyz', capture=True, env=env).stdout)
    write(DIST / 'runtime-check.json', json.dumps(result, indent=2) + '\n')
    if not result['ok'] and strict:
        raise RuntimeError('System providers are incomplete; see runtime-check.json. Packaging without --verify-runtime remains available.')
    return result


def stem(profile):
    return f'Openmukti-{version()}-{system()}-{architecture()}-' + ('portable' if profile == 'frozen' else 'system-runtime')


def portable_tar(payload, profile):
    target = DIST / (stem(profile) + '.tar.xz')
    with tarfile.open(target, 'w:xz') as archive:
        archive.add(payload, arcname='Openmukti')
    return target


def portable_zip(payload, profile):
    """Create a ZIP of the complete payload, preserving Unix symlink entries."""
    target = DIST / (stem(profile) + '.zip')
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
        for path in sorted(payload.rglob('*')):
            relative = Path('Openmukti') / path.relative_to(payload)
            name = relative.as_posix()
            if path.is_symlink():
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = (0o120777 << 16)
                archive.writestr(info, os.readlink(path))
            elif path.is_file():
                info = zipfile.ZipInfo.from_file(path, name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
                with path.open('rb') as source:
                    archive.writestr(info, source.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=8)
    return target


def portable_targz(payload, profile):
    target = DIST / (stem(profile) + '.tar.gz')
    with tarfile.open(target, 'w:gz', compresslevel=8) as archive:
        archive.add(payload, arcname='Openmukti')
    return target


def portable_tarzst(payload, profile):
    require('zstd')
    raw = WORK / (stem(profile) + '.tar')
    target = DIST / (stem(profile) + '.tar.zst')
    with tarfile.open(raw, 'w', format=tarfile.PAX_FORMAT) as archive:
        archive.add(payload, arcname='Openmukti')
    run('zstd', '-f', '-T0', raw, '-o', target)
    raw.unlink(missing_ok=True)
    return target


def python_distribution(kind):
    """Build a standards-based wheel or source distribution from pyproject.toml."""
    tool_env = WORK / 'python-build-tools'
    python = tool_env / 'bin/python'
    if os.name == 'nt':
        python = tool_env / 'Scripts/python.exe'
    if not python.exists():
        run(sys.executable, '-m', 'venv', tool_env)
    # Keep packaging tools isolated from the application's build environment.
    from .auto_dependencies import ensure_pip
    ensure_pip(python)
    # Never run the PyPA `build` module from the repository root: our own
    # top-level build.py would shadow it, producing an argparse error instead.
    if subprocess.run([str(python), '-c', 'import build'], cwd=WORK, capture_output=True).returncode:
        run(python, '-m', 'pip', 'install', '--disable-pip-version-check', 'build', cwd=WORK)
    output = WORK / ('python-dist-' + kind)
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    run(python, '-m', 'build', '--' + kind, '--outdir', output, ROOT, cwd=WORK)
    files = sorted(output.iterdir())
    if len(files) != 1 or not files[0].is_file():
        raise RuntimeError(f'Expected one {kind} artifact, found {len(files)}')
    target = DIST / files[0].name
    shutil.copy2(files[0], target)
    return target


def wheel(_payload, _profile):
    return python_distribution('wheel')


def sdist(_payload, _profile):
    return python_distribution('sdist')


def install_tree(payload, name, prefix='/usr'):
    root = WORK / ('stage-' + name)
    if root.exists(): shutil.rmtree(root)
    prefix_path = root / prefix.lstrip('/')
    shutil.copytree(payload, prefix_path / 'lib/openmukti', symlinks=True)
    for name in ('openmukti', 'openmukti-gui'):
        write(prefix_path / 'bin' / name, f'#!/bin/sh\nexec "{prefix}/lib/openmukti/{name}" "$@"\n', 0o755)
    write(prefix_path / 'share/applications' / (APP_ID + '.desktop'), desktop())
    icon = prefix_path / 'share/icons/hicolor/256x256/apps' / (APP_ID + '.png')
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'openvoice/resources/openmukti-icon.png', icon)
    return root


def deb(payload, profile):
    require('dpkg-deb')
    root = install_tree(payload, 'deb')
    arch = {'x86_64':'amd64', 'aarch64':'arm64', 'i686':'i386', 'armv7':'armhf',
            'ppc64le':'ppc64el'}.get(architecture(), architecture())
    glibc = platform.libc_ver()[1]
    depends = f'libc6 (>= {glibc or "2.35"}), libx11-6, libxext6, libxrender1, libxft2, libfontconfig1'
    if profile == 'system':
        arch = 'all'
        depends = ('python3 (>= 3.10), python3-tk, python3-pil, python3-numpy, '
                   'python3-opencv, tesseract-ocr, tesseract-ocr-eng, tesseract-ocr-osd, '
                   'poppler-utils, ffmpeg, espeak-ng')
    write(root / 'DEBIAN/control', f'Package: openmukti\nVersion: {version()}\nSection: sound\nPriority: optional\nArchitecture: {arch}\nMaintainer: Aishik Dutta\nDepends: {depends}\nDescription: {DESCRIPTION}\n')
    target = DIST / (stem(profile) + '.deb')
    run('dpkg-deb', '--root-owner-group', '--build', root, target)
    run('dpkg-deb', '--info', target, capture=True)
    return target


def rpm(payload, profile):
    require('rpmbuild')
    top = WORK / 'rpmbuild'
    for name in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
        (top / name).mkdir(parents=True, exist_ok=True)
    stage = install_tree(payload, 'rpm')
    deps = f'Requires: glibc >= {platform.libc_ver()[1] or "2.35"}, libX11, libXext, libXrender, libXft, fontconfig\n'
    if profile == 'system':
        deps = 'BuildArch: noarch\nRequires: python3 >= 3.10, python3-tkinter, python3-pillow, python3-numpy, python3-opencv, tesseract, tesseract-langpack-eng, tesseract-langpack-osd, poppler-utils, ffmpeg\n'
    spec = top / 'SPECS/openmukti.spec'
    write(spec, f'''%global __os_install_post %{{nil}}
%global debug_package %{{nil}}
%global _build_id_links none
Name: openmukti
Version: {version()}
Release: 1
Summary: Offline audiobook maker with OCR
License: MIT AND Apache-2.0 AND GPL-3.0-or-later
AutoReqProv: no
{deps}%description
{DESCRIPTION}
%install
mkdir -p "%{{buildroot}}"
cp -a {shlex.quote(str(stage))}/. "%{{buildroot}}/"
%files
/usr/bin/openmukti
/usr/bin/openmukti-gui
/usr/lib/openmukti
/usr/share/applications/{APP_ID}.desktop
/usr/share/icons/hicolor/256x256/apps/{APP_ID}.png
''')
    run('rpmbuild', '-bb', '--define', '_topdir ' + str(top), spec)
    candidates = list((top / 'RPMS').rglob(f'openmukti-{version()}-1.*.rpm'))
    if len(candidates) != 1: raise RuntimeError('Expected exactly one native RPM')
    target = DIST / (stem(profile) + '.rpm')
    shutil.copy2(candidates[0], target)
    run('rpm', '-qip', target, capture=True)
    return target


def arch_package(payload, profile):
    require('zstd')
    root = install_tree(payload, 'arch')
    deps = ['glibc', 'libx11', 'libxext', 'libxrender', 'libxft', 'fontconfig']
    if profile == 'system':
        deps += ['python', 'tk', 'python-pypdf', 'python-pillow', 'python-numpy', 'opencv', 'tesseract', 'tesseract-data-eng', 'tesseract-data-osd', 'poppler', 'ffmpeg', 'espeak-ng']
    installed_size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    write(root / '.PKGINFO', f'pkgname = openmukti\npkgbase = openmukti\npkgver = {version()}-1\npkgdesc = {DESCRIPTION}\nbuilddate = {int(time.time())}\npackager = Aishik Dutta\nsize = {installed_size}\narch = {"any" if profile == "system" else architecture()}\nlicense = MIT\n' + ''.join('depend = ' + d + '\n' for d in deps))
    raw = WORK / 'arch-package.tar'
    with tarfile.open(raw, 'w', format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(root.iterdir()): archive.add(path, arcname=path.name)
    target = DIST / (stem(profile) + '.pkg.tar.zst')
    run('zstd', '-f', '-T0', raw, '-o', target)
    run('zstd', '-t', target)
    return target


def slack_package(payload, profile, compression):
    """Create a Slackware installable package archive with install metadata."""
    extension = 'txz' if compression == 'xz' else 'tgz'
    stage = install_tree(payload, 'slack-' + extension)
    install = stage / 'install'
    install.mkdir(exist_ok=True)
    description = [
        'openmukti: Openmukti Audiobook Maker',
        'openmukti: Offline audiobook creation with GUI and command-line tools.',
        'openmukti: Includes OCR and multilingual text/video features.',
    ]
    description.extend(['openmukti:'] * (11 - len(description)))
    write(install / 'slack-desc', '\n'.join(description[:11]) + '\n')
    write(install / 'doinst.sh', '#!/bin/sh\n# No post-install actions are required.\n', 0o755)
    target = DIST / (stem(profile) + '.' + extension)
    mode = 'w:xz' if compression == 'xz' else 'w:gz'
    with tarfile.open(target, mode, format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(stage.rglob('*')):
            relative = path.relative_to(stage).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.uid, info.gid = 0, 0
            info.uname, info.gname = 'root', 'bin'
            if path.is_file() and not path.is_symlink():
                with path.open('rb') as source:
                    archive.addfile(info, source)
            else:
                archive.addfile(info)
    return target


def slack_txz(payload, profile):
    return slack_package(payload, profile, 'xz')


def slack_tgz(payload, profile):
    return slack_package(payload, profile, 'gz')


def xbps_package(payload, profile):
    """Create an XBPS package from the staged tree using native Void tools."""
    require('xbps-create')
    require('xbps-uhelper')
    arch = run('xbps-uhelper', 'arch', capture=True).stdout.strip()
    if not arch:
        raise RuntimeError('xbps-uhelper did not report the native XBPS architecture')
    dependencies = os.environ.get('OPENMUKTI_XBPS_DEPENDENCIES', '').strip()
    if not dependencies:
        raise RuntimeError('Set OPENMUKTI_XBPS_DEPENDENCIES to the runtime package names for this Void host; dependency names differ by profile and repository')
    stage = install_tree(payload, 'xbps', prefix='/usr')
    output = WORK / 'xbps-output'
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    run('xbps-create', '-A', arch, '-n', f'openmukti-{version()}_1',
        '-s', DESCRIPTION, '-S', DESCRIPTION,
        '-H', 'https://github.com/img2vid', '-m', 'Openmukti maintainers',
        '-l', 'MIT', '-D', dependencies, '-t', 'audio', stage, cwd=output)
    candidates = sorted(output.glob('*.xbps'))
    if len(candidates) != 1:
        raise RuntimeError(f'xbps-create produced {len(candidates)} package files')
    target = DIST / (stem(profile) + '.xbps')
    shutil.copy2(candidates[0], target)
    return target


def apk_package(payload, profile):
    """Build an Alpine APK through abuild, using the user's configured key."""
    require('abuild')
    dependencies = os.environ.get('OPENMUKTI_APK_DEPENDENCIES', '').split()
    if not dependencies:
        raise RuntimeError('Set OPENMUKTI_APK_DEPENDENCIES to the exact Alpine runtime package names before building; package names differ by Alpine release and profile')
    if any(not re.fullmatch(r'[A-Za-z0-9+_.:<>=~-]+', item) for item in dependencies):
        raise RuntimeError('OPENMUKTI_APK_DEPENDENCIES contains a package name with unsupported characters')
    arch = architecture()
    apk_arch = {'i686': 'x86', 'armv7': 'armv7', 'aarch64': 'aarch64', 'x86_64': 'x86_64',
                'ppc64le': 'ppc64le', 's390x': 's390x', 'riscv64': 'riscv64'}.get(arch)
    if profile == 'frozen' and apk_arch is None:
        raise RuntimeError(f'No Alpine APK architecture mapping is configured for {arch}')
    package_arch = 'noarch' if profile == 'system' else apk_arch
    work = WORK / 'apkbuild'
    if work.exists():
        shutil.rmtree(work)
    distfiles = work / 'distfiles'
    repodest = work / 'repo'
    distfiles.mkdir(parents=True)
    stage = install_tree(payload, 'apk', prefix='/usr')
    source_archive = distfiles / 'openmukti-payload.tar.gz'
    with tarfile.open(source_archive, 'w:gz', compresslevel=8) as archive:
        for path in sorted(stage.rglob('*')):
            archive.add(path, arcname=path.relative_to(stage).as_posix())
    depends = ' '.join(dependencies)
    apkbuild = f'''# Generated by Openmukti's native build system.
pkgname=openmukti
pkgver={version()}
pkgrel=0
pkgdesc="Offline audiobook maker with OCR"
url="https://github.com/img2vid"
arch="{package_arch}"
license="MIT"
depends="{depends}"
makedepends=""
options="!check"
source="openmukti-payload.tar.gz"
build() {{
    :
}}
package() {{
    tar -xzf "$srcdir/openmukti-payload.tar.gz" -C "$pkgdir"
}}
'''
    write(work / 'APKBUILD', apkbuild)
    env = os.environ.copy()
    env['SRCDEST'] = str(distfiles)
    env['REPODEST'] = str(repodest)
    env['APORTSDIR'] = str(work)
    run('abuild', 'checksum', cwd=work, env=env)
    run('abuild', '-r', cwd=work, env=env)
    candidates = sorted(repodest.rglob('*.apk'))
    if len(candidates) != 1:
        raise RuntimeError(f'abuild produced {len(candidates)} APK package files; check abuild key and repository configuration')
    target = DIST / (stem(profile) + '.apk')
    shutil.copy2(candidates[0], target)
    return target


def appimage(payload, profile):
    if profile != 'frozen': raise RuntimeError('AppImage requires a frozen runtime; system Python is not portable')
    appdir = install_tree(payload, 'appimage')
    write(appdir / 'AppRun', '#!/bin/sh\nAPPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit\n'
          'if [ "${1:-}" = "--cli" ]; then\n  shift\n  exec "$APPDIR/usr/lib/openmukti/openmukti" "$@"\nfi\n'
          'exec "$APPDIR/usr/lib/openmukti/openmukti-gui" "$@"\n', 0o755)
    shutil.copy2(appdir / 'usr/share/applications' / (APP_ID + '.desktop'), appdir)
    shutil.copy2(ROOT / 'openvoice/resources/openmukti-icon.png', appdir / (APP_ID + '.png'))
    arch = {'armv7':'armhf'}.get(architecture(), architecture())
    tool = shutil.which('appimagetool')
    if not tool:
        sys.path.insert(0, str(ROOT / 'packaging'))
        from fetch_ffmpeg import request_json, download_verified
        metadata = request_json('https://api.github.com/repos/AppImage/appimagetool/releases/latest')
        asset = next((a for a in metadata['assets'] if a['name'] == f'appimagetool-{arch}.AppImage'), None)
        if not asset or not asset.get('digest', '').startswith('sha256:'):
            raise RuntimeError('AppImage release has no authoritative checksum for this architecture')
        binary = WORK / 'appimagetool.AppImage'
        download_verified(asset['browser_download_url'], binary, asset['digest'].split(':', 1)[1])
        binary.chmod(0o755)
        unpack = WORK / 'appimagetool'
        unpack.mkdir(exist_ok=True)
        run(binary, '--appimage-extract', cwd=unpack, capture=True)
        tool = unpack / 'squashfs-root/AppRun'
    target = DIST / (stem(profile) + '.AppImage')
    env = dict(os.environ, ARCH=arch)
    run(tool, appdir, target, env=env)
    target.chmod(0o755)
    if elf_arch(target) != architecture(): raise RuntimeError('AppImage architecture does not match the host')
    return target


def flatpak(payload, profile):
    if profile != 'frozen': raise RuntimeError('Flatpak requires the frozen runtime profile')
    require('flatpak-builder'); require('flatpak')
    # Build from the staged bundle, so the sandbox never needs network access to pip.
    # Platform 25.08 has a newer glibc than our Ubuntu 22.04 build baseline.
    stage = install_tree(payload, 'flatpak', prefix='/app') / 'app'
    manifest = {'app-id': APP_ID, 'runtime': 'org.freedesktop.Platform', 'runtime-version': '25.08',
                'sdk': 'org.freedesktop.Sdk', 'command': 'openmukti-gui',
                'finish-args': ['--share=ipc', '--socket=x11', '--socket=pulseaudio', '--share=network', '--filesystem=host'],
                'modules': [{'name': 'openmukti', 'buildsystem': 'simple',
                             'build-commands': ['cp -a . /app/'],
                             'sources': [{'type': 'dir', 'path': str(stage)}]}]}
    source = WORK / 'openmukti.flatpak.json'
    write(source, json.dumps(manifest, indent=2) + '\n')
    repo = WORK / 'flatpak-repo'
    run('flatpak-builder', '--user', '--assumeyes', '--install-deps-from=flathub', '--force-clean',
        '--repo=' + str(repo), WORK / 'flatpak-build', source)
    target = DIST / (stem(profile) + '.flatpak')
    run('flatpak', 'build-bundle', repo, target, APP_ID, 'master')
    return target


def bsd_package(payload, profile):
    family = system()
    prefix = '/usr/pkg' if family == 'netbsd' else '/usr/local'
    stage = install_tree(payload, family, prefix)
    if family in ('freebsd', 'dragonfly'):
        require('pkg')
        metadata = WORK / 'pkg-manifest'
        metadata.mkdir(exist_ok=True)
        manifest = {'name': 'openmukti', 'version': version(), 'origin': 'audio/openmukti',
                    'comment': DESCRIPTION, 'desc': DESCRIPTION, 'maintainer': 'img2vid@users.noreply.github.com',
                    'www': 'https://github.com/img2vid', 'prefix': prefix, 'licenselogic': 'multi',
                    'licenses': ['MIT'], 'categories': ['audio'],
                    'arch': run('pkg', 'config', 'ABI', capture=True).stdout.strip(),
                    'files': {str(Path('/') / p.relative_to(stage)): '-' if p.is_symlink() else digest(p)
                              for p in stage.rglob('*') if p.is_file() or p.is_symlink()}}
        if profile == 'system':
            deps = json.loads(os.environ.get('OPENMUKTI_PKG_DEPENDENCIES', '{}'))
            if not deps: raise RuntimeError('Set OPENMUKTI_PKG_DEPENDENCIES to installed pkg dependency records (name: {origin,version})')
            manifest['deps'] = deps
        write(metadata / '+MANIFEST', json.dumps(manifest, indent=2))
        out = WORK / 'pkg-output'; out.mkdir(exist_ok=True)
        # DragonFly's libarchive lacks builtin zstd support: use its native XZ format.
        compression = ['-f', 'txz'] if family == 'dragonfly' else []
        run('pkg', 'create', *compression, '-r', stage, '-m', metadata, '-o', out)
        files = list(out.glob('openmukti-*'))
        if len(files) != 1: raise RuntimeError('Native pkg did not create one archive')
        target = DIST / (stem(profile) + files[0].suffix)
        shutil.copy2(files[0], target)
        return target
    require('pkg_create')
    packlist = WORK / 'packing-list'
    entries = [p.relative_to(stage / prefix.lstrip('/')).as_posix()
               for p in sorted(stage.rglob('*')) if p.is_file() or p.is_symlink()]
    description = WORK / 'package-description'
    write(description, DESCRIPTION + '\n')
    dependencies = json.loads(os.environ.get('OPENMUKTI_BSD_DEPENDENCIES', '[]'))
    if profile == 'system' and not dependencies:
        raise RuntimeError('Set OPENMUKTI_BSD_DEPENDENCIES to installed pkg_info package names for native dependency metadata')
    dependency_lines = '' if family == 'openbsd' else ''.join('@pkgdep ' + d + '\n' for d in dependencies)
    write(packlist, dependency_lines + '\n'.join(entries) + '\n')
    target = DIST / (stem(profile) + '.tgz')
    native = WORK / f'openmukti-{version()}.tgz'
    if family == 'openbsd':
        dep_options = [arg for dependency in dependencies for arg in ('-P', dependency)]
        run('pkg_create', '-A', run('machine', '-a', capture=True).stdout.strip(),
            '-B', stage, '-p', prefix, '-f', packlist, '-d', description,
            '-D', 'COMMENT=Offline audiobook maker with OCR', '-D', 'FULLPKGPATH=audio/openmukti',
            '-D', 'PORTSDIR=/usr/ports', *dep_options, native)
    else:
        run('pkg_create', '-p', stage / prefix.lstrip('/'), '-I', prefix,
            '-c', '-Offline audiobook maker with OCR', '-d', description, '-f', packlist, native)
    shutil.copy2(native, target)
    return target


def ips(payload, profile):
    for tool in ('pkgrepo', 'pkgsend', 'pkgrecv'): require(tool)
    stage = install_tree(payload, 'ips', '/usr')
    repo = WORK / 'ips-repository'
    if repo.exists(): shutil.rmtree(repo)
    run('pkgrepo', 'create', repo)
    run('pkgrepo', 'set', '-s', repo, 'publisher/prefix=openmukti')
    fmri = f'pkg://openmukti/application/audio/openmukti@{version()}'
    content = run('pkgsend', 'generate', stage, capture=True).stdout
    dependencies = json.loads(os.environ.get('OPENMUKTI_IPS_DEPENDENCIES', '[]'))
    if profile == 'system' and not dependencies:
        raise RuntimeError('Set OPENMUKTI_IPS_DEPENDENCIES to required package FMRIs for this native repository')
    manifest = WORK / 'openmukti.p5m'
    write(manifest, f'set name=pkg.fmri value={fmri}\nset name=pkg.summary value="Offline audiobook maker with OCR"\n'
          + f'set name=variant.arch value={"sparc" if architecture() == "sparc64" else "i386"}\n'
          + ''.join('depend type=require fmri=' + d + '\n' for d in dependencies) + content)
    run('pkgsend', 'publish', '-s', repo.as_uri(), '-d', stage, manifest)
    target = DIST / (stem(profile) + '.p5p')
    target.unlink(missing_ok=True)
    run('pkgrecv', '-s', repo.as_uri(), '-a', '-d', target, fmri)
    return target


def svr4(payload, profile):
    require('pkgmk'); require('pkgtrans')
    stage = install_tree(payload, 'svr4', '/usr')
    metadata = WORK / 'svr4-meta'; metadata.mkdir(exist_ok=True)
    info = metadata / 'pkginfo'
    write(info, f'PKG=OPENmukti\nNAME=Openmukti Audiobook Maker\nVERSION={version()}\nARCH={"sparc" if architecture() == "sparc64" else "i386"}\nCATEGORY=application\nVENDOR=Aishik Dutta\nBASEDIR=/\n')
    prototype = ['i pkginfo=' + str(info)]
    for path in sorted(stage.rglob('*')):
        rel = path.relative_to(stage).as_posix()
        if path.is_symlink(): prototype.append(f's none {rel}={os.readlink(path)}')
        elif path.is_dir(): prototype.append(f'd none {rel} 0755 root bin')
        else: prototype.append(f'f none {rel}={path} {path.stat().st_mode & 0o777:04o} root bin')
    spec = metadata / 'prototype'
    write(spec, '\n'.join(prototype) + '\n')
    spool = WORK / 'svr4-spool'; spool.mkdir(exist_ok=True)
    run('pkgmk', '-o', '-f', spec, '-d', spool)
    target = DIST / (stem(profile) + '.pkg')
    target.unlink(missing_ok=True)
    run('pkgtrans', '-s', spool, target, 'OPENmukti')
    return target


def dmg(payload, profile):
    if profile != 'frozen': raise RuntimeError('macOS DMG requires the frozen runtime profile')
    require('hdiutil')
    stage = WORK / 'dmg'; stage.mkdir(exist_ok=True)
    app = stage / 'Openmukti Audiobook Maker.app/Contents'
    # A proper .app wrapper keeps CLI and GUI on the same complete frozen runtime.
    if app.parent.exists(): shutil.rmtree(app.parent)
    shutil.copytree(payload, app / 'Resources/runtime', symlinks=True)
    write(app / 'MacOS/Openmukti', '#!/bin/sh\nHERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit\nexec "$HERE/../Resources/runtime/openmukti-gui" "$@"\n', 0o755)
    import plistlib
    with (app / 'Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleName': 'Openmukti Audiobook Maker', 'CFBundleIdentifier': APP_ID,
                      'CFBundleExecutable': 'Openmukti', 'CFBundlePackageType': 'APPL',
                      'CFBundleShortVersionString': version(), 'NSHighResolutionCapable': True}, stream)
    applications = stage / 'Applications'
    if not applications.exists(): applications.symlink_to('/Applications')
    target = DIST / (stem(profile) + '.dmg')
    target.unlink(missing_ok=True)
    run('hdiutil', 'create', '-volname', 'Openmukti', '-srcfolder', stage, '-ov', '-format', 'UDZO', target)
    run('hdiutil', 'verify', target)
    return target


def mac_pkg(payload, profile):
    """Build an unsigned native macOS installer package on macOS."""
    require('pkgbuild')
    stage = install_tree(payload, 'mac-pkg', prefix='/usr/local')
    target = DIST / (stem(profile) + '.pkg')
    run('pkgbuild', '--root', stage, '--identifier', APP_ID,
        '--version', version(), '--install-location', '/', target)
    return target


PACKAGERS = {
    'tar': portable_tar, 'zip': portable_zip, 'tar-gz': portable_targz,
    'tar-zst': portable_tarzst, 'wheel': wheel, 'sdist': sdist,
    'deb': deb, 'rpm': rpm, 'arch': arch_package,
    'appimage': appimage, 'flatpak': flatpak,
    'slack-txz': slack_txz, 'slack-tgz': slack_tgz,
    'apk': apk_package, 'xbps': xbps_package,
    'pkg': bsd_package, 'bsd-tgz': bsd_package,
    'ips': ips, 'svr4': svr4, 'dmg': dmg, 'mac-pkg': mac_pkg,
}


def format_skip_reason(name, profile):
    """Return why an optional auto target cannot run on this host, if known."""
    if profile == 'system' and name in {'appimage', 'flatpak', 'dmg'}:
        return 'this format requires the frozen runtime profile'
    tools = {
        'tar-zst': ('zstd',), 'arch': ('zstd',),
        'deb': ('dpkg-deb',), 'rpm': ('rpmbuild', 'rpm'),
        'flatpak': ('flatpak-builder', 'flatpak'),
        'apk': ('abuild',), 'xbps': ('xbps-create', 'xbps-uhelper'),
        'pkg': ('pkg',), 'bsd-tgz': ('pkg_create',),
        'ips': ('pkgrepo', 'pkgsend', 'pkgrecv'),
        'svr4': ('pkgmk', 'pkgtrans'), 'dmg': ('hdiutil',),
        'mac-pkg': ('pkgbuild',),
    }.get(name, ())
    absent = [tool for tool in tools if not shutil.which(tool)]
    if absent:
        return 'missing tool(s): ' + ', '.join(absent)
    env_requirements = {
        'apk': 'OPENMUKTI_APK_DEPENDENCIES',
        'xbps': 'OPENMUKTI_XBPS_DEPENDENCIES',
    }
    if profile == 'system':
        env_requirements.update({
            'pkg': 'OPENMUKTI_PKG_DEPENDENCIES',
            'bsd-tgz': 'OPENMUKTI_BSD_DEPENDENCIES',
            'ips': 'OPENMUKTI_IPS_DEPENDENCIES',
        })
    variable = env_requirements.get(name)
    if variable and not os.environ.get(variable):
        return f'{variable} is not configured'
    return None


def build(args):
    WORK.mkdir(exist_ok=True); DIST.mkdir(exist_ok=True)
    family = system()
    available = FORMATS.get(family, ['tar'])
    requested = available if args.formats == 'auto' else list(dict.fromkeys(args.formats.split(',')))
    invalid = set(requested) - set(available)
    if invalid:
        print(f'Unsupported native formats on {family}: {sorted(invalid)}; available: {available}', file=sys.stderr)
        return 2
    if getattr(args, 'auto_deps', False):
        from .auto_dependencies import ensure_dependencies
        ensure_dependencies(requested, args.profile)
    skipped = {}
    if args.formats == 'auto':
        retained = []
        for name in requested:
            reason = format_skip_reason(name, args.profile)
            if reason:
                skipped[name] = {'status': 'skipped', 'reason': reason}
                print(f'{name} skipped: {reason}', file=sys.stderr, flush=True)
            else:
                retained.append(name)
        requested = retained
    report = {'application': 'Openmukti Audiobook Maker', 'version': version(),
              'host': family, 'host_description': platform.uname().version, 'architecture': architecture(),
              'profile': args.profile, 'python_embedded': args.profile == 'frozen',
              'libc': platform.libc_ver() if family == 'linux' else None,
              'runtime_verified': False, 'results': skipped, 'status': 'failed'}
    report_path = DIST / 'build-report.json'
    try:
        payload = freeze() if args.profile == 'frozen' else system_payload(args.python)
        if args.profile == 'system':
            report['system_capabilities'] = verify(payload, args.profile, args.verify_gui, strict=False)
        write(payload / 'BUILD-INFO.json', json.dumps({k:v for k,v in report.items() if k not in ('status','results')}, indent=2) + '\n')
        if args.verify_runtime:
            verify(payload, args.profile, args.verify_gui)
            report['runtime_verified'] = True
            write(payload / 'BUILD-INFO.json', json.dumps({k:v for k,v in report.items() if k not in ('status','results')}, indent=2) + '\n')
        for name in requested:
            # A failed format must not hide the outputs of independent successful packagers.
            try:
                path = PACKAGERS[name](payload, args.profile)
                if not path.is_file() or path.stat().st_size == 0: raise RuntimeError('Packager produced no output')
                report['results'][name] = {'status': 'built', 'file': path.name, 'bytes': path.stat().st_size,
                                            'sha256': digest(path), 'runtime_verified': report['runtime_verified']}
            except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
                report['results'][name] = {'status': 'failed', 'reason': str(exc)}
                print(f'{name} FAILED: {exc}', file=sys.stderr, flush=True)
        states = {r['status'] for r in report['results'].values()}
        report['status'] = 'built' if 'failed' not in states and 'built' in states else 'failed'
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        report['error'] = str(exc)
        print('BUILD FAILED:', exc, file=sys.stderr, flush=True)
    finally:
        write(report_path, json.dumps(report, indent=2) + '\n')
        sums = [r['sha256'] + '  ' + r['file'] for r in report['results'].values() if r['status'] == 'built']
        write(DIST / 'SHA256SUMS.txt', '\n'.join(sums) + ('\n' if sums else ''))
        print('Build report:', report_path, flush=True)
    return 0 if report['status'] == 'built' else 1
