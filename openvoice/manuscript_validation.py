"""Offline manuscript script checks, asset audits and publication preflight.

Reports evidence rather than presuming that multilingual text is erroneous.
"""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from pathlib import Path

_SCRIPT_RANGES = (
    ('Arabic', 0x0600, 0x08FF),
    ('Bengali', 0x0980, 0x09FF),
    ('Devanagari', 0x0900, 0x097F),
    ('Gurmukhi', 0x0A00, 0x0A7F),
    ('Gujarati', 0x0A80, 0x0AFF),
    ('Oriya', 0x0B00, 0x0B7F),
    ('Tamil', 0x0B80, 0x0BFF),
    ('Telugu', 0x0C00, 0x0C7F),
    ('Kannada', 0x0C80, 0x0CFF),
    ('Malayalam', 0x0D00, 0x0D7F),
    ('Sinhala', 0x0D80, 0x0DFF),
    ('Thai', 0x0E00, 0x0E7F),
    ('Lao', 0x0E80, 0x0EFF),
    ('Myanmar', 0x1000, 0x109F),
    ('Georgian', 0x10A0, 0x10FF),
    ('Hangul', 0xAC00, 0xD7AF),
    ('CJK', 0x3400, 0x9FFF),
    ('Hiragana', 0x3040, 0x309F),
    ('Katakana', 0x30A0, 0x30FF),
    ('Hebrew', 0x0590, 0x05FF),
    ('Greek', 0x0370, 0x03FF),
    ('Cyrillic', 0x0400, 0x052F),
)
_COMPLEX = {'Arabic','Bengali','Devanagari','Gurmukhi','Gujarati','Oriya','Tamil',
            'Telugu','Kannada','Malayalam','Sinhala','Thai','Lao','Myanmar','Hebrew'}


def script_of(character: str) -> str | None:
    code = ord(character)
    for name, first, last in _SCRIPT_RANGES:
        if first <= code <= last:
            return name
    if 0x0041 <= code <= 0x005A or 0x0061 <= code <= 0x007A or 0x00C0 <= code <= 0x024F:
        return 'Latin'
    return None


def mixed_script_report(text: str, *, max_issues: int = 100) -> dict:
    if len(text) > 5_000_000:
        raise ValueError('Manuscript exceeds 5 million character report limit')
    if not 1 <= max_issues <= 10000:
        raise ValueError('max_issues must be in 1..10000')
    counts: dict[str, int] = {}
    paragraphs = []
    issues = []
    for offset, paragraph in enumerate(re.split(r'\n\s*\n', text)):
        local = {}
        for char in paragraph:
            family = script_of(char)
            if family:
                local[family] = local.get(family, 0) + 1
                counts[family] = counts.get(family, 0) + 1
        if not local:
            continue
        major = max(local.values())
        dominant = [s for s, count in local.items() if count == major][0]
        paragraphs.append({'paragraph': offset + 1, 'dominant_script': dominant,
                           'scripts': local, 'mixed': len(local) > 1})
        if len(local) > 1 and len(issues) < max_issues:
            issues.append({'kind': 'mixed-script', 'paragraph': offset + 1,
                           'scripts': sorted(local), 'message': 'Check font coverage and TTS voice language; mixing may be intentional.'})
    marks = []
    for index, char in enumerate(text):
        if unicodedata.category(char) in ('Mn','Mc','Me') and (index == 0 or text[index-1] == '\n'):
            if len(marks) < max_issues:
                marks.append({'index': index, 'codepoint': f'U+{ord(char):04X}', 'kind': 'isolated-combining-mark'})
    warnings = []
    if any(script in _COMPLEX for script in counts):
        warnings.append('Complex scripts require a shaping-capable renderer (such as HarfBuzz); per-character drawing is not sufficient.')
    if any(script in counts for script in ('Arabic','Hebrew')):
        warnings.append('Bidirectional text needs script-aware ordering; verify punctuation placement.')
    return {'total_characters': len(text), 'scripts': counts, 'paragraphs': paragraphs,
            'mixed_paragraph_count': sum(bool(p['mixed']) for p in paragraphs),
            'issues': issues, 'combining_mark_warnings': marks,
            'normalization': 'NFC' if unicodedata.is_normalized('NFC', text) else 'non-NFC',
            'warnings': warnings}


def audit_audio_segments(manifest: str | Path, folder: str | Path) -> dict:
    """Audit a JSON list of rendered segments: {id, file, sha256?}."""
    data = json.loads(Path(manifest).read_text(encoding='utf-8'))
    items = data.get('segments',data.get('passages')) if isinstance(data, dict) else data
    if not isinstance(items, list) or len(items) > 100000:
        raise ValueError('Expected a list of no more than 100000 segments')
    root = Path(folder).expanduser().resolve()
    rows = []
    missing = 0
    for index, segment in enumerate(items):
        if not isinstance(segment, dict) or not isinstance(segment.get('file'), str):
            raise ValueError(f'Invalid segment at position {index}')
        name = segment['file']
        path = (root / name).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() not in {'.wav','.mp3','.flac','.ogg','.opus','.m4a','.aac'}:
            raise ValueError('Segment path is unsafe or not audio')
        ok = path.is_file() and path.stat().st_size > 0
        status = 'present' if ok else 'missing'
        if ok and segment.get('sha256'):
            hasher = hashlib.sha256()
            with path.open('rb') as inp:
                for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                    hasher.update(chunk)
            if hasher.hexdigest() != segment['sha256']:
                status = 'checksum-mismatch'
        if status != 'present':
            missing += 1
        rows.append({'id': segment.get('id', index), 'file': name, 'status': status})
    return {'total': len(rows), 'missing_or_corrupt': missing, 'ready': missing == 0,
            'segments': rows}


def publication_preflight(folder: str | Path, *, title: str = '', author: str = '',
                          language: str = '', cover: str = '') -> dict:
    """Basic format and metadata readiness report. NOT platform certification."""
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Export directory does not exist')
    audio_ext = {'.wav','.mp3','.m4b','.m4a','.flac','.opus','.ogg','.aac'}
    video_ext = {'.mp4','.mov','.mkv','.webm'}
    files = [p for p in root.rglob('*') if p.is_file()]
    if len(files) > 100000:
        raise ValueError('Too many export files to audit')
    media = [p for p in files if p.suffix.casefold() in audio_ext | video_ext]
    issues = []
    for field, value in [('title',title),('author',author),('language',language)]:
        if not value.strip():
            issues.append({'severity':'warning', 'message':f'Missing publication metadata: {field}'})
    if not media:
        issues.append({'severity':'error', 'message':'No exported audio or video files found'})
    for p in media:
        if p.stat().st_size == 0:
            issues.append({'severity':'error','message':f'Empty exported file: {p.relative_to(root)}'})
    if cover:
        cover_path = Path(cover)
        if not cover_path.is_file():
            issues.append({'severity':'error','message':'Supplied cover image is missing'})
        elif cover_path.suffix.lower() not in {'.jpg','.jpeg','.png','.webp'}:
            issues.append({'severity':'warning','message':'Cover format may not be accepted by publishing platform'})
    return {'folder':str(root), 'media_count':len(media), 'files':len(files),
            'bytes':sum(p.stat().st_size for p in files), 'issues':issues,
            'ready_for_manual_platform_review':not any(x['severity']=='error' for x in issues),
            'disclaimer':'Publishing platforms have independent evolving rules; verify their current requirements.'}
