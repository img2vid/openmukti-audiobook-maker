"""Detect the native OS, then build its supported Openmukti release formats.

Run with ``python build_detect_os.py`` (or ``py -3 build_detect_os.py`` on
Windows). This builds only for the computer running the script; it does not
cross-compile releases for other operating systems.
"""
from __future__ import annotations

import argparse
import sys

import build
from build_select import LABELS, host_formats, parse_selection, selected_profile
from scripts.build_unix import format_skip_reason
from scripts.platform_support import architecture, system, windows_arch


def profile_formats(profile):
    formats = host_formats()
    if profile == 'system':
        # These formats contain a frozen application runtime by design.
        formats = [name for name in formats if name not in {'appimage', 'flatpak', 'dmg'}]
    return formats


def missing_requirement(name, profile):
    return format_skip_reason(name, profile)


def automatic_formats(profile):
    formats = profile_formats(profile)
    selected, skipped = [], []
    for name in formats:
        reason = missing_requirement(name, profile)
        if reason:
            skipped.append((name, reason))
        else:
            selected.append(name)
    return selected, skipped


def main(argv=None):
    parser = argparse.ArgumentParser(description='Detect this computer and build its native Openmukti formats')
    parser.add_argument('--formats', help='Override the detected host format set with comma-separated names')
    parser.add_argument('--profile', choices=['auto', 'frozen', 'system'], default='auto')
    parser.add_argument('--no-auto-deps', action='store_true', help='Disable automatic dependency installation')
    parser.add_argument('--deps-plan', action='store_true', help='Show required install commands without installing')
    args = parser.parse_args(argv)
    family = system()
    arch = windows_arch() if family == 'windows' else architecture()
    profile = selected_profile(args.profile)
    if args.deps_plan:
        return build.main(['--formats', args.formats or 'auto', '--profile', profile, '--deps-plan'])
    requested = profile_formats(profile)
    if args.formats:
        try:
            requested = parse_selection(args.formats, requested)
        except ValueError as exc:
            parser.error(str(exc))
    if not args.no_auto_deps and family != 'windows':
        from scripts.auto_dependencies import ensure_dependencies
        ensure_dependencies(requested, profile)
    if args.formats:
        chosen, skipped = requested, []
    else:
        chosen, skipped = automatic_formats(profile)
    print(f'Detected build host: {family} / {arch}')
    print(f'Runtime profile: {profile}')
    if not chosen:
        print('No implemented formats are available for this host.', file=sys.stderr)
        return 2
    print('Formats to attempt:')
    for name in chosen:
        print(f'  - {name}: {LABELS.get(name, name)}')
    print('Optional native tools may be required. See dist/build-report.json for per-format results.')
    for name, reason in skipped:
        print(f'Skipped {name}: {reason}')
    target = 'exe' if family == 'windows' else ','.join(chosen)
    # Dependencies were already prepared above; never install them twice.
    return build.main(['--formats', target, '--profile', profile, '--no-auto-deps'])


if __name__ == '__main__':
    pause = build.single_process_console()
    try:
        result = main()
    except KeyboardInterrupt:
        result = 130
        print('\nBuild interrupted.', file=sys.stderr)
    finally:
        if pause:
            try:
                input('\nFinished. Press Enter to close this window...')
            except (EOFError, KeyboardInterrupt, OSError):
                pass
    raise SystemExit(result)
