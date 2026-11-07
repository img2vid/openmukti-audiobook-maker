"""Portable native imaging worker discovery and cancellable JSON transport."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path


def find_worker():
    name = 'OpenmuktiOCRWorker.exe' if os.name == 'nt' else 'OpenmuktiOCRWorker'
    override = os.environ.get('OPENMUKTI_OCR_WORKER', '').strip()
    candidates = [Path(override).expanduser()] if override else []
    for base in (getattr(sys, '_MEIPASS', ''), Path(sys.executable).parent, Path(__file__).resolve().parent.parent):
        if base:
            candidates.extend((Path(base) / 'ocr_worker' / name, Path(base) / '_internal' / 'ocr_worker' / name))
    return next((p.resolve() for p in candidates if p.is_file()), None)


def import_with_worker(source, settings, *, progress=None, cancel=None):
    from .ocr import OCRCancelled, OCRError, OCRResult, find_tesseract
    worker = find_worker()
    if not worker:
        raise OCRError('The portable OCR worker is missing; rebuild the OCR-enabled Windows edition.')
    with tempfile.TemporaryDirectory(prefix='openmukti-ocr-request-') as folder:
        folder = Path(folder)
        request, result_path, cancel_path = folder / 'request.json', folder / 'result.json', folder / 'cancel'
        binary = find_tesseract()
        request.write_text(json.dumps({'source': str(source), 'settings': asdict(settings), 'result': str(result_path), 'cancel': str(cancel_path), 'tesseract': str(binary) if binary else ''}), encoding='utf-8')
        environment = os.environ.copy()
        if getattr(sys, 'frozen', False):
            environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        options = {'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT, 'env': environment, 'text': True, 'encoding': 'utf-8', 'errors': 'replace'}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NO_WINDOW
        try:
            process = subprocess.Popen([str(worker), '--request', str(request)], **options)
        except OSError as exc:
            raise OCRError(f'Cannot start portable OCR worker: {exc}') from exc
        messages = queue.Queue()
        def drain():
            for line in process.stdout:
                messages.put(line)
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        log, cancelled_at = [], None
        try:
            while process.poll() is None or reader.is_alive() or not messages.empty():
                if cancel is not None and cancel.is_set() and cancelled_at is None:
                    cancel_path.touch()
                    cancelled_at = time.monotonic()
                if cancelled_at and time.monotonic() - cancelled_at > 5 and process.poll() is None:
                    process.kill()
                try:
                    line = messages.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    data = json.loads(line)
                    if 'progress' in data and progress:
                        progress(*data['progress'])
                    elif 'error' in data:
                        log.append(data['error'])
                except (ValueError, TypeError):
                    log.append(line.strip())
                log = log[-20:]
            reader.join(timeout=1)
            if cancelled_at or (cancel is not None and cancel.is_set()):
                raise OCRCancelled('OCR cancelled. No partial text was applied.')
            if process.returncode or not result_path.is_file():
                raise OCRError('Portable OCR failed: ' + '\n'.join(log)[-1500:])
            return OCRResult.from_dict(json.loads(result_path.read_text(encoding='utf-8')))
        finally:
            if process.poll() is None:
                cancel_path.touch()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            reader.join(timeout=1)
            process.stdout.close()
