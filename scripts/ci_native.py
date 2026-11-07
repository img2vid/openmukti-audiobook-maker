"""Prepare native BSD/Solaris dependency receipts and run their system packages.

Package installation belongs to the disposable CI VM, never to the application.
Unavailable optional native libraries are recorded in dist, not reported as bundled.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.platform_support import system


def query(*command, privileged=False):
    if privileged:
        from scripts.auto_dependencies import as_admin
        command = as_admin(list(command))
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)



def installed_ips_fmris(lines: str, names: list[str]) -> list[str]:
    """Select actual installed-package FMRIs instead of fabricating dependencies."""
    chosen = set(names)
    result = []
    for line in lines.splitlines():
        fields = line.strip().split()
        if not fields or not fields[0].startswith(('pkg://', 'pkg:/')):
            continue
        fmri = fields[0]
        name = fmri.split('@', 1)[0].removeprefix('pkg:/')
        if name.startswith('/'):
            name = name[1:]
            name = name.split('/', 1)[1] if '/' in name else ''
        if name in chosen and fmri not in result:
            result.append(fmri)
    return result


def ips_packages_for_python(major: int, minor: int) -> list[str]:
    """Request packages matching the interpreter actually running in the VM.

    OmniOS r151054 uses Python 3.13, so fixed python-311 package names
    could never match that host's installed IPS inventory.
    """
    version = f'{major}{minor}'
    return [f'runtime/python-{version}', f'library/python/tkinter-{version}',
            'image/tesseract', 'image/library/opencv', 'image/library/pillow',
            'library/python/numpy', 'video/ffmpeg', 'print/filter/poppler']


def main(*, install_only=False):
    family = system()
    attempts = []
    deps = {}
    bsd_deps = []
    ips_deps = []
    if family in ('freebsd', 'dragonfly'):
        py = f'py{sys.version_info.major}{sys.version_info.minor}'
        packages = ['python' + f'{sys.version_info.major}{sys.version_info.minor}', py + '-tkinter',
                    py + '-pillow', py + '-numpy', py + '-opencv', 'tesseract', 'tesseract-data',
                    'ffmpeg', 'poppler-utils', 'espeak-ng', 'piper-tts']
        for package in packages:
            installed = query('pkg', 'install', '-y', package, privileged=True)
            attempts.append({'package': package, 'installed': installed.returncode == 0,
                             'detail': (installed.stderr + installed.stdout)[-1500:]})
            receipt = query('pkg', 'query', '%n\t%o\t%v', package)
            for line in receipt.stdout.splitlines():
                fields = line.split('\t')
                if len(fields) == 3:
                    name, origin, release = fields
                    deps[name] = {'origin': origin, 'version': release}
        os.environ['OPENMUKTI_PKG_DEPENDENCIES'] = json.dumps(deps)
    elif family == 'openbsd':
        packages = [f'python-tkinter%{sys.version_info.major}.{sys.version_info.minor}', 'py3-Pillow', 'py3-numpy', 'py3-opencv', 'tesseract',
                    'tesseract-eng', 'tesseract-osd', 'ffmpeg', 'poppler-utils', 'espeak', 'piper']
        for package in packages:
            installed = query('pkg_add', '-I', package, privileged=True)
            attempts.append({'package': package, 'installed': installed.returncode == 0,
                             'detail': (installed.stderr + installed.stdout)[-1500:]})
        # Use pkg_create's native pkgpath:pkgspec:default representation.
        for contents in Path('/var/db/pkg').glob('*/+CONTENTS'):
            text = contents.read_text(errors='replace')
            path = next((x.split('=', 1)[1] for x in text.splitlines() if x.startswith('@comment pkgpath=')), None)
            name = contents.parent.name
            if path and any(name.startswith(p.split('%')[0] + '-') for p in ['python'] + packages):
                bsd_deps.append(path + ':=:' + name)
        os.environ['OPENMUKTI_BSD_DEPENDENCIES'] = json.dumps(bsd_deps)
    elif family == 'netbsd':
        py = f'py{sys.version_info.major}{sys.version_info.minor}'
        packages = ['python' + f'{sys.version_info.major}{sys.version_info.minor}', py + '-Tk', py + '-Pillow',
                    py + '-numpy', py + '-opencv', 'tesseract', 'tesseract-data-eng', 'tesseract-data-osd',
                    'ffmpeg6', 'poppler-utils', 'espeak-ng', 'piper-tts']
        for package in packages:
            installed = query('/usr/sbin/pkg_add', '-u', package, privileged=True)
            attempts.append({'package': package, 'installed': installed.returncode == 0,
                             'detail': (installed.stderr + installed.stdout)[-1500:]})
        output = query('/usr/sbin/pkg_info', '-a').stdout
        for line in output.splitlines():
            name = line.split()[0]
            if any(name.startswith(p + '-') for p in packages): bsd_deps.append(name)
        os.environ['OPENMUKTI_BSD_DEPENDENCIES'] = json.dumps(bsd_deps)
    elif family in ('solaris', 'illumos'):
        # Search the configured IPS publishers rather than assuming third-party repositories.
        packages = ips_packages_for_python(sys.version_info.major, sys.version_info.minor)
        for package in packages:
            installed = query('pkg', 'install', '--accept', package, privileged=True)
            attempts.append({'package': package, 'installed': installed.returncode in (0, 4),
                             'detail': (installed.stderr + installed.stdout)[-1500:]})
        # Installed FMRIs, including publisher names, are authoritative. The
        # previous per-package pattern was empty on OmniOS and broke IPS.
        receipt = query('pkg', 'list', '-Hv')
        if receipt.returncode != 0:
            attempts.append({'package': 'installed IPS inventory', 'installed': False,
                             'detail': (receipt.stderr + receipt.stdout)[-1500:]})
        ips_deps = installed_ips_fmris(receipt.stdout if receipt.returncode == 0 else '', packages)
        if not ips_deps:
            # Do not generate made-up package dependencies or silently mark
            # an incomplete native IPS package as successful. Log enough
            # inventory context to diagnose the next VM image change.
            print('IPS dependency discovery failed:', json.dumps({
                'python': sys.version.split()[0],
                'requested': packages,
                'inventory_exit_code': receipt.returncode,
                'inventory_stderr': receipt.stderr[-1500:],
                'python_inventory': [
                    line for line in receipt.stdout.splitlines()
                    if 'python' in line.lower()
                ][:25],
                'inventory_sample': receipt.stdout.splitlines()[:8],
            }), flush=True)
        print('Installed IPS dependency FMRIs:', json.dumps(ips_deps), flush=True)
        os.environ['OPENMUKTI_IPS_DEPENDENCIES'] = json.dumps(ips_deps)
    else:
        raise RuntimeError('This CI preparer is for the BSD and Solaris/illumos jobs')
    dist = ROOT / 'dist'; dist.mkdir(exist_ok=True)
    (dist / 'provider-installation.json').write_text(json.dumps(attempts, indent=2) + '\n')
    # The native compiler/package tool decides availability. Missing dependencies
    # are visible in runtime-check.json; these are system-runtime packages.
    if install_only:
        return 0
    return subprocess.call([sys.executable, str(ROOT / 'build.py'), '--profile', 'system', '--python', sys.executable, '--no-auto-deps'])


if __name__ == '__main__':
    raise SystemExit(main())
