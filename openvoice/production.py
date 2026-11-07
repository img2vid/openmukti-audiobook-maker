"""Production automation: workflow tracking, estimates and logs.

A small JSON-backed production board records each chapter's stage
(imported → corrected → narrated → mastered → exported), quality-control
checkpoints and approvals. Combined with duration estimation and resource
forecasting it powers the production dashboard without any external
service. The JSONL production log gives every rendering run an auditable,
redaction-friendly record.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path

STAGES = ('imported', 'corrected', 'narrated', 'mastered', 'exported')
FORMAT = 'openmukti-production'
VERSION = 1

# Rough encoded-size model for forecasting (bytes per second of audio).
ENCODED_BYTES_PER_SECOND = {
    'wav': 176400, 'flac': 90000, 'mp3': 16000, 'm4a': 12000, 'aac': 12000,
    'ogg': 14000, 'opus': 8000, 'aiff': 176400, 'wma': 16000,
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _check_stage(stage: str) -> str:
    if stage not in STAGES:
        raise ValueError(f'Stage must be one of: {", ".join(STAGES)}')
    return stage


class ProductionBoard:
    """Track chapter workflow stages, checkpoints and approvals."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('format') != FORMAT:
                raise ValueError('Unsupported production board file')
            if int(data.get('version', 0)) > VERSION:
                raise ValueError('Production board was saved by a newer application version')
            self.chapters: dict[str, dict] = data.get('chapters', {})
        else:
            self.chapters = {}

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'format': FORMAT, 'version': VERSION, 'saved': _now(), 'chapters': self.chapters}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.path

    def _entry(self, chapter: str) -> dict:
        if not chapter.strip():
            raise ValueError('Chapter title must not be empty')
        return self.chapters.setdefault(chapter, {'stage': STAGES[0], 'checkpoints': {},
                                                  'approved': False, 'history': []})

    def set_stage(self, chapter: str, stage: str) -> dict:
        """Move a chapter to a workflow stage (forward or back for rework)."""
        entry = self._entry(chapter)
        stage = _check_stage(stage)
        if stage != entry['stage']:
            entry['history'].append({'at': _now(), 'from': entry['stage'], 'to': stage})
            entry['stage'] = stage
            if stage != 'exported':
                entry['approved'] = False
        return entry

    def set_checkpoint(self, chapter: str, checkpoint: str, passed: bool) -> dict:
        """Record a quality-control checkpoint result for a chapter."""
        if not checkpoint.strip():
            raise ValueError('Checkpoint name must not be empty')
        entry = self._entry(chapter)
        entry['checkpoints'][checkpoint.strip()] = {'passed': bool(passed), 'at': _now()}
        if not passed:
            entry['approved'] = False
        return entry

    def approve(self, chapter: str) -> dict:
        """Approve a chapter after all recorded checkpoints have passed."""
        entry = self._entry(chapter)
        failed = [name for name, cp in entry['checkpoints'].items() if not cp.get('passed')]
        if failed:
            raise ValueError(f'Chapter has failing checkpoints: {", ".join(sorted(failed))}')
        entry['approved'] = True
        entry['history'].append({'at': _now(), 'from': entry['stage'], 'to': entry['stage'],
                                 'note': 'approved'})
        return entry

    def dashboard(self) -> dict:
        """Overall production progress across chapters and stages."""
        per_stage = {stage: 0 for stage in STAGES}
        approved = 0
        for entry in self.chapters.values():
            per_stage[entry.get('stage', STAGES[0])] += 1
            approved += 1 if entry.get('approved') else 0
        total = len(self.chapters)
        completed = per_stage['exported']
        return {'total_chapters': total, 'chapters_by_stage': per_stage,
                'approved': approved, 'exported': completed,
                'percent_exported': round(100 * completed / total, 1) if total else 0.0}


def estimate_render_seconds(words: int, *, realtime_factor: float = 0.5,
                            wpm: int = 160) -> dict:
    """Estimate synthesis wall-clock time from past benchmark measurements.

    ``realtime_factor`` is measured as synthesis seconds per audio second
    on the current machine (0.5 means rendering runs twice as fast as
    playback). The estimate includes a fixed per-chunk overhead model so
    short passages are not underestimated.
    """
    if words < 0:
        raise ValueError('Word count must not be negative')
    if realtime_factor <= 0:
        raise ValueError('Realtime factor must be positive')
    if wpm < 1:
        raise ValueError('Words per minute must be positive')
    audio_seconds = words * 60.0 / wpm
    chunks = max(1, math.ceil(words / 450)) if words else 0
    overhead = chunks * 0.4
    return {'words': words, 'estimated_audio_seconds': round(audio_seconds, 1),
            'estimated_render_seconds': round(audio_seconds * realtime_factor + overhead, 1),
            'chunks': chunks, 'realtime_factor': realtime_factor}


def forecast_resources(chapters: list[dict], *, audio_format: str = 'wav',
                       wpm: int = 160) -> dict:
    """Forecast storage for generated audio before a large job.

    Each chapter is ``{'title': ..., 'words': ...}``. WAV/AIFF figures use
    44.1 kHz 16-bit stereo; compressed formats use typical audiobook
    bitrates. Returns per-chapter and total byte estimates.
    """
    if audio_format not in ENCODED_BYTES_PER_SECOND:
        raise ValueError(f'Unknown audio format for forecasting: {audio_format}')
    rate = ENCODED_BYTES_PER_SECOND[audio_format]
    rows, total = [], 0
    for chapter in chapters:
        words = int(chapter.get('words', 0))
        if words < 0:
            raise ValueError('Chapter word counts must not be negative')
        seconds = words * 60.0 / wpm
        size = int(seconds * rate)
        total += size
        rows.append({'title': chapter.get('title', ''), 'words': words,
                     'estimated_audio_seconds': round(seconds, 1),
                     'estimated_bytes': size})
    return {'audio_format': audio_format, 'chapters': rows, 'total_estimated_bytes': total,
            'assumption': f'{rate} bytes/second ({audio_format})'}


class ProductionLog:
    """Append-only JSONL production log with optional field redaction."""

    def __init__(self, path: str | Path, *, redact: list[str] | None = None):
        self.path = Path(path)
        self.redact = {r.casefold() for r in (redact or [])}

    def record(self, event: str, level: str = 'info', **fields) -> dict:
        if level not in ('debug', 'info', 'warning', 'error'):
            raise ValueError('Log level must be debug, info, warning or error')
        if not event.strip():
            raise ValueError('Log event name must not be empty')
        entry = {'at': _now(), 'level': level, 'event': event.strip()}
        for key, value in fields.items():
            entry[key] = '[redacted]' if key.casefold() in self.redact else value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return entry

    def entries(self, *, level: str = '') -> list[dict]:
        if not self.path.is_file():
            return []
        rows = []
        for line in self.path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                entry = json.loads(line)
                if not level or entry.get('level') == level:
                    rows.append(entry)
        return rows

    def summary(self) -> dict:
        counts = {'debug': 0, 'info': 0, 'warning': 0, 'error': 0}
        for entry in self.entries():
            counts[entry.get('level', 'info')] = counts.get(entry.get('level', 'info'), 0) + 1
        counts['total'] = sum(v for k, v in counts.items() if k != 'total')
        return counts
