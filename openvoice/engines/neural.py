"""CPU neural engine adapters, with a durable JSON-lines worker per backend."""
from __future__ import annotations
import atexit
import hashlib
import importlib.resources
import json
import os
import subprocess
import threading
import tempfile
from pathlib import Path

from .base import EngineError, Cancelled, RunControl, SpeechEngine, SpeechSettings, invoke
from ..neural_runtime import (KOKORO_VOICES, KITTEN_VOICES, POCKET_VOICES,
                              cache_home, python_path, is_installed, _python_candidate, bundled_uv)
from ..neural_models import (require_downloaded, mark_downloaded, model_environment,
                             effective_model, effective_voice, pocket_voice_state_path)

class _Worker:
    """One process for one neural backend, serializing calls for a long audiobook."""
    def __init__(self, python: Path, script: Path, name: str, *, allow_download: bool = False):
        self.lock = threading.RLock()
        self.python = python
        self.script = script
        self.name = name
        self.allow_download = allow_download
        self.device_mode = os.environ.get("OPENMUKTI_GPU_MODE", "auto")
        self.process = None
        self.log = None
        self.log_path = cache_home() / name / 'worker.log'

    def _start(self):
        if self.process and self.process.poll() is None:
            return
        if self.process:
            self.close()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = self.log_path.open('ab', buffering=0)
        self.process = subprocess.Popen([str(self.python), '-u', str(self.script)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, env=model_environment(allow_network=self.allow_download),
                                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

    def _log_excerpt(self) -> str:
        """Show a bounded tail of the real worker traceback in the GUI."""
        try:
            with self.log_path.open('rb') as stream:
                stream.seek(0, os.SEEK_END)
                stream.seek(max(0, stream.tell() - 12_288))
                tail = stream.read().decode('utf-8', 'replace')
            return '\n'.join(tail.splitlines()[-8:])[-1000:]
        except OSError:
            return ''

    def _diagnostics(self) -> str:
        excerpt = self._log_excerpt()
        return f'\nWorker log: {self.log_path}' + (f'\nLast log lines:\n{excerpt}' if excerpt else '')

    def request(self, payload: dict, control=None) -> dict:
        with self.lock:
            if control: control.check()
            self._start()
            proc = self.process
            if control: control.register(proc)
            try:
                try:
                    proc.stdin.write((json.dumps(payload,ensure_ascii=False)+'\n').encode('utf-8'))
                    proc.stdin.flush()
                    response = None
                    # Older workers/upstream dependencies may write native log
                    # lines into stdout. Ignore bounded chatter and save it to
                    # the diagnostic log; do not confuse it with protocol JSON.
                    for _ in range(128):
                        raw = proc.stdout.readline(65_536)
                        if not raw:
                            break
                        try:
                            candidate = json.loads(raw)
                        except (UnicodeError, ValueError):
                            candidate = None
                        if isinstance(candidate, dict) and isinstance(candidate.get('ok'), bool):
                            response = candidate
                            break
                        if self.log:
                            line = raw[:4096].decode('utf-8', 'replace').rstrip()
                            self.log.write(('[non-protocol stdout] ' + line +
                                            (' [truncated]' if len(raw) > 4096 else '') + '\n').encode('utf-8'))
                except (BrokenPipeError, OSError) as exc:
                    details = self._diagnostics()
                    self.close()
                    raise EngineError(f'{self.name} inference worker stopped unexpectedly: {exc}{details}') from exc
                if control and control.stopped.is_set():
                    self.close()
                    raise Cancelled('Speech cancelled')
                if response is None:
                    details = self._diagnostics()
                    self.close()
                    raise EngineError(f'{self.name} worker produced no valid JSON response. '
                                      f'Check that its dependencies and model load correctly.{details}')
                if not response['ok']:
                    raise EngineError(f'{self.name}: {response.get("error", "unknown inference error")}'
                                      f'{self._diagnostics()}')
                return response
            finally:
                if control: control.unregister(proc)

    def close(self):
        if self.process:
            proc, self.process = self.process, None
            if proc.poll() is None:
                proc.kill()
            for file in (proc.stdin, proc.stdout):
                if file: file.close()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        if self.log:
            self.log.close()
            self.log = None

_WORKERS: dict[str, _Worker] = {}
_WORKERS_LOCK = threading.RLock()


def _worker_script() -> Path:
    # Build packages contain this as a .txt resource so PyInstaller and wheels
    # always collect the source even when they exclude ordinary Python modules.
    content = importlib.resources.files('openvoice').joinpath('resources/neural_worker.txt').read_bytes()
    digest = hashlib.sha256(content).hexdigest()[:18]
    target = cache_home() / ('neural-worker-' + digest + '.py')
    if not target.is_file() or target.read_bytes() != content:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.neural-worker-', suffix='.tmp', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(content)
            os.replace(temp, target)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return target


def _get_worker(name: str) -> _Worker:
    with _WORKERS_LOCK:
        if not is_installed(name):
            raise EngineError(f"{name} CPU engine is not installed. Use the GUI Install / repair selected neural engine button first.")
        python = python_path(name)
        script = _worker_script()
        worker = _WORKERS.get(name)
        if worker is None or worker.python != python or worker.script != script or worker.device_mode != os.environ.get("OPENMUKTI_GPU_MODE", "auto"):
            if worker: worker.close()
            worker = _Worker(python, script, name)
            _WORKERS[name] = worker
        return worker


def download_neural_voice(engine: str, model: str = '', voice: str = '', *, report=None) -> None:
    """Only call following an explicit user click and positive confirmation.

    A separate, network-enabled worker handles this one intentional download.
    No normal preview/export/discovery call can invoke this function.
    """
    from ..neural_runtime import NEURAL_ENGINES
    if engine not in NEURAL_ENGINES:
        raise ValueError('Unknown neural engine: ' + engine)
    if not is_installed(engine):
        raise EngineError(f'{engine} CPU engine dependencies are not installed. '
                          'Click Install / repair selected neural engine first.')
    selected_model = effective_model(engine, model, voice)
    selected_voice = effective_voice(engine, voice)
    if report:
        report(f'Downloading {engine}: {selected_model} / {selected_voice or "all speakers"}')
    worker = _Worker(python_path(engine), _worker_script(), engine,
                     allow_download=True)
    try:
        args = {'action':'download', 'engine':engine,
                'model':selected_model, 'voice':selected_voice}
        if engine == 'pocket':
            args['voice_state_path'] = str(pocket_voice_state_path(selected_model, selected_voice))
        worker.request(args)
        mark_downloaded(engine, selected_model, selected_voice)
    finally:
        worker.close()


def close_neural_workers():
    with _WORKERS_LOCK:
        for worker in _WORKERS.values():
            worker.close()
        _WORKERS.clear()

atexit.register(close_neural_workers)

class NeuralSpeechEngine(SpeechEngine):
    supports_rate = True  # native speed or bundled FFmpeg pitch-preserving tempo
    supports_pitch = False
    supports_volume = False

    def available(self) -> bool:
        if is_installed(self.key) or bundled_uv():
            return True
        try:
            _python_candidate()
            return True
        except RuntimeError:
            return False

    def voices(self) -> list[str]:
        return list({'kokoro':KOKORO_VOICES,'kitten':KITTEN_VOICES,
                     'pocket':POCKET_VOICES,'coqui':()}[self.key])

    def voices_for_model(self, model: str) -> list[str]:
        if self.key != 'coqui':
            return self.voices()
        require_downloaded(self.key, model)
        return _get_worker(self.key).request({'action':'voices','engine':self.key,'model':model})['voices']

    def render_wav(self, text: str, output: Path, settings: SpeechSettings,
                   control: RunControl | None = None) -> None:
        try:
            require_downloaded(self.key, settings.model, settings.voice, settings.language)
            worker = _get_worker(self.key)
            payload = {'engine':self.key, 'text':text, 'output':str(Path(output).resolve()),
                       'voice':settings.voice, 'model':settings.model, 'rate':settings.rate,
                       'language':settings.language}
            if self.key == 'pocket':
                payload['voice_state_path'] = str(pocket_voice_state_path(
                    settings.model, settings.voice, settings.language))
            worker.request(payload,control)
            if self.key in ('pocket', 'coqui') and settings.rate:
                # These APIs do not expose a reliable rate option. Preserve the
                # rate control with FFmpeg's pitch-preserving atempo filter.
                from ..fftools import find_binary
                ffmpeg = find_binary('ffmpeg')
                if not ffmpeg:
                    raise EngineError('FFmpeg is required to adjust Pocket/Coqui speech speed.')
                source = Path(output)
                target = source.with_suffix('.tempo.wav')
                factor = max(0.5, min(2, 1 + settings.rate * 0.06))
                try:
                    invoke([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-i', str(source),
                            '-af', f'atempo={factor:.4f}', '-c:a', 'pcm_s16le', str(target)],control=control)
                    target.replace(source)
                finally:
                    target.unlink(missing_ok=True)
        except (OSError, RuntimeError) as exc:
            if isinstance(exc, EngineError):
                raise
            raise EngineError(f'{self.label} setup failed: {exc}') from exc

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None = None) -> None:
        from .builtin import play_wav
        with tempfile.TemporaryDirectory(prefix=f'openmukti-{self.key}-') as work:
            output = Path(work) / 'preview.wav'
            self.render_wav(text, output, settings, control)
            play_wav(output, control)

class Kokoro82M(NeuralSpeechEngine):
    key='kokoro'
    label='Kokoro-82M (CPU, multilingual)'
    supports_rate=True

class Kitten(NeuralSpeechEngine):
    key='kitten'
    label='KittenTTS 0.8 (lightweight CPU ONNX)'
    supports_rate=True

class Pocket(NeuralSpeechEngine):
    key='pocket'
    label='Kyutai Pocket TTS (CPU)'

class CoquiCPU(NeuralSpeechEngine):
    key='coqui'
    label='Coqui TTS (CPU, maintained coqui-tts fork)'

NEURAL_BUILTINS = [Kokoro82M,Kitten,Pocket,CoquiCPU]
