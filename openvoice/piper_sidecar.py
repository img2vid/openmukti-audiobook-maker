from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path


class PiperSidecarError(RuntimeError):
    pass


def find_worker() -> Path | None:
    name = 'OpenmuktiPiperWorker.exe' if os.name == 'nt' else 'OpenmuktiPiperWorker'
    override = os.environ.get('OPENMUKTI_PIPER_WORKER', '').strip()
    bases = [
        Path(getattr(sys, '_MEIPASS', '')) if getattr(sys, '_MEIPASS', '') else None,
        Path(sys.executable).resolve().parent,
        Path(__file__).resolve().parent.parent,
    ]
    paths = [Path(override).expanduser()] if override else []
    for base in bases:
        if base is None:
            continue
        paths.extend((base / 'piper_worker' / name,
                      base / '_internal' / 'piper_worker' / name,
                      base / name))
    for candidate in paths:
        if candidate.is_file():
            return candidate
    return None


def render_with_worker(*, mode: str, model: Path, config: Path, output: Path,
                       ipa: str = '', text: str = '', length_scale: float = 1.0,
                       speaker_id: int | None = None, control=None) -> None:
    worker = find_worker()
    if worker is None:
        raise PiperSidecarError('Piper phoneme worker is missing from this portable build. Rebuild using: py -3 build.py --repair.')
    if control is not None:
        control.check()
    command = [str(worker), '--mode', mode, '--model', str(model), '--config', str(config),
               '--output', str(output), '--length-scale', str(length_scale)]
    if speaker_id is not None:
        command.extend(['--speaker-id', str(speaker_id)])
    if mode == 'ipa':
        command.extend(['--ipa', ipa])
    else:
        command.extend(['--text', text])
    try:
        environment = os.environ.copy()
        if getattr(sys, 'frozen', False) and str(getattr(sys, '_MEIPASS', '')) in str(worker):
            environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=False, timeout=1200, env=environment)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PiperSidecarError(f'Portable Piper worker could not run: {exc}') from exc
    if control is not None:
        control.check()
    if result.returncode != 0:
        message = result.stderr.decode('utf-8', 'replace').strip() or result.stdout.decode('utf-8','replace').strip()
        raise PiperSidecarError(f'Piper worker failed: {message[:1500] or "unknown error"}')
    if not output.is_file() or output.stat().st_size < 44:
        raise PiperSidecarError('Piper worker reported success without producing a valid WAV output')
