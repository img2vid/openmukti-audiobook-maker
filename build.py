"""Single public build entry point for Openmukti on every supported OS.

Windows: py -3 build.py [--repair] [--verify-runtime] [--keep-open]
Other systems: python3 build.py --list-targets

For Windows Explorer double-clicks, the new console is retained after failure
or success so errors cannot disappear immediately. All normal builds create
build-logs/windows-build.log plus windows-build-status.json for recovery.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from scripts.platform_support import architecture, system, windows_arch


def single_process_console() -> bool:
    """True when Windows created a private console for double-clicked Python.

    A terminal-launch (cmd/PowerShell/Windows Terminal) generally shares its
    console with other processes. Detection is best effort; --keep-open may
    be used explicitly if the user wants an unconditional prompt.
    """
    if os.name != 'nt' or not getattr(sys.stdin, 'isatty', lambda: False)():
        return False
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        get_process_list = kernel.GetConsoleProcessList
        get_process_list.argtypes = (ctypes.POINTER(wintypes.DWORD), wintypes.DWORD)
        get_process_list.restype = wintypes.DWORD
        process_ids = (wintypes.DWORD * 32)()
        return get_process_list(process_ids, len(process_ids)) == 1
    except (AttributeError, OSError, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build Openmukti for this computer (no cross compilation)')
    parser.add_argument('--formats', default='auto', help='Comma-separated formats, or auto (see --list-targets)')
    parser.add_argument('--profile', choices=['frozen', 'system'], default='frozen',
                        help='frozen embeds Python/native dependencies; system uses installed Python')
    parser.add_argument('--verify-runtime', action='store_true', help='Test OCR and completed runtime')
    parser.add_argument('--verify-gui', action='store_true', help='Test Tk spelling suggestions and undo (requires a display)')
    parser.add_argument('--list-targets', action='store_true')
    parser.add_argument('--no-auto-deps', action='store_true',
                        help='Skip automatic native dependency installation (for controlled/offline builds)')
    parser.add_argument('--deps-plan', action='store_true',
                        help='Print native dependencies and install commands without making changes')
    parser.add_argument('--python', help='Python 3.10+ command for a system-runtime package')
    # All Windows functionality formerly exposed by build_windows.py is here.
    win = parser.add_mutually_exclusive_group()
    win.add_argument('--repair', '--resume', dest='repair', action='store_true',
                     help='Windows: reuse compatible build environments and existing Piper worker after interruption')
    win.add_argument('--verify-existing', action='store_true',
                     help='Windows: validate/package existing EXEs without rebuilding')
    win.add_argument('--package-existing', action='store_true',
                     help='Windows: package existing EXEs without executing them')
    win.add_argument('--diagnose-policy', action='store_true',
                     help='Windows: diagnose unsigned EXE execution-policy restrictions')
    parser.add_argument('--keep-open', action='store_true',
                        help='Windows: pause before closing so errors remain visible (also automatic when double-clicked)')
    args = parser.parse_args(argv)
    from scripts.build_unix import FORMATS, NATIVE_ARCHES
    if args.list_targets:
        print(json.dumps({'formats': {'windows': ['exe'], **FORMATS},
                          'bundled_runtime_architectures': NATIVE_ARCHES,
                          'system_runtime': 'Any native Unix Python 3.10+ host with the package tool and required providers',
                          'host': system(), 'architecture': windows_arch() if system() == 'windows' else architecture()}, indent=2))
        return 0
    if args.verify_gui:
        args.verify_runtime = True
    args.auto_deps = not args.no_auto_deps
    if args.deps_plan:
        from scripts.auto_dependencies import ensure_dependencies
        formats = (['exe'] if system() == 'windows' else
                   FORMATS.get(system(), ['tar']) if args.formats == 'auto' else args.formats.split(','))
        report = ensure_dependencies(formats, args.profile, dry_run=True)
        print(json.dumps(report, indent=2))
        print('Python wheel dependencies are installed in isolated environments during the actual build.')
        return 0
    if system() == 'windows':
        if args.formats not in ('auto', 'exe') or args.profile != 'frozen':
            parser.error('On Windows use --formats exe --profile frozen; build other targets on their native hosts')
        if args.verify_gui:
            parser.error('--verify-gui is supported only for native Unix builds')
        if args.verify_runtime and (args.verify_existing or args.diagnose_policy or args.package_existing):
            parser.error('--verify-runtime applies to a new build or repair; --verify-existing validates the finished files')
        from scripts.build_windows_py315 import entrypoint
        options = []
        if args.repair: options.append('--repair')
        if args.verify_existing: options.append('--verify-existing')
        if args.package_existing: options.append('--package-existing')
        if args.diagnose_policy: options.append('--diagnose-policy')
        if args.verify_runtime: options.append('--verify-runtime')
        return entrypoint(options)
    if args.repair or args.verify_existing or args.package_existing or args.diagnose_policy or args.keep_open:
        parser.error('Windows-specific options require Windows')
    from scripts.build_unix import build
    return build(args)


if __name__ == '__main__':
    # Inspect before running: Windows GUI double-click creates a solitary console.
    # Do not pause unattended workflows or terminals that already stay open.
    pause = ('--keep-open' in sys.argv[1:]) or single_process_console()
    result = 1
    try:
        result = main()
    except KeyboardInterrupt:
        print('\nBuild interrupted. Existing logs are in build-logs/; rerun with --repair.', file=sys.stderr)
        result = 130
    except Exception:
        traceback.print_exc()
        print('\nBuild failed. On Windows, check build-logs/windows-build.log. '
              'Rerun with: py -3 build.py --repair', file=sys.stderr)
        result = 1
    finally:
        if pause and os.name == 'nt':
            try:
                input('\nBuild finished or stopped. Press Enter to close this window...')
            except (EOFError, KeyboardInterrupt, OSError):
                pass
    raise SystemExit(result)
