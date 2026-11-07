from __future__ import annotations
import re
import codecs
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
MAX_UNCOMPRESSED = 80 * 1024 * 1024

class DocumentError(RuntimeError):
    pass

class _HTMLText(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == 'img' and not self.skip:
            self.out.append(' ' + (dict(attrs).get('alt') or '') + ' ')
        if tag in ('td', 'th') and not self.skip:
            self.out.append('  ')
        if tag in ('script', 'style'):
            self.skip += 1
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'li', 'tr', 'section'):
            self.out.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li', 'tr', 'section'):
            self.out.append('\n')

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)

def html_to_text(source: str) -> str:
    parser = _HTMLText()
    parser.feed(source)
    return ''.join(parser.out)

def _safe_zip_read(z: zipfile.ZipFile, item: str) -> bytes:
    obj = z.getinfo(item)
    if obj.file_size > MAX_UNCOMPRESSED:
        raise DocumentError('Document part is too large')
    return z.read(item)

def _docx_text(path: Path, footnotes='inline', tables='plain') -> str:
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(_safe_zip_read(z, 'word/document.xml'))
        notes = {}
        if 'word/footnotes.xml' in z.namelist():
            tree = ET.fromstring(_safe_zip_read(z, 'word/footnotes.xml'))
            for note in tree.findall(ns + 'footnote'):
                # WordprocessingML stores footnote text inside <w:p>/<w:r>/<w:t>.
                # Include only text nodes, not every XML node's .itertext(),
                # which can duplicate text and accidentally include metadata.
                fragments = [''.join(t.text or '' for t in para.iter(ns + 't'))
                             for para in note.iter(ns + 'p')]
                notes[note.get(ns + 'id')] = ' '.join(part for part in fragments if part).strip()
    used_notes = {}
    def paragraph(p):
        bits = []
        for node in p.iter():
            if node.tag == ns + 't':
                bits.append(node.text or '')
            elif node.tag == ns + 'tab':
                bits.append('\t')
            elif node.tag == ns + 'br':
                bits.append('\n')
            elif node.tag == ns + 'footnoteReference':
                note = notes.get(node.get(ns+'id'))
                if note:
                    index = node.get(ns+'id')
                    used_notes[index] = note
                    if footnotes == 'inline':
                        bits.append(' (' + note + ') ')
                    elif footnotes == 'end':
                        bits.append(' [note ' + index + ']')
            elif node.tag.endswith('}docPr') and node.get('descr'):
                bits.append(' ' + node.get('descr') + ' ')
        return ''.join(bits)
    def blocks(node):
        for child in node:
            if child.tag == ns+'p':
                yield paragraph(child)
            elif child.tag == ns+'tbl' and tables == 'describe':
                rows = [[' '.join(blocks(cell)).strip() for cell in row.findall(ns+'tc')]
                        for row in child.findall(ns+'tr')]
                if not rows:
                    continue
                if len(rows) == 1:
                    yield 'Table. ' + '. '.join(rows[0])
                else:
                    yield 'Table. Columns: ' + ', '.join(rows[0]) + '.'
                    for index, row in enumerate(rows[1:], 1):
                        yield 'Row ' + str(index) + '. ' + '. '.join(
                            (rows[0][i] if i < len(rows[0]) and rows[0][i] else 'Column '+str(i+1)) +
                            ': ' + value for i,value in enumerate(row))
            elif child.tag == ns+'tr':
                cells = (' '.join(blocks(cell)) for cell in child.findall(ns+'tc'))
                yield ' | '.join(cells)
            else:
                yield from blocks(child)
    result = '\n'.join(blocks(root))
    if footnotes == 'end' and used_notes:
        result += '\n\nFootnotes\n' + '\n'.join(f'{i}. {n}' for i,n in used_notes.items())
    return result

def _epub_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(_safe_zip_read(z, 'META-INF/container.xml'))
        opf_path = next((node.attrib['full-path'] for node in container.iter() if node.tag.endswith('rootfile')), None)
        if opf_path is None:
            raise DocumentError('EPUB package file is missing')
        opf = ET.fromstring(_safe_zip_read(z, opf_path))
        manifest = {node.attrib.get('id'): node.attrib.get('href') for node in opf.iter() if node.tag.endswith('item') and node.attrib.get('id') and node.attrib.get('href')}
        spine = [node.attrib['idref'] for node in opf.iter() if node.tag.endswith('itemref') and node.attrib.get('idref')]
        root_dir = PurePosixPath(opf_path).parent
        chapters = []
        for item_id in spine:
            href = manifest.get(item_id)
            if not href:
                continue
            href = href.split('#')[0].split('?')[0]
            candidate = root_dir.joinpath(href)
            parts = []
            for p in candidate.parts:
                if p == '..':
                    if parts:
                        parts.pop()
                    else:
                        raise DocumentError('Unsafe EPUB path')
                elif p not in ('.', '/'):
                    parts.append(p)
            entry = '/'.join(parts)
            if entry.lower().endswith(('.xhtml', '.html', '.htm')):
                chapters.append(html_to_text(_safe_zip_read(z, entry).decode('utf-8-sig', errors='replace')))
        return '\n\n'.join(chapters)

def _decode_text_file(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_UNCOMPRESSED:
        raise DocumentError('Input text exceeds the size limit')
    if raw.startswith((codecs.BOM_UTF32_BE, codecs.BOM_UTF32_LE)):
        return raw.decode('utf-32')
    if raw.startswith((codecs.BOM_UTF16_BE, codecs.BOM_UTF16_LE)):
        return raw.decode('utf-16')
    if len(raw) >= 4 and len(raw) % 2 == 0:
        for offset, encoding in ((1, 'utf-16-le'), (0, 'utf-16-be')):
            if raw[offset::2].count(0) > len(raw) // 4:
                return raw.decode(encoding)
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeError:
            pass
    return raw.decode('utf-8', errors='replace')

ARCHIVE_DOCUMENTS = {'.txt', '.md', '.markdown', '.html', '.htm', '.fb2', '.odt',
                     '.epub', '.docx', '.rtf', '.srt', '.vtt', '.pdf', '.mobi', '.azw', '.azw3', '.prc'}


def document_members(archive):
    return [item for item in archive.infolist()
            if not item.is_dir() and not any(part.startswith(('.', '__MACOSX')) for part in PurePosixPath(item.filename).parts)
            and PurePosixPath(item.filename).suffix.lower() in ARCHIVE_DOCUMENTS]


def use_scan_dialog(path):
    from .ocr import SCAN_EXTENSIONS
    path = Path(path)
    if path.suffix.lower() == '.zip':
        try:
            with zipfile.ZipFile(path) as archive:
                return not document_members(archive)
        except (OSError, zipfile.BadZipFile):
            return False
    return path.suffix.lower() in SCAN_EXTENSIONS


def structured_text(path):
    if path.suffix.lower() == '.odt':
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(_safe_zip_read(archive, 'content.xml'))
        body = root.find('.//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text')
        tags = {'p', 'h'}
    else:
        if path.stat().st_size > MAX_UNCOMPRESSED:
            raise DocumentError('FictionBook exceeds the size limit')
        root = ET.parse(path).getroot()
        body = root.find('{*}body')
        tags = {'p', 'v', 'subtitle', 'text-author'}
    if body is None:
        raise DocumentError('Book has no text body')
    paragraphs = []
    for node in body.iter():
        tag = node.tag.rsplit('}', 1)[-1]
        if tag in {'s', 'tab', 'line-break'}:
            node.text = {'s': ' ', 'tab': '\t', 'line-break': '\n'}[tag]
    for node in body.iter():
        if node.tag.rsplit('}', 1)[-1] in tags:
            paragraphs.append(''.join(node.itertext()))
    return '\n\n'.join(paragraphs)


def read_document(path: str | Path, *, ocr_settings=None, progress=None, cancel=None, footnotes='inline', tables='plain', _archive_member=False) -> str:
    path = Path(path)
    from .desktop_prefs import authorized
    if not _archive_member:authorized('folders',path)
    ext = path.suffix.lower()
    try:
        if footnotes not in ('inline','end','skip') or tables not in ('plain','describe'):
            raise DocumentError('Invalid footnote or table narration rule')
        if ext in ('.mobi','.azw','.azw3','.prc'):
            from .import_studio import read_kindle
            return read_kindle(path)
        if ext in ('.txt', '.md', '.markdown', '.csv', '.log', '.json', '.xml'):
            return _decode_text_file(path)
        if ext in ('.html', '.htm'):
            return html_to_text(_decode_text_file(path))
        if ext in ('.srt', '.vtt'):
            text = _decode_text_file(path)
            text = re.sub('(?m)^\\s*\\d+\\s*$', '', text)
            text = re.sub('(?m)^.*\\d\\d:\\d\\d:\\d\\d[.,]\\d+\\s*-->.*$', '', text)
            text = re.sub('(?m)^.*\\d\\d:\\d\\d[.,]\\d+\\s*-->.*$', '', text)
            return text.replace('WEBVTT', '', 1)
        if ext in ('.fb2', '.odt'):
            return structured_text(path)
        if ext == '.zip':
            with zipfile.ZipFile(path) as archive:
                members = document_members(archive)
                if members:
                    if len(members) > 1000 or sum(item.file_size for item in members) > MAX_UNCOMPRESSED:
                        raise DocumentError('Document collection exceeds import limits')
                    parts = []
                    total = 0
                    with tempfile.TemporaryDirectory() as folder:
                        for item in members:
                            local = Path(folder) / ('document' + PurePosixPath(item.filename).suffix.lower())
                            local.write_bytes(archive.read(item))
                            part = read_document(local, ocr_settings=ocr_settings, progress=progress, cancel=cancel, footnotes=footnotes, tables=tables, _archive_member=True)
                            total += len(part)
                            if total > MAX_UNCOMPRESSED:
                                raise DocumentError('Imported collection exceeds text limit')
                            parts.append(part)
                            local.unlink()
                    return '\n\n'.join(parts)
        if ext == '.docx':
            return _docx_text(path, footnotes, tables)
        if ext == '.epub':
            return _epub_text(path)
        if ext == '.pdf':
            # Assess every PDF page independently, including mixed text/scan
            # books. Fall back to the original text reader when OCR extras are
            # absent and the PDF already has a complete text layer.
            from .ocr import import_ocr
            try:
                import importlib.util
                from .ocr_sidecar import find_worker
                can_render = importlib.util.find_spec('pypdfium2') is not None or find_worker() is not None
                if can_render:
                    return import_ocr(path, ocr_settings, progress=progress, cancel=cancel).text
                from pypdf import PdfReader
                texts = [(page.extract_text() or '') for page in PdfReader(str(path)).pages]
                if any(not text.strip() for text in texts):
                    raise DocumentError('This PDF contains scanned or blank pages. Install OCR support with: python -m pip install ".[ocr]"')
                return '\n\n'.join(texts)
            except ImportError as exc:
                raise DocumentError('PDF support requires: python -m pip install ".[ocr]"') from exc
        if ext == '.rtf':
            try:
                from striprtf.striprtf import rtf_to_text
            except ImportError as exc:
                raise DocumentError("RTF support requires: pip install 'openvoice-desktop[rtf]'") from exc
            return rtf_to_text(_decode_text_file(path))
        if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp', '.pnm', '.pgm', '.ppm', '.zip', '.cbz') or path.is_dir():
            from .ocr import import_ocr
            return import_ocr(path, ocr_settings, progress=progress, cancel=cancel).text
        raise DocumentError(f"Unsupported input format: {ext or '(none)'}")
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise DocumentError(f'Cannot read {path}: {exc}') from exc
