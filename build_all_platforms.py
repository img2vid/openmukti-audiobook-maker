"""Start the native multi-OS build matrix from a Windows or Ubuntu checkout.

This coordinates GitHub Actions; it does not pretend to cross-compile native
Windows, macOS, BSD, or Solaris binaries on the local computer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / '.github' / 'workflows' / 'build.yml'
NATIVE_MATRIX = (
    'Windows x64 and ARM64; Linux x86_64 and ARM64 plus configured extra Linux architectures; '
    'macOS x86_64 and ARM64; FreeBSD x86_64 and ARM64; OpenBSD x86_64 and ARM64; '
    'NetBSD x86_64 and ARM64; DragonFly BSD x86_64; Solaris x86_64; illumos x86_64. '
    'AIX and other rare targets need configured self-hosted runners.'
)


def command(args, *, capture=False, check=True, timeout=None):
    print('+', ' '.join(str(item) for item in args), flush=True)
    return subprocess.run(
        [str(item) for item in args], cwd=ROOT, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=check, timeout=timeout,
    )


def output(args):
    result = command(args, capture=True)
    return result.stdout.strip()


def plan():
    print('This launcher can be run from Windows or Ubuntu.')
    print('It dispatches the repository workflow to native GitHub-hosted runners, then downloads the artifacts.')
    print(NATIVE_MATRIX)
    print('Formats not implemented by the workflow or requiring an application port are not created.')
    print('Requirements: push this source version to GitHub and authorize GitHub CLI. Missing Git/gh are installed automatically where supported.')


def resolve_ref(value):
    if value:
        return value
    branch = output(['git', 'branch', '--show-current'])
    if not branch:
        raise RuntimeError('Could not determine the current branch; pass --ref explicitly.')
    return branch


def require_pushed_commit(ref, repo):
    local_commit = output(['git', 'rev-parse', 'HEAD'])
    dirty = output(['git', 'status', '--porcelain'])
    if dirty:
        raise RuntimeError('Commit and push the build files before dispatching; the working tree has uncommitted changes.')
    if repo:
        remote_commit = output(['gh', 'api', f'repos/{repo}/commits/{ref}', '--jq', '.sha'])
    else:
        result = command(['git', 'ls-remote', '--heads', 'origin', f'refs/heads/{ref}'], capture=True)
        remote_commit = result.stdout.split()[0] if result.stdout.split() else ''
    if not remote_commit:
        raise RuntimeError(f'Could not find branch {ref!r} on the remote. Push it or pass the correct --repo and --ref.')
    if remote_commit != local_commit:
        raise RuntimeError(
            f'Branch {ref!r} on GitHub is not at the current commit. Push this exact commit, then run the launcher again.'
        )
    return local_commit


def run_id_from_dispatch(text):
    matches = re.findall(r'/actions/runs/(\d+)', text)
    return matches[-1] if matches else None


def find_dispatched_run(ref, repo, commit, started):
    args = ['gh', 'run', 'list', '--workflow', 'build.yml', '--branch', ref,
            '--event', 'workflow_dispatch', '--limit', '20', '--json',
            'databaseId,createdAt,headSha,event,workflowName']
    if repo:
        args += ['--repo', repo]
    runs = json.loads(output(args) or '[]')
    for item in runs:
        created = datetime.fromisoformat(item['createdAt'].replace('Z', '+00:00'))
        if item.get('headSha') == commit and created.timestamp() >= started - 60:
            return str(item['databaseId'])
    return None


def unique_destination(base):
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = base.with_name(base.name + f'-{suffix}')
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Build the configured native platform matrix from a Windows or Ubuntu GitHub checkout'
    )
    parser.add_argument('--plan', action='store_true', help='Show which native runner jobs the workflow dispatches')
    parser.add_argument('--no-auto-deps', action='store_true', help='Do not automatically install missing Git/GitHub CLI')
    parser.add_argument('--ref', help='Pushed branch to build; defaults to the current Git branch')
    parser.add_argument('--repo', help='GitHub OWNER/REPOSITORY; defaults to the checkout origin')
    parser.add_argument('--timeout-minutes', type=int, default=240, help='Maximum wait time for the workflow (default: 240)')
    parser.add_argument('--download-dir', help='Artifact parent directory; defaults to dist/all-platforms-<run-id>')
    args = parser.parse_args(argv)
    if args.plan:
        plan()
        return 0
    if args.timeout_minutes < 1:
        parser.error('--timeout-minutes must be at least 1')
    if not WORKFLOW.is_file() or 'workflow_dispatch:' not in WORKFLOW.read_text(encoding='utf-8'):
        raise RuntimeError('The repository build.yml does not include a workflow_dispatch trigger.')
    if not args.no_auto_deps and (not shutil.which('gh') or not shutil.which('git')):
        from scripts.auto_dependencies import ensure_dependencies
        ensure_dependencies([], profile='system', cli_tools=('git', 'gh'), cli_only=True)
    if not shutil.which('gh'):
        raise RuntimeError('GitHub CLI (gh) is required. Install it on Windows or Ubuntu, then run gh auth login.')
    if not shutil.which('git'):
        raise RuntimeError('Git is required. Run this script from a GitHub checkout of the project.')
    auth = command(['gh', 'auth', 'status'], check=False, capture=True)
    if auth.returncode:
        if sys.stdin.isatty():
            print('GitHub authorization required. Starting the official interactive gh login.', flush=True)
            command(['gh', 'auth', 'login'])
            command(['gh', 'auth', 'status'])
        else:
            raise RuntimeError('GitHub authorization required: run gh auth login in an interactive terminal')
    ref = resolve_ref(args.ref)
    commit = require_pushed_commit(ref, args.repo)
    started = time.time()
    dispatch = ['gh', 'workflow', 'run', 'build.yml', '--ref', ref]
    if args.repo:
        dispatch += ['--repo', args.repo]
    result = command(dispatch, capture=True)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    run_id = run_id_from_dispatch(result.stdout + '\n' + result.stderr)
    if not run_id:
        run_id = find_dispatched_run(ref, args.repo, commit, started)
    if not run_id:
        raise RuntimeError('GitHub accepted the dispatch, but its run ID could not be resolved. Check the Actions page for this repository.')
    print(f'Watching native platform build run {run_id}...', flush=True)
    watch = ['gh', 'run', 'watch', run_id, '--exit-status']
    if args.repo:
        watch += ['--repo', args.repo]
    watch_code = 0
    try:
        watched = command(watch, check=False, timeout=args.timeout_minutes * 60)
        watch_code = watched.returncode
    except subprocess.TimeoutExpired:
        print(f'Wait limit reached. The workflow is still available as run {run_id}.', file=sys.stderr)
        return 124
    destination = Path(args.download_dir).expanduser() if args.download_dir else ROOT / 'dist' / f'all-platforms-{run_id}'
    destination = unique_destination(destination.resolve())
    download = ['gh', 'run', 'download', run_id, '--dir', destination]
    if args.repo:
        download += ['--repo', args.repo]
    downloaded = command(download, check=False)
    if downloaded.returncode:
        print('Artifact download failed. The completed run remains available in GitHub Actions.', file=sys.stderr)
        return downloaded.returncode
    print(f'Artifacts downloaded to: {destination}')
    if watch_code:
        print('One or more native runner jobs failed; the available successful artifacts were downloaded.', file=sys.stderr)
        return watch_code
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f'Build-all launcher: {exc}', file=sys.stderr)
        raise SystemExit(1)
