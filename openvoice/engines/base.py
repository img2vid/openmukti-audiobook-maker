from __future__ import annotations
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

class EngineError(RuntimeError):
    pass

class Cancelled(EngineError):
    pass

@dataclass(frozen=True)
class SpeechSettings:
    voice: str = ''
    rate: int = 0
    pitch: int = 0
    volume: int = 100
    model: str = ''
    speaker_id: int | None = None  # Piper voice index; None preserves legacy behavior
    language: str = "auto"  # language for multilingual neural models

class RunControl:

    def __init__(self):
        self.stopped = threading.Event()
        self.resumed = threading.Event()
        self.resumed.set()
        self._lock = threading.Lock()
        self._active: subprocess.Popen | None = None

    def pause(self) -> None:
        self.resumed.clear()

    def resume(self) -> None:
        self.resumed.set()

    def stop(self) -> None:
        self.stopped.set()
        self.resumed.set()
        with self._lock:
            proc = self._active
        if proc is not None and proc.poll() is None:
            proc.kill()

    def check(self) -> None:
        if self.stopped.is_set():
            raise Cancelled('Speech cancelled')
        while not self.resumed.wait(timeout=0.1):
            if self.stopped.is_set():
                raise Cancelled('Speech cancelled')
        if self.stopped.is_set():
            raise Cancelled('Speech cancelled')

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._active = proc
            if self.stopped.is_set() and proc.poll() is None:
                proc.kill()

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            if self._active is proc:
                self._active = None

def invoke(args: list[str], *, cwd: str | None=None, stdin: bytes | None=None, control: RunControl | None=None) -> bytes:
    from ..desktop_prefs import authorized
    authorized('external_tools')
    if control:
        control.check()
    try:
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creationflags)
    except OSError as exc:
        raise EngineError(f'Cannot launch speech engine: {exc}') from exc
    if control:
        control.register(proc)
    try:
        stdout, stderr = proc.communicate(stdin)
    finally:
        if control:
            control.unregister(proc)
    if control and control.stopped.is_set():
        raise Cancelled('Speech cancelled')
    if proc.returncode:
        detail = stderr.decode('utf-8', 'replace').strip()
        raise EngineError(f'Speech engine failed (exit {proc.returncode}): {detail[:2000]}')
    return stdout

class SpeechEngine:
    key = ''
    label = ''
    supports_pitch = False
    supports_rate = False
    supports_volume = False

    def available(self) -> bool:
        raise NotImplementedError

    def voices(self) -> list[str]:
        return []

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None=None) -> None:
        raise NotImplementedError

    def render_wav(self, text: str, output: Path, settings: SpeechSettings, control: RunControl | None=None) -> None:
        raise NotImplementedError
