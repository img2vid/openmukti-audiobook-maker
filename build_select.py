"""Interactive host-native format picker for Openmukti builds.

Run with ``python build_select.py`` (or ``py -3 build_select.py`` on Windows).
Only formats implemented for the current host are shown. Native package tools
and signing keys may still be required for the selected format.
"""
from __future__ import annotations

import argparse
import sys

import build
from scripts.build_unix import FORMATS, NATIVE_ARCHES
from scripts.platform_support import architecture, system, windows_arch


LABELS = {
    'tar': 'Portable .tar.xz archive',
    'zip': 'Portable .zip archive',
    'tar-gz': 'Portable .tar.gz archive',
    'tar-zst': 'Portable .tar.zst archive (requires zstd)',
    'wheel': 'Python wheel distribution (not a desktop installer)',
    'sdist': 'Python source distribution (not a desktop installer)',
    'exe': 'Windows standalone EXEs and portable ZIP',
    'deb': 'Debian package (.deb; dpkg-deb required)',
    'rpm': 'RPM package (.rpm; rpmbuild required)',
    'arch': 'Arch package (.pkg.tar.zst; zstd required)',
    'appimage': 'AppImage (frozen profile and AppImage tooling required)',
    'flatpak': 'Flatpak bundle (frozen profile and Flatpak tooling required)',
    'slack-txz': 'Slackware TXZ package archive',
    'slack-tgz': 'Slackware TGZ package archive',
    'apk': 'Alpine APK package (abuild, signing key, dependency list required)',
    'xbps': 'Void XBPS package (xbps-create and dependency list required)',
    'pkg': 'FreeBSD/DragonFly package (native pkg tools required)',
    'bsd-tgz': 'OpenBSD/NetBSD package archive (native pkg_create required)',
    'ips': 'Solaris/illumos IPS package (IPS tools required)',
    'svr4': 'Solaris/illumos SVR4 package (SVR4 tools required)',
    'dmg': 'macOS disk image (.dmg)',
    'mac-pkg': 'macOS installer package (.pkg; unsigned)',
}


def host_formats():
    family = system()
    return ['exe'] if family == 'windows' else list(FORMATS.get(family, ['tar']))


def selected_profile(choice):
    if choice != 'auto':
        return choice
    family = system()
    if family == 'windows':
        return 'frozen'
    arch = architecture()
    if arch in NATIVE_ARCHES.get(family, []):
        return 'frozen'
    return 'system'


def print_formats(formats):
    family = system()
    arch = windows_arch() if family == 'windows' else architecture()
    print(f'Build target for this computer: {family} / {arch}')
    print('Choose one or more implemented formats for this host:')
    for index, name in enumerate(formats, 1):
        print(f'  {index:2}. {name:<12} {LABELS.get(name, name)}')
    print('Enter a number, comma-separated numbers, a format name, or "all".')


def parse_selection(value, formats):
    value = value.strip()
    if value.lower() == 'all':
        return list(formats)
    result = []
    for raw in value.split(','):
        item = raw.strip().lower()
        if not item:
            continue
        if item.isdecimal():
            index = int(item)
            if index < 1 or index > len(formats):
                raise ValueError(f'Choose a number from 1 to {len(formats)}.')
            name = formats[index - 1]
        else:
            name = item
            if name not in formats:
                raise ValueError(f'{name!r} is not available for {system()} on this build host.')
        if name not in result:
            result.append(name)
    if not result:
        raise ValueError('Select at least one format.')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Choose Openmukti build format(s) for this computer')
    parser.add_argument('--formats', help='Comma-separated format names, or all; omit to show the interactive menu')
    parser.add_argument('--profile', choices=['auto', 'frozen', 'system'], default='auto',
                        help='auto selects frozen where configured and system-runtime on other Unix hosts')
    parser.add_argument('--list', action='store_true', help='List formats for this host and exit')
    parser.add_argument('--no-auto-deps', action='store_true', help='Disable automatic dependency installation')
    parser.add_argument('--deps-plan', action='store_true', help='Show dependency commands without installing')
    args = parser.parse_args(argv)
    formats = host_formats()
    if args.list:
        print_formats(formats)
        return 0
    if args.formats:
        try:
            chosen = parse_selection(args.formats, formats)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        print_formats(formats)
        while True:
            try:
                chosen = parse_selection(input('Formats to build: '), formats)
                break
            except ValueError as exc:
                print(f'Invalid selection: {exc}', file=sys.stderr)
    profile = selected_profile(args.profile)
    print(f'Building: {", ".join(chosen)} (profile: {profile})')
    target = 'exe' if system() == 'windows' and chosen == ['exe'] else ','.join(chosen)
    flags = ['--formats', target, '--profile', profile]
    if args.no_auto_deps: flags.append('--no-auto-deps')
    if args.deps_plan: flags.append('--deps-plan')
    return build.main(flags)


if __name__ == '__main__':
    pause = build.single_process_console()
    try:
        result = main()
    except KeyboardInterrupt:
        result = 130
        print('\nBuild selection cancelled.', file=sys.stderr)
    finally:
        if pause:
            try:
                input('\nFinished. Press Enter to close this window...')
            except (EOFError, KeyboardInterrupt, OSError):
                pass
    raise SystemExit(result)
