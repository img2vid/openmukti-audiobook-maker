"""Explicitly installed, isolated CPU-only environments for neural engines.

The GUI can install engine packages after a user confirms voice downloading or
clicks Install / repair. Model weights are separately approved and never
requested as a side effect of synthesis.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CPU_WHEEL_INDEX = 'https://download.pytorch.org/whl/cpu'
KITTEN_WHEEL = 'https://github.com/KittenML/KittenTTS/releases/download/0.8.1/kittentts-0.8.1-py3-none-any.whl'
NEURAL_ENGINES = ('kokoro', 'kitten', 'pocket', 'coqui')
DEFAULT_MODELS = {
    'kokoro': 'hexgrad/Kokoro-82M',
    'kitten': 'KittenML/kitten-tts-nano-0.8',
    'pocket': '',  # upstream TTSModel.load_model default
    'coqui': 'tts_models/en/ljspeech/tacotron2-DDC',
}
DEFAULT_VOICES = {'kokoro': 'af_heart', 'kitten': 'Bella', 'pocket': 'alba', 'coqui': ''}
KOKORO_VOICES = tuple('''af_alloy af_aoede af_bella af_heart af_jessica af_kore af_nicole af_nova af_river af_sarah af_sky
am_adam am_echo am_eric am_fenrir am_liam am_michael am_onyx am_puck am_santa
bf_alice bf_emma bf_isabella bf_lily bm_daniel bm_fable bm_george bm_lewis
ef_dora em_alex em_santa ff_siwis hf_alpha hf_beta hm_omega hm_psi
if_sara im_nicola jf_alpha jf_gongitsune jf_nezumi jf_tebukuro jm_kumo
pf_dora pm_alex pm_santa zf_xiaobei zf_xiaoni zf_xiaoxiao zf_xiaoyi
zm_yunjian zm_yunxi zm_yunxia zm_yunyang'''.split())
KITTEN_VOICES = ('Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo')
POCKET_VOICES = tuple('''alba giovanni lola juergen rafael estelle anna azelma bill_boerst caro_davy charles
cosette eponine eve fantine george jane jean javert marius mary michael paul peter_yearsley stuart_bell vera'''.split())

_install_locks = {key: threading.RLock() for key in NEURAL_ENGINES}


def cache_home() -> Path:
    configured = os.environ.get('OPENMUKTI_NEURAL_HOME', '').strip()
    if configured:
        return Path(configured).expanduser()
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))
    elif sys.platform == 'darwin':
        base = str(Path.home() / 'Library/Application Support')
    else:
        base = os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))
    return Path(base) / 'OpenmuktiAudiobookMaker' / 'neural-engines'


def python_path(engine: str) -> Path:
    if engine not in NEURAL_ENGINES:
        raise ValueError(f'Unknown neural engine: {engine}')
    base = cache_home() / engine / '.venv'
    return base / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def is_installed(engine: str) -> bool:
    return python_path(engine).is_file() and (cache_home() / engine / '.ready').is_file()


def bundled_uv() -> str | None:
    """Find the verified build-bundled uv executable, or an installed copy."""
    suffix = '.exe' if os.name == 'nt' else ''
    frozen_root = Path(getattr(sys, '_MEIPASS', '') or '')
    candidates = []
    if getattr(sys, 'frozen', False):
        candidates += [frozen_root / 'uv' / ('uv' + suffix), frozen_root / ('uv' + suffix)]
    source_root = Path(__file__).resolve().parents[1]
    candidates += [source_root / '.build-venv' / ('Scripts' if os.name == 'nt' else 'bin') / ('uv' + suffix),
                   source_root / '.build-native' / 'venv' / 'bin' / 'uv']
    for binary in candidates:
        if binary.is_file():
            return str(binary)
    return shutil.which('uv')


def _python_candidate() -> list[str]:
    # Frozen GUI executable is NOT a Python interpreter. Choose any compatible
    # installed interpreter, with Python 3.12 preferred when it is available.
    candidates = []
    if os.name == 'nt':
        py = shutil.which('py')
        if py:
            candidates.extend([[py, '-3.12'], [py, '-3.11'], [py, '-3.13'], [py, '-3.14']])
    for cmd in ('python3.12', 'python3.11', 'python3.13', 'python3.14', 'python3.10', 'python3', 'python'):
        binary = shutil.which(cmd)
        if binary:
            candidates.append([binary])
    if not getattr(sys, 'frozen', False) and (3, 10) <= sys.version_info[:2] < (3, 15):
        candidates.append([sys.executable])
    seen = set()
    for candidate in candidates:
        if tuple(candidate) in seen:
            continue
        seen.add(tuple(candidate))
        try:
            probe = subprocess.run(candidate + ['-c', 'import sys; print(sys.version_info.major, sys.version_info.minor)'],
                                   capture_output=True, text=True, timeout=15, check=False)
            version = tuple(map(int, probe.stdout.strip().split()))
            if probe.returncode == 0 and (3, 10) <= version < (3, 15):
                return candidate
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    raise RuntimeError('A compatible Python 3.10–3.14 interpreter is not installed. '
                       'The built-in uv bootstrap can download Python 3.12 automatically '
                       'if uv is bundled or available on PATH.')


def install_plan(engine: str) -> list[list[str]]:
    """Return pip command arguments, not including Python/-m pip.

    Torch CPU index MUST be applied before installing other packages. Ordinary
    Linux PyPI torch wheels may otherwise pull gigabytes of CUDA dependencies.
    """
    if engine not in NEURAL_ENGINES:
        raise ValueError(f'Unknown neural engine: {engine}')
    base = ['install', '--disable-pip-version-check', '--prefer-binary', '--no-input']
    # Kokoro uses torch but not torchaudio. Avoid forcing an unnecessary
    # heavyweight wheel and its platform compatibility restrictions.
    torch = base + (['torch'] if engine == 'kokoro' else ['torch', 'torchaudio'])
    if sys.platform.startswith('linux'):
        torch += ['--index-url', CPU_WHEEL_INDEX]
    if engine == 'kokoro':
        # misaki[ja] pulls pyopenjtalk (a source-only build on several platforms)
        # and unidic (which contains no dictionary until another ~500MB download).
        # Install compatible prebuilt packages instead: pyopenjtalk-plus provides
        # the pyopenjtalk module, and unidic-lite includes its dictionary.
        # This retains Japanese G2P support without requiring a compiler or a
        # silent first-render dictionary download. Chinese is a pure-Python extra.
        return [torch,
                base + ['kokoro>=0.9.2', 'soundfile', 'espeakng-loader', 'misaki[zh]'],
                base + ['pyopenjtalk-plus>=0.4.1.post8', 'unidic-lite',
                        'fugashi', 'jaconv', 'mojimoji']]
    if engine == 'kitten':
        # Official 0.8 ONNX release, not the larger Kitten-TTS 2 1.7B model.
        return [base + [KITTEN_WHEEL, 'soundfile', 'espeakng-loader']]
    if engine == 'pocket':
        return [torch, base + ['pocket-tts', 'scipy']]
    # Current maintained Coqui fork requires PyTorch separately.
    return [torch, base + ['coqui-tts', 'torchcodec']]


def installation_log(engine: str) -> Path:
    """Persistent, human-readable log; safe to inspect after the GUI closes."""
    if engine not in NEURAL_ENGINES:
        raise ValueError(f'Unknown neural engine: {engine}')
    return cache_home() / engine / 'dependency-install.log'


def _run(command: list[str], *, timeout: int = 1800, log_path: Path | None = None,
         label: str = '', report=None) -> None:
    """Run a bootstrap command with useful failure details instead of hiding stderr.

    A failing uv/pip command previously surfaced just its first five arguments,
    making dependency resolution, network, and native-wheel errors indistinguishable.
    Keep output in a persistent install log, and put the actionable last lines in
    the GUI failure dialog. Never silently switch to downloading model weights.
    """
    log_path = Path(log_path) if log_path is not None else None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a', encoding='utf-8') as logfile:
            logfile.write('\n[%s] %s\n$ %s\n' % (
                datetime.now(timezone.utc).isoformat(timespec='seconds'),
                label or 'Dependency setup', subprocess.list2cmdline(command)))
    try:
        completed = subprocess.run(command, check=False, timeout=timeout,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, errors='replace')
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes):
            output = output.decode('utf-8', 'replace')
        if log_path is not None:
            with log_path.open('a', encoding='utf-8') as logfile:
                logfile.write(output + f'\nTimed out after {timeout}s.\n')
        raise RuntimeError(f'{label or "Dependency setup"} timed out after {timeout}s. '
                           f'Details: {log_path or "installer output"}') from exc
    except OSError as exc:
        if log_path is not None:
            with log_path.open('a', encoding='utf-8') as logfile:
                logfile.write(f'\nProcess launch failed: {exc}\n')
        raise RuntimeError(f'{label or "Dependency setup"}: {exc}. '
                           f'Log: {log_path or "not available"}') from exc
    output = completed.stdout or ''
    if log_path is not None:
        with log_path.open('a', encoding='utf-8') as logfile:
            logfile.write(output)
            if not output.endswith('\n'):
                logfile.write('\n')
            logfile.write(f'Exit code: {completed.returncode}\n')
    if completed.returncode:
        # The final lines normally contain the resolver or native-build error.
        # Include them directly so a screenshot is enough to diagnose a problem.
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        excerpt = '\n'.join(lines[-12:])[-1800:] or '(Command produced no output)'
        raise RuntimeError(
            f'{label or "Dependency setup"} failed (exit {completed.returncode}).\n'
            f'{excerpt}\n\nFull installation log: {log_path or "unavailable"}')


def _run_step(command: list[str], *, engine: str, label: str,
              timeout: int = 1800, report=None) -> None:
    """Retry only temporary download problems, never resolution/build failures."""
    logfile = installation_log(engine)
    for attempt in range(3):
        try:
            return _run(command, timeout=timeout, log_path=logfile,
                        label=label, report=report)
        except RuntimeError as exc:
            reason = str(exc).lower()
            transient = any(phrase in reason for phrase in (
                'timed out', 'connection reset', 'connection refused', 'connection error',
                'temporary failure', 'network is unreachable', 'http 502', 'http 503',
                'http 504', 'dns error', 'failed to fetch', 'failed to download'))
            if not transient or attempt == 2:
                raise
            if report:
                report(f'{engine}: temporary download problem; retrying ({attempt+1}/2). '
                       f'Full log: {logfile}')
            time.sleep(attempt + 1)


def ensure_installed(engine: str, *, report=None) -> Path:
    """Install dependencies on GUI confirmation without downloading voice models.

    Existing partial installations are repaired in place. ``.ready`` is only
    written after all stages and imports succeed.
    """
    if engine not in NEURAL_ENGINES:
        raise ValueError('Unknown neural speech engine: ' + engine)
    with _install_locks[engine]:
        if is_installed(engine):
            return python_path(engine)
        python = python_path(engine)
        root = cache_home() / engine
        root.mkdir(parents=True, exist_ok=True)
        (root / '.ready').unlink(missing_ok=True)
        uv = bundled_uv()
        log = installation_log(engine)
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f'\n=== Installation / repair started: {datetime.now(timezone.utc).isoformat()} ===\n')
        if report:
            report(f'Preparing {engine} CPU runtime (diagnostics: {log})')
        if not python.is_file():
            if uv:
                _run_step([uv, 'venv', '--python', '3.12', '--managed-python',
                           '--seed', str(root / '.venv')], engine=engine,
                          label='Creating managed Python 3.12 environment', timeout=900, report=report)
            else:
                try:
                    candidate = _python_candidate()
                except RuntimeError as exc:
                    raise RuntimeError('Cannot bootstrap an isolated neural environment: no Python 3.10–3.14 '
                                       'and no bundled uv runtime found. Rebuild with uv enabled, or install Python 3.12. '
                                       f'Installation log: {log}') from exc
                _run_step(candidate + ['-m', 'venv', str(root / '.venv')], engine=engine,
                          label='Creating Python virtual environment', timeout=180, report=report)
        if not python.is_file():
            raise RuntimeError(f'The Python environment for {engine} was not created: {python}\nLog: {log}')
        if not uv:
            _run_step([str(python), '-m', 'ensurepip', '--upgrade'], engine=engine,
                      label='Preparing pip', timeout=120, report=report)
        steps = install_plan(engine)
        for index, pip_args in enumerate(steps, 1):
            label = f'{engine} dependency stage {index}/{len(steps)}'
            if report:
                report(f'Installing {label} (CPU only). Install log: {log}')
            if uv:
                # uv pip install differs from pip: omit unsupported pip-only flags.
                flags = {'--no-input', '--disable-pip-version-check', '--prefer-binary'}
                command = [uv, 'pip', 'install', '--python', str(python),
                           *[arg for arg in pip_args[1:] if arg not in flags]]
            else:
                command = [str(python), '-m', 'pip', *pip_args]
            _run_step(command, engine=engine, label=label, report=report)
        imports = {'kokoro':'import kokoro; import pyopenjtalk; import fugashi',
                   'kitten':'import kittentts', 'pocket':'import pocket_tts', 'coqui':'import TTS'}
        if report:
            report(f'Checking {engine} imports and recording successful installation...')
        _run_step([str(python), '-c', imports[engine]], engine=engine,
                  label=f'Validating {engine} Python packages', timeout=120, report=report)
        (root / '.ready').write_text('1\n', encoding='ascii')
        if report:
            report(f'{engine} CPU dependencies installed successfully.')
        return python
