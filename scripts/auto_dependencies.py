"""Install build prerequisites with the host's trusted package manager.

This runs before format detection. It never claims that a native package can be
built on the wrong OS, installs through native repositories (not curl | sh),
and records any unresolved prerequisites. Elevated operations may prompt for
an administrator password. A working Python 3.10+ and internet access are the
initial prerequisites for running this Python source file.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .platform_support import system

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / '.build-native' / 'dependency-setup.json'

# Each value is a package provided by the normal, configured OS repositories.
# None means that this distro has no known, trustworthy automated installer
# for the named tool: don't invent an installer or silently skip the problem.
LINUX_PACKAGES = {
    'apt': {
        'python-venv': 'python3-venv', 'python-tk': 'python3-tk',
        'tesseract': 'tesseract-ocr', 'tesseract-eng': 'tesseract-ocr-eng',
        'tesseract-osd': 'tesseract-ocr-osd', 'ffmpeg': 'ffmpeg', 'espeak-ng': 'espeak-ng',
        'zstd': 'zstd', 'dpkg-deb': 'dpkg', 'rpmbuild': 'rpm', 'rpm': 'rpm',
        'flatpak': 'flatpak', 'flatpak-builder': 'flatpak-builder',
        'libfuse': 'libfuse2', 'git': 'git', 'gh': 'gh',
        'Pillow': 'python3-pil', 'numpy': 'python3-numpy', 'cv2': 'python3-opencv',
    },
    'dnf': {
        'python-venv': 'python3', 'python-tk': 'python3-tkinter',
        'tesseract': 'tesseract', 'tesseract-eng': 'tesseract-langpack-eng',
        'tesseract-osd': 'tesseract-langpack-osd', 'ffmpeg': 'ffmpeg', 'espeak-ng': 'espeak-ng',
        'zstd': 'zstd', 'dpkg-deb': 'dpkg', 'rpmbuild': 'rpm-build', 'rpm': 'rpm',
        'flatpak': 'flatpak', 'flatpak-builder': 'flatpak-builder',
        'libfuse': 'fuse-libs', 'git': 'git', 'gh': 'gh',
        'Pillow': 'python3-pillow', 'numpy': 'python3-numpy', 'cv2': 'python3-opencv',
    },
    'pacman': {
        'python-venv': 'python', 'python-tk': 'tk',
        'tesseract': 'tesseract', 'tesseract-eng': 'tesseract-data-eng',
        'tesseract-osd': 'tesseract-data-osd', 'ffmpeg': 'ffmpeg', 'espeak-ng': 'espeak-ng',
        'zstd': 'zstd', 'dpkg-deb': 'dpkg', 'rpmbuild': 'rpm-tools', 'rpm': 'rpm-tools',
        'flatpak': 'flatpak', 'flatpak-builder': 'flatpak-builder',
        'libfuse': 'fuse2', 'git': 'git', 'gh': 'github-cli',
        'Pillow': 'python-pillow', 'numpy': 'python-numpy', 'cv2': 'opencv',
    },
    'zypper': {
        'python-venv': 'python3', 'python-tk': 'python3-tk',
        'tesseract': 'tesseract-ocr', 'tesseract-eng': 'tesseract-ocr-traineddata-english',
        'tesseract-osd': 'tesseract-ocr-traineddata-orientation_and_script_detection',
        'ffmpeg': 'ffmpeg', 'espeak-ng': 'espeak-ng', 'zstd': 'zstd',
        'dpkg-deb': 'dpkg', 'rpmbuild': 'rpm-build', 'rpm': 'rpm',
        'flatpak': 'flatpak', 'flatpak-builder': 'flatpak-builder',
        'libfuse': 'libfuse2', 'git': 'git', 'gh': 'gh',
        'Pillow': 'python3-Pillow', 'numpy': 'python3-numpy', 'cv2': 'python3-opencv',
    },
    'apk': {
        'python-venv': 'python3', 'python-tk': 'tk',
        'tesseract': 'tesseract-ocr', 'tesseract-eng': 'tesseract-ocr-data-eng',
        'tesseract-osd': 'tesseract-ocr-data-osd',
        'ffmpeg': 'ffmpeg', 'espeak-ng': 'espeak-ng', 'zstd': 'zstd',
        'dpkg-deb': 'dpkg', 'rpmbuild': 'rpm', 'rpm': 'rpm',
        'flatpak': 'flatpak', 'flatpak-builder': 'flatpak-builder',
        'abuild': 'alpine-sdk', 'git': 'git', 'gh': 'github-cli',
        'Pillow': 'py3-pillow', 'numpy': 'py3-numpy', 'cv2': 'py3-opencv',
    },
    'xbps': {
        'python-venv': 'python3', 'python-tk': 'python3-tkinter',
        'tesseract': 'tesseract', 'tesseract-eng': 'tesseract-ocr-data-eng',
        'tesseract-osd': 'tesseract-ocr-data-osd', 'ffmpeg': 'ffmpeg',
        'espeak-ng': 'espeak-ng', 'zstd': 'zstd', 'dpkg-deb': 'dpkg',
        'rpmbuild': 'rpm', 'rpm': 'rpm', 'flatpak': 'flatpak',
        'flatpak-builder': 'flatpak-builder', 'git': 'git', 'gh': 'github-cli',
        'Pillow': 'python3-Pillow', 'numpy': 'python3-numpy', 'cv2': 'python3-opencv',
        'xbps-create': 'xbps', 'xbps-uhelper': 'xbps',
    },
}

FORMAT_TOOLS = {
    'tar-zst': ('zstd',), 'arch': ('zstd',), 'slack-txz': ('xz',),
    'deb': ('dpkg-deb',), 'rpm': ('rpmbuild', 'rpm'),
    'flatpak': ('flatpak', 'flatpak-builder'),
    'apk': ('abuild',), 'xbps': ('xbps-create', 'xbps-uhelper'),
    'pkg': ('pkg',), 'bsd-tgz': ('pkg_create',),
    'ips': ('pkgrepo', 'pkgsend', 'pkgrecv'), 'svr4': ('pkgmk', 'pkgtrans'),
    'dmg': ('hdiutil',), 'mac-pkg': ('pkgbuild',),
}


def linux_manager():
    """Use only an actual known manager, respecting the host's distro family."""
    release = {}
    try:
        for line in Path('/etc/os-release').read_text(encoding='utf-8').splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                release[key] = value.strip().strip('"\'')
    except OSError:
        pass
    words = (release.get('ID', '') + ' ' + release.get('ID_LIKE', '')).lower().split()
    preferences = (
        ('apt', {'debian', 'ubuntu', 'linuxmint', 'pop', 'raspbian', 'kali'}),
        ('dnf', {'fedora', 'rhel', 'centos', 'rocky', 'almalinux', 'ol'}),
        ('pacman', {'arch', 'manjaro', 'endeavouros'}),
        ('zypper', {'opensuse', 'opensuse-leap', 'opensuse-tumbleweed', 'suse', 'sles'}),
        ('apk', {'alpine'}),
        ('xbps', {'void'}),
    )
    candidates = [manager for manager, ids in preferences if ids.intersection(words)]
    candidates += [x for x in ('apt', 'dnf', 'pacman', 'zypper', 'apk', 'xbps') if x not in candidates]
    commands = {'apt': 'apt-get', 'dnf': 'dnf', 'pacman': 'pacman',
                'zypper': 'zypper', 'apk': 'apk', 'xbps': 'xbps-install'}
    for candidate in candidates:
        if shutil.which(commands[candidate]):
            return candidate, commands[candidate]
    return None, None


def as_admin(command):
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        return command
    sudo = shutil.which('sudo')
    if sudo:
        return [sudo, *(['-n'] if not sys.stdin.isatty() else []), *command]
    return command  # May succeed in a user-scoped manager; otherwise show failure.


def needed_tools(formats, profile, family, *, cli_only=False):
    ordered = []
    def add(name):
        if name not in ordered:
            ordered.append(name)
    if cli_only:
        return ordered
    if family == 'linux':
        if profile == 'frozen' or set(formats).intersection({'wheel', 'sdist'}):
            add('python-venv')
        add('python-tk')
        for item in ('tesseract', 'tesseract-eng', 'tesseract-osd', 'ffmpeg', 'espeak-ng'):
            add(item)
        if profile == 'system':
            for item in ('Pillow', 'numpy', 'cv2'):
                add(item)
        # The AppImage builder extracts verified appimagetool before running it;
        # FUSE is not needed merely to produce the AppImage archive.
    elif family == 'macos':
        for item in ('tesseract', 'ffmpeg', 'espeak-ng'):
            add(item)
    for fmt in formats:
        for tool in FORMAT_TOOLS.get(fmt, ()):
            add(tool)
    return ordered


def installed(tool, *, family):
    if tool == 'python-venv':
        return importlib.util.find_spec('venv') is not None and importlib.util.find_spec('ensurepip') is not None
    if tool == 'python-tk':
        return importlib.util.find_spec('tkinter') is not None
    if tool in ('Pillow', 'numpy', 'cv2'):
        return importlib.util.find_spec('PIL' if tool == 'Pillow' else tool) is not None
    if tool == 'tesseract-eng' or tool == 'tesseract-osd':
        binary = shutil.which('tesseract')
        if not binary:
            return False
        try:
            result = subprocess.run([binary, '--list-langs'], capture_output=True,
                                    text=True, timeout=20, check=False)
            return tool.rsplit('-', 1)[-1] in result.stdout.splitlines()
        except (OSError, subprocess.TimeoutExpired):
            return False
    if tool == 'libfuse':
        return any(Path(p).exists() for p in ('/lib/x86_64-linux-gnu/libfuse.so.2',
                                            '/usr/lib/x86_64-linux-gnu/libfuse.so.2',
                                            '/usr/lib/libfuse.so.2'))
    return shutil.which(tool) is not None


def install_command(manager, executable, package):
    if manager == 'apt': return as_admin([executable, 'install', '-y', '--no-install-recommends', package])
    if manager == 'dnf': return as_admin([executable, 'install', '-y', package])
    if manager == 'pacman': return as_admin([executable, '-S', '--needed', '--noconfirm', package])
    if manager == 'zypper': return as_admin([executable, '--non-interactive', 'install', package])
    if manager == 'apk': return as_admin([executable, 'add', package])
    if manager == 'xbps': return as_admin([executable, '-Sy', package])
    if manager == 'brew': return [executable, 'install', package]
    if manager == 'winget': return [executable, 'install', '--id', package, '--exact',
                                    '--accept-package-agreements', '--accept-source-agreements']
    raise ValueError('Unknown installer: ' + manager)


def run_install(command, *, dry_run):
    print('[auto-deps] ' + ' '.join(str(x) for x in command), flush=True)
    if dry_run:
        return True, 'planned (not executed)'
    try:
        result = subprocess.run(command, check=False)
        return result.returncode == 0, 'exit status ' + str(result.returncode)
    except OSError as exc:
        return False, str(exc)


def ensure_dependencies(formats=(), profile='frozen', *, dry_run=False, cli_tools=(), cli_only=False, report_path=None):
    """Attempt native installs; never hide errors or pretend missing tools exist.

    All Python packages required by frozen builds are installed separately by
    the isolated venv build script. This step supplies system/native tools.
    """
    family = system()
    formats = list(dict.fromkeys(formats))
    result = {'host': family, 'profile': profile, 'formats': formats,
              'dry_run': dry_run, 'tools': {}, 'warnings': []}
    if family == 'linux':
        manager, executable = linux_manager()
    elif family == 'macos':
        manager, executable = 'brew', shutil.which('brew')
    elif family == 'windows':
        manager, executable = 'winget', shutil.which('winget')
    else:
        manager = executable = None
    result['package_manager'] = manager
    requested = needed_tools(formats, profile, family, cli_only=cli_only)
    for tool in cli_tools:
        if tool not in requested:
            requested.append(tool)
    if family in ('freebsd', 'dragonfly', 'openbsd', 'netbsd', 'solaris', 'illumos') and not dry_run and not cli_only:
        # Uses the same tested native package selection as the VM jobs, and
        # also sets package dependency metadata for pkg/pkg_create/IPS.
        from .ci_native import main as prepare_native
        try:
            prepare_native(install_only=True)
        except (OSError, RuntimeError, ValueError) as exc:
            result['warnings'].append(f'Native provider installation failed: {exc}')
    needs_downloads = any(not installed(tool, family=family) and
                          (tool in LINUX_PACKAGES.get(manager, {}) or family != 'linux')
                          for tool in requested)
    if manager == 'apt' and executable and needs_downloads:
        # apt lists may be empty on new Ubuntu/Debian images; refresh only when needed.
        ok, detail = run_install(as_admin([executable, 'update']), dry_run=dry_run)
        if not ok:
            result['warnings'].append('apt-get update failed: ' + detail)
    attempted = {}
    for tool in requested:
        if installed(tool, family=family):
            result['tools'][tool] = {'status': 'present'}
            continue
        package = None
        if family == 'linux' and manager:
            package = LINUX_PACKAGES.get(manager, {}).get(tool)
        elif family == 'macos':
            package = {'tesseract': 'tesseract', 'ffmpeg': 'ffmpeg',
                       'espeak-ng': 'espeak-ng', 'zstd': 'zstd',
                       'gh': 'gh', 'git': 'git'}.get(tool)
        elif family == 'windows':
            package = {'gh': 'GitHub.cli', 'git': 'Git.Git'}.get(tool)
        if package is None or executable is None:
            result['tools'][tool] = {'status': 'unavailable', 'detail':
                f'No trusted automatic package installation available for {tool} on {family} ({manager or "no manager"})'}
            continue
        if package in attempted:
            ok, detail = attempted[package]
        else:
            command = install_command(manager, executable, package)
            ok, detail = run_install(command, dry_run=dry_run)
            attempted[package] = (ok, detail)
        if dry_run:
            status = 'planned' if ok else 'failed'
        else:
            status = 'installed' if installed(tool, family=family) else 'unavailable'
        result['tools'][tool] = {'status': status, 'package': package, 'detail': detail}
    if family == 'linux' and 'flatpak' in formats and shutil.which('flatpak') and not dry_run:
        result['flatpak_remote'] = 'present'
        check = subprocess.run(['flatpak', 'remotes', '--user', '--columns=name'], capture_output=True, text=True)
        if check.returncode or 'flathub' not in check.stdout.splitlines():
            remote = ['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub',
                      'https://flathub.org/repo/flathub.flatpakrepo']
            ok, detail = run_install(remote, dry_run=False)
            result['flatpak_remote'] = 'configured' if ok else 'unavailable: ' + detail
    if not dry_run:
        file = Path(report_path) if report_path else REPORT
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    bad = [f'{name}: {value.get("detail", "")}' for name, value in result['tools'].items()
           if value['status'] in ('failed', 'unavailable')]
    if bad:
        print('[auto-deps] Unavailable tools (see .build-native/dependency-setup.json):\n  - '
              + '\n  - '.join(bad), file=sys.stderr, flush=True)
    return result


def ensure_pip(python):
    """Enable pip inside an already-created virtual environment if it is missing."""
    probe = subprocess.run([str(python), '-m', 'pip', '--version'], capture_output=True, check=False)
    if probe.returncode:
        subprocess.run([str(python), '-m', 'ensurepip', '--upgrade'], check=True)
