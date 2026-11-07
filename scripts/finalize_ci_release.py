"""Write accurate GitHub Release notes from build jobs and published assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .prepare_ci_release_assets import EXPECTED_ARTIFACTS
except ImportError:  # Running this file as a standalone CI script.
    from prepare_ci_release_assets import EXPECTED_ARTIFACTS


def summary(needs: dict, asset_names: list[str],
            *, ref: str, run_url: str) -> dict:
    jobs = {name: job.get('result', 'unknown') for name, job in needs.items()}
    uploaded = [name for name in EXPECTED_ARTIFACTS
                if any(asset.startswith(name + '--') and
                       not asset.endswith('--SHA256SUMS.txt')
                       for asset in asset_names)]
    missing = [name for name in EXPECTED_ARTIFACTS if name not in uploaded]
    required = [name for name in jobs if name not in
                ('checks', 'additional-native-runners', 'release-create')]
    failures = [name for name in required if jobs[name] != 'success']
    if jobs.get('additional-native-runners') not in (None, 'success', 'skipped'):
        failures.append('additional-native-runners')
    complete = (not missing and not failures and jobs.get('checks') == 'success')
    version_tag = ref.startswith('refs/tags/v')
    prerelease = not (version_tag and complete)
    title = ('Openmukti ' + ref.removeprefix('refs/tags/')
             if version_tag else 'Openmukti continuous build')
    title += ' — verified' if complete else ' — PARTIAL (platforms missing)'
    notes = [f'Build source: {run_url}', '',
             '**Status:** ' + ('All expected platform outputs are present.'
                               if complete else
                               'INCOMPLETE — some build jobs or uploads failed.'), '',
             f'**Published platforms:** {len(uploaded)} of {len(EXPECTED_ARTIFACTS)}.', '',
             'Distributions come from successful build jobs only. System-runtime',
             'packages still require separately installed native dependencies.',
             'Large files are split into numbered parts with SHA256 verification.',
             '', '**Build jobs:**']
    notes += [f'- {key}: {value}' for key, value in sorted(jobs.items())]
    if missing:
        notes += ['', '**Missing platform artifacts:**']
        notes += [f'- {name}' for name in missing]
    if not complete:
        notes += ['', 'This prerelease is not a fully verified cross-platform release.']
    return {'complete': complete, 'prerelease': prerelease, 'title': title,
            'notes': '\n'.join(notes) + '\n', 'uploaded': uploaded,
            'missing': missing, 'failed_jobs': failures}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('needs_json', type=Path)
    parser.add_argument('assets_json', type=Path)
    parser.add_argument('notes_output', type=Path)
    parser.add_argument('--ref', required=True)
    parser.add_argument('--run-url', required=True)
    args = parser.parse_args(argv)
    needs = json.loads(args.needs_json.read_text(encoding='utf-8'))
    assets = json.loads(args.assets_json.read_text(encoding='utf-8'))
    info = summary(needs, [row['name'] for row in assets],
                   ref=args.ref, run_url=args.run_url)
    args.notes_output.write_text(info['notes'], encoding='utf-8')
    args.notes_output.with_suffix('.json').write_text(
        json.dumps({k: v for k, v in info.items() if k != 'notes'}, indent=2),
        encoding='utf-8')
    print(json.dumps({k: v for k, v in info.items() if k != 'notes'}, indent=2))


if __name__ == '__main__':
    main()
