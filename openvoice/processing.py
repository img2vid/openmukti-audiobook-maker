from __future__ import annotations
import csv
import json
import re
import unicodedata
from pathlib import Path

class TextProcessingError(ValueError):
    pass

def normalize_text(text: str, repair_ocr: bool=False) -> str:
    text = unicodedata.normalize('NFC', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '')
    text = ''.join((ch for ch in text if ch in '\n\t' or unicodedata.category(ch) != 'Cc'))
    if repair_ocr:
        text = re.sub('(?<=[a-z])[-\\u00ad]\\n(?=[a-z])', '', text)
        text = re.sub('(?<!\\n)\\n(?!\\n)', ' ', text)
    text = re.sub('[ \\t]+', ' ', text)
    text = re.sub(' *\\n *', '\n', text)
    text = re.sub('\\n{3,}', '\n\n', text)
    return text.strip()

def load_replacements(files: list[str] | tuple[str, ...]) -> list[dict]:
    result = []
    for file in files:
        path = Path(file)
        if path.suffix.lower() == '.json':
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(data, list):
                raise TextProcessingError(f'Dictionary must contain a JSON list: {path}')
            rows = data
        elif path.suffix.lower() in {'.tsv', '.dic', '.txt'}:
            with path.open('r', encoding='utf-8-sig', newline='') as f:
                rows = [{'find': r[0], 'replace': r[1]} for r in csv.reader(f, delimiter='\t') if len(r) >= 2 and r[0] and (not r[0].startswith('#'))]
        else:
            raise TextProcessingError('Supported dictionary formats are JSON and tab-delimited TSV/TXT/DIC')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('find'), str) or (not isinstance(row.get('replace'), str)):
                raise TextProcessingError(f'Invalid dictionary entry in {path}')
            if not row['find']:
                raise TextProcessingError('Dictionary find cannot be empty')
            result.append(row)
    return result

def apply_replacements(text: str, rows: list[dict]) -> str:
    for row in rows:
        needle = row['find']
        flags = 0 if row.get('case_sensitive', False) else re.IGNORECASE
        if row.get('regex', False):
            try:
                text = re.sub(needle, row['replace'], text, flags=flags)
            except re.error as exc:
                raise TextProcessingError(f'Invalid pronunciation regex {needle!r}: {exc}') from exc
        else:
            left = '(?<!\\w)' if needle[0].isalnum() else ''
            right = '(?!\\w)' if needle[-1].isalnum() else ''
            text = re.sub(left + re.escape(needle) + right, lambda _match: row['replace'], text, flags=flags)
    return text

def split_text(text: str, max_chars: int=450) -> list[str]:
    if max_chars < 16:
        raise TextProcessingError('max_chars must be >= 16')
    text = text.strip()
    if not text:
        return []
    pieces = re.split('(?<=[.!?。！？])\\s+|\\n{2,}', text)
    chunks: list[str] = []
    current = ''
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        tokens = re.findall('\\S+\\s*', piece)
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            while len(token) > max_chars:
                if current:
                    chunks.append(current)
                    current = ''
                chunks.append(token[:max_chars])
                token = token[max_chars:]
            if not token:
                continue
            if current and len(current) + 1 + len(token) > max_chars:
                chunks.append(current)
                current = token
            else:
                current = f'{current} {token}' if current else token
    if current:
        chunks.append(current)
    return chunks
