"""Progress shared by renderers, the Tk event queue and stderr-only CLI bars."""
from __future__ import annotations
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    fraction: float
    label: str
    stage_fraction: float | None = None


def emit(callback, fraction, label, stage_fraction=None):
    if callback:
        callback(Progress(max(0., min(1., fraction)), label,
                          None if stage_fraction is None else max(0., min(1., stage_fraction))))


def subprogress(callback, start, end, label=''):
    if not callback:
        return None
    def update(event):
        emit(callback, start + (end - start) * event.fraction,
             (label + ' · ' if label else '') + event.label, event.stage_fraction)
    return update


class ConsoleProgress:
    def __init__(self, stream=None):
        self.stream = stream or sys.stderr
        self.terminal = self.stream.isatty()
        self.last_time = 0.
        self.last_percent = -1

    def __call__(self, event):
        now = time.monotonic()
        percent = int(event.fraction * 100)
        if percent != 100 and now - self.last_time < (.15 if self.terminal else 1.):
            return
        self.last_time, self.last_percent = now, percent
        bar = '#' * (percent // 4) + '-' * (25 - percent // 4)
        text = f'[{bar}] {percent:3d}% {event.label}'
        if self.terminal:
            width = max(30, shutil.get_terminal_size((100,24)).columns - 1)
            text = text[:width].ljust(width)
        self.stream.write(('\r' if self.terminal else '') + text + ('\n' if not self.terminal or percent == 100 else ''))
        self.stream.flush()


def run_ffmpeg(command, *, control=None, progress=None, duration=None):
    """Read real FFmpeg timestamps while draining output and checking cancellation."""
    updates = queue.Queue(maxsize=300)
    command = list(command)
    command[1:1] = ['-progress', 'pipe:1', '-nostats']
    with tempfile.TemporaryFile(mode='w+b') as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding='utf-8', errors='replace',
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def reader():
            for line in process.stdout:
                if line.startswith(('out_time_us=', 'out_time_ms=')):
                    try:
                        updates.put_nowait(int(line.split('=', 1)[1]) / 1_000_000)
                    except (ValueError, queue.Full):
                        pass
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        def drain():
            while True:
                try:
                    seconds = updates.get_nowait()
                except queue.Empty:
                    return
                if progress and duration:
                    progress(max(0., min(.999, seconds / duration)))
        try:
            while process.poll() is None:
                if control: control.check()
                drain()
                time.sleep(.08)
            thread.join(timeout=2)
            drain()
            if control: control.check()
            if process.returncode:
                errors.seek(0, 2)
                size = errors.tell()
                errors.seek(max(0, size - 2000))
                raise RuntimeError('FFmpeg error: ' + errors.read().decode('utf-8', 'replace').strip())
            if progress: progress(1.)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            thread.join(timeout=2)
            process.stdout.close()
