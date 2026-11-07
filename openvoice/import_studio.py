"""Explicit article import, saved batch rules and stable-file folder monitoring."""
from __future__ import annotations

import codecs
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .documents import DocumentError, MAX_UNCOMPRESSED, html_to_text


def read_kindle(path):
    # Calibre detects file variants and rejects encrypted publications itself.
    from .desktop_prefs import authorized
    authorized('external_tools')
    binary=shutil.which('ebook-convert')
    if not binary:
        raise DocumentError('DRM-free Kindle import requires Calibre ebook-convert on PATH')
    with tempfile.TemporaryDirectory() as tmp:
        dest=Path(tmp)/'book.txt'
        try:
            result=subprocess.run([binary,str(Path(path).resolve()),str(dest)],cwd=tmp,
                                  stdin=subprocess.DEVNULL,capture_output=True,timeout=240)
        except subprocess.TimeoutExpired as exc:
            raise DocumentError('Kindle conversion timed out') from exc
        if result.returncode or not dest.is_file():
            raise DocumentError('Calibre could not import this DRM-free book: '+result.stderr[-600:].decode(errors='replace'))
        if dest.stat().st_size>MAX_UNCOMPRESSED:
            raise DocumentError('Converted book exceeds the import limit')
        return dest.read_text(encoding='utf-8-sig')


def read_article(url, opener=None):
    from .desktop_prefs import authorized
    authorized('network')
    address=urllib.parse.urlsplit(url)
    if address.scheme not in ('http','https') or not address.hostname or address.username or address.password:
        raise ValueError('Enter an HTTP or HTTPS article address')
    req=urllib.request.Request(url,headers={'User-Agent':'Openmukti article importer','Accept':'text/html,text/plain'})
    with (opener or urllib.request.urlopen)(req,timeout=20) as response:
        mime=response.headers.get_content_type()
        if mime not in ('text/html','application/xhtml+xml','text/plain'):
            raise DocumentError('Article URL must return HTML or plain text')
        raw=response.read(8*1024**2+1)
        if len(raw)>8*1024**2:
            raise DocumentError('Article exceeds the 8 MiB import limit')
        try:
            encoding=response.headers.get_content_charset() or 'utf-8-sig'
            text=raw.decode(encoding,errors='replace')
        except LookupError as exc:
            raise DocumentError('Unknown article encoding') from exc
    return html_to_text(text).strip() if mime!='text/plain' else text.strip()


def batch_read(paths,preset=None):
    from .documents import read_document, ARCHIVE_DOCUMENTS
    from .texttools import transform
    from .processing import normalize_text
    preset=preset or {}
    extensions=set(preset.get('extensions',ARCHIVE_DOCUMENTS|{'.zip','.cbz'}))
    if not all(isinstance(v,str) and v.startswith('.') for v in extensions):
        raise ValueError('Preset extensions must begin with a period')
    files=[]
    for source in map(Path,paths):
        if source.is_dir():
            files.extend(sorted(p for p in (source.rglob('*') if preset.get('recursive') else source.iterdir())
                                if p.is_file() and p.suffix.lower() in extensions))
        elif source.suffix.lower() in extensions:
            files.append(source)
    if not files:
        raise ValueError('No documents match the import rules')
    parts=[]
    for file in files:
        raw=read_document(file,footnotes=preset.get('footnotes','inline'),tables=preset.get('tables','plain'))
        if preset.get('repair_ocr'):
            raw=normalize_text(raw,repair_ocr=True)
        if preset.get('operations'):
            raw=transform(raw,preset['operations'])
        if preset.get('headings'):
            raw=file.stem+'\n\n'+raw
        parts.append(raw)
    return '\n\n'.join(parts)


class FolderInbox:
    """Require an unchanged size and modification time across two scans."""
    def __init__(self,folder):
        self.folder=Path(folder).resolve(strict=True)
        self.previous={}
        self.seen=set()

    def poll(self):
        from .documents import ARCHIVE_DOCUMENTS
        observed={}
        ready=[]
        for path in sorted(self.folder.iterdir()):
            if path.suffix.lower() not in ARCHIVE_DOCUMENTS or not path.is_file():
                continue
            stat=path.stat()
            stamp=(stat.st_size,stat.st_mtime_ns)
            observed[path]=stamp
            if stamp[0] and self.previous.get(path)==stamp and (path,stamp) not in self.seen:
                ready.append(path)
                self.seen.add((path,stamp))
        self.previous=observed
        return ready
