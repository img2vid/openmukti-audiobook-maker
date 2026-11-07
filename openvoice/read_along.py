"""Export one timed narration as an EPUB 3 media overlay."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from uuid import uuid4
from xml.etree import ElementTree
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from .animated_video import load_cues
from .audiofx import audio_info


def export_epub(audio, timing, output, title, language):
    audio, timing, output = map(Path, (audio, timing, output))
    if output.resolve() in (audio.resolve(), timing.resolve()) or output.suffix.lower() != '.epub':
        raise ValueError('Choose a separate .epub output')
    if not title.strip() or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', language):
        raise ValueError('Supply a title and language tag')
    info = audio_info(audio)
    if not any(stream.get('codec_name') == 'mp3' for stream in info.get('streams', [])) or audio.suffix.lower() != '.mp3':
        raise ValueError('Choose an MP3 narration')
    duration = info['duration_seconds']
    cues = load_cues(timing, duration)
    paragraphs, clips = [], []
    last_end = 0
    total = 0
    for index, cue in enumerate(cues, 1):
        if cue.start < last_end or cue.end > duration:
            raise ValueError('Cues must be non-overlapping and within the narration')
        paragraphs.append(f'<p id="p{index}">{escape(cue.text)}</p>')
        clips.append(f'<par><text src="book.xhtml#p{index}"/><audio src="speech.mp3" '
                     f'clipBegin="{cue.start:.6f}s" clipEnd="{cue.end:.6f}s"/></par>')
        total += cue.end - cue.start
        last_end = cue.end
    title = escape(title)
    head = (f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'lang="{language}" xml:lang="{language}"><head><title>{title}</title></head><body>')
    modified = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    files = {
        'META-INF/container.xml': '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        'book.xhtml': head + f'<h1>{title}</h1>' + ''.join(paragraphs) + '</body></html>',
        'nav.xhtml': head + f'<nav epub:type="toc"><h1>Contents</h1><ol><li><a href="book.xhtml">{title}</a></li></ol></nav></body></html>',
        'overlay.smil': '<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0"><body>' + ''.join(clips) + '</body></smil>',
        'package.opf': f'''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="uid">urn:uuid:{uuid4()}</dc:identifier><dc:title>{title}</dc:title>
<dc:language>{language}</dc:language><meta property="dcterms:modified">{modified}</meta>
<meta property="media:duration">{total:.6f}s</meta><meta property="media:duration" refines="#overlay">{total:.6f}s</meta></metadata>
<manifest><item id="book" href="book.xhtml" media-type="application/xhtml+xml" media-overlay="overlay"/>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="overlay" href="overlay.smil" media-type="application/smil+xml"/>
<item id="audio" href="speech.mp3" media-type="audio/mpeg"/></manifest><spine><itemref idref="book"/></spine></package>''',
    }
    with TemporaryDirectory(dir=output.parent) as folder:
        stage = Path(folder) / 'book.epub'
        with ZipFile(stage, 'w', compression=ZIP_DEFLATED) as archive:
            archive.writestr('mimetype', 'application/epub+zip', compress_type=ZIP_STORED)
            for name, content in files.items():
                ElementTree.fromstring(content)
                archive.writestr(name, content)
            archive.write(audio, 'speech.mp3', compress_type=ZIP_STORED)
        stage.replace(output)
