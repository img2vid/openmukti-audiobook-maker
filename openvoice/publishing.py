"""Publishing and export tools: ASS subtitles, transcript documents,
audiobook samples, naming rules, release notes and attribution documents.

Everything works offline. ASS export reuses the same timed cues as the
SRT/WebVTT exporter. The transcript writer produces clean HTML and a
dependency-free, text-only PDF using the built-in PDF core fonts.
"""
from __future__ import annotations
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path


# --- ASS subtitles (feature: styled subtitle export) --------------------

def _ass_clock(seconds: float) -> str:
    centiseconds = int(round(max(0.0, seconds) * 100))
    seconds_part, cs = divmod(centiseconds, 100)
    minutes, sec = divmod(seconds_part, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours}:{minutes:02}:{sec:02}.{cs:02}'


def ass_export(source: str | Path, target: str | Path, *, font: str = 'Arial',
               size: int = 48, primary: str = '&H00FFFFFF', outline: str = '&H80000000',
               alignment: int = 2, title: str = 'Openmukti Audiobook') -> Path:
    """Export timed cues (JSON/SRT/VTT) as styled ASS subtitles.

    ``alignment`` follows the ASS numpad convention (2 = bottom center).
    Colors use ASS ``&HAABBGGRR`` notation. Newlines inside cues become
    ASS line breaks; timing is converted to centisecond precision.
    """
    from .animated_video import load_cues
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('Select a separate subtitle output')
    if target.suffix.lower() != '.ass':
        raise ValueError('ASS export requires an .ass output file')
    if not 1 <= alignment <= 9:
        raise ValueError('ASS alignment must be 1..9 (numpad positions)')
    if not 4 <= size <= 300:
        raise ValueError('ASS font size must be 4..300')
    for color in (primary, outline):
        if not re.fullmatch(r'&H[0-9A-Fa-f]{8}', color):
            raise ValueError(f'Invalid ASS color: {color!r} (expected &HAABBGGRR)')
    cues = load_cues(source, float('inf'))
    if not cues:
        raise ValueError('No timed cues found in the source file')
    header = [
        '[Script Info]', f'Title: {title}', 'ScriptType: v4.00+',
        'WrapStyle: 0', 'ScaledBorderAndShadow: yes', 'YCbCr Matrix: TV.709', '',
        '[V4+ Styles]',
        'Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, '
        'Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, '
        'BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
        f'Style: Default,{font},{size},{primary},{outline},&H64000000,'
        f'0,0,0,0,100,100,0,0,1,2,1,{alignment},30,30,40,1', '',
        '[Events]',
        'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',
    ]
    events = []
    for cue in cues:
        body = escape(cue.text, quote=False).replace('\n', r'\N')
        start, end = _ass_clock(cue.start), _ass_clock(max(cue.end, cue.start + 0.01))
        events.append(f'Dialogue: 0,{start},{end},Default,,0,0,0,,{body}')
    target.write_text('\n'.join(header + events) + '\n', encoding='utf-8')
    return target


# --- export naming rules ------------------------------------------------

_NAME_TOKEN = re.compile(r'\{([a-z]+)(?::([^}]*))?\}')
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def render_name(pattern: str, context: dict, *, max_length: int = 180) -> str:
    """Render a filename from a pattern with ``{token}`` placeholders.

    Supported tokens: ``title``, ``author``, ``chapter``, ``number``
    (zero-padded with ``{number:03}``), ``language``, ``date``, ``narrator``,
    ``ext``. Unknown tokens raise an error rather than leaking into file
    names. Result is sanitized for all supported filesystems.
    """
    if not pattern.strip():
        raise ValueError('Choose a naming pattern')

    def substitute(match: re.Match) -> str:
        token, fmt = match.group(1), match.group(2)
        if token not in ('title', 'author', 'chapter', 'number', 'language', 'date', 'narrator', 'ext'):
            raise ValueError(f'Unknown naming token: {{{token}}}')
        value = context.get(token, '')
        if token == 'number':
            try:
                number = int(value if value != '' else 0)
            except (TypeError, ValueError) as exc:
                raise ValueError('The {number} token needs an integer context value') from exc
            width = int(fmt) if fmt and fmt.isdigit() else 0
            return f'{number:0{width}d}' if width else str(number)
        return str(value)

    name = _NAME_TOKEN.sub(substitute, pattern)
    name = _UNSAFE.sub('_', name)
    name = re.sub(r'\s+', ' ', name).strip(' .')
    if not name:
        raise ValueError('Naming pattern produced an empty file name')
    if name in ('.', '..') or name.casefold() in {'con', 'prn', 'aux', 'nul'} | {f'com{i}' for i in range(1, 10)} | {f'lpt{i}' for i in range(1, 10)}:
        raise ValueError(f'Naming pattern produced a reserved file name: {name}')
    return name[:max_length]


def name_chapters(pattern: str, chapters: list[str], context: dict) -> list[str]:
    """Apply a naming pattern to chapter titles, resolving collisions."""
    names, seen = [], {}
    for index, chapter in enumerate(chapters, 1):
        local = dict(context, chapter=chapter, number=index)
        base = render_name(pattern, local)
        count = seen.get(base.casefold(), 0)
        seen[base.casefold()] = count + 1
        names.append(base if count == 0 else f'{base}-{count + 1}')
    return names


# --- audiobook samples --------------------------------------------------

def create_sample(source: str | Path, target: str | Path, *, start: float = 0.0,
                  duration: float = 60.0, fade_seconds: float = 2.0) -> Path:
    """Cut a promotional excerpt with fade-in/out using FFmpeg."""
    from .fftools import find_binary
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError('Sample output must differ from the source')
    if duration <= 0 or duration > 3600:
        raise ValueError('Sample duration must be 0..3600 seconds')
    if start < 0:
        raise ValueError('Sample start must not be negative')
    fade = min(fade_seconds, duration / 2)
    executable = find_binary('ffmpeg')
    if not executable:
        raise RuntimeError('Sample generation requires FFmpeg')
    filters = f'afade=t=in:st=0:d={fade:g},afade=t=out:st={duration - fade:g}:d={fade:g}'
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=target.suffix, delete=False) as handle:
        stage = Path(handle.name)
    try:
        subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
                        '-ss', f'{start:g}', '-t', f'{duration:g}', '-i', str(source),
                        '-af', filters, str(stage)], check=True)
        stage.replace(target)
    finally:
        stage.unlink(missing_ok=True)
    return target


# --- release notes and attribution --------------------------------------

def release_notes(version: str, changes: list[dict], *, title: str = '') -> str:
    """Generate Markdown release notes from structured change entries.

    Each change is ``{'kind': 'added|fixed|changed|removed', 'text': ...}``
    and may carry ``chapters: [...]`` to document corrected chapters.
    """
    kinds = ('added', 'fixed', 'changed', 'removed')
    grouped: dict[str, list[dict]] = {k: [] for k in kinds}
    for change in changes:
        kind = str(change.get('kind', '')).casefold()
        if kind not in grouped:
            raise ValueError(f'Change kind must be one of: {", ".join(kinds)}')
        text = str(change.get('text', '')).strip()
        if not text:
            raise ValueError('Change entries need text')
        grouped[kind].append(change)
    heading = title.strip() or 'Audiobook Release'
    rows = [f'# {heading} — {version}', '',
            f'Generated {datetime.now(timezone.utc):%Y-%m-%d}.', '']
    labels = {'added': 'Added', 'fixed': 'Fixed', 'changed': 'Changed', 'removed': 'Removed'}
    for kind in kinds:
        if not grouped[kind]:
            continue
        rows.append(f'## {labels[kind]}')
        rows.append('')
        for change in grouped[kind]:
            line = f'- {change["text"].strip()}'
            chapters = change.get('chapters')
            if chapters:
                line += f" (chapters: {', '.join(str(c) for c in chapters)})"
            rows.append(line)
        rows.append('')
    return '\n'.join(rows).rstrip() + '\n'


def attribution_document(project_title: str, assets: list[dict], *,
                         author: str = '', narrator: str = '') -> str:
    """Compile a credits and licensing document from asset records.

    Each asset is ``{'name': ..., 'type': 'voice|music|image|font|sound',
    'source': ..., 'license': ..., 'attribution': ...}``. Assets requiring
    attribution are grouped at the top so nothing is missed at release.
    """
    rows = [f'# Credits and Attributions — {project_title}', '']
    if author:
        rows.append(f'**Author:** {author}  ')
    if narrator:
        rows.append(f'**Narrator:** {narrator}  ')
    rows.append('')
    rows.append(f'Produced with Openmukti Audiobook Maker on {datetime.now(timezone.utc):%Y-%m-%d}.')
    rows.append('')
    required = [a for a in assets if str(a.get('attribution', '')).strip()]
    optional = [a for a in assets if not str(a.get('attribution', '')).strip()]
    if required:
        rows += ['## Required attributions', '']
        for asset in required:
            rows.append(f"- **{asset.get('name', 'Unnamed asset')}** ({asset.get('type', 'asset')}): "
                        f"{asset['attribution'].strip()}"
                        + (f" License: {asset['license'].strip()}." if str(asset.get('license', '')).strip() else ''))
        rows.append('')
    if optional:
        rows += ['## Other assets', '']
        for asset in optional:
            parts = [f"**{asset.get('name', 'Unnamed asset')}** ({asset.get('type', 'asset')})"]
            if str(asset.get('source', '')).strip():
                parts.append(f"source: {asset['source'].strip()}")
            if str(asset.get('license', '')).strip():
                parts.append(f"license: {asset['license'].strip()}")
            rows.append('- ' + '; '.join(parts))
        rows.append('')
    return '\n'.join(rows).rstrip() + '\n'


# --- transcript export ---------------------------------------------------

def _pdf_escape(value: str) -> str:
    return value.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')


def _latin1(value: str) -> str:
    """Core-font PDFs encode WinAnsi; unsupported characters become '?'."""
    return value.encode('cp1252', errors='replace').decode('cp1252')


def write_transcript_pdf(target: str | Path, title: str, chapters: list[tuple[str, str]],
                         *, author: str = '', page_size: tuple[float, float] = (595.0, 842.0)) -> Path:
    """Write a dependency-free, text-only transcript PDF (A4 by default).

    Uses the PDF core Helvetica fonts, so no font files are embedded and no
    third-party packages are required. Latin-script text renders cleanly;
    scripts outside WinAnsi encoding should use the HTML export instead.
    """
    target = Path(target)
    if target.suffix.lower() != '.pdf':
        raise ValueError('Transcript PDF output needs a .pdf file name')
    width, height = page_size
    margin, leading, font_size = 56.0, 14.0, 11.0
    lines_per_page = int((height - 2 * margin) // leading)

    def wrap(text: str, width_chars: int) -> list[str]:
        out = []
        for raw in text.splitlines():
            words = raw.split()
            line = ''
            for word in words:
                candidate = (line + ' ' + word).strip()
                if len(candidate) > width_chars and line:
                    out.append(line)
                    line = word
                else:
                    line = candidate
            out.append(line)
        return out or ['']

    # Build pages of (text, size, bold) tuples.
    pages: list[list[tuple[str, float, bool]]] = [[]]
    def add_line(line: str, size: float = font_size, bold: bool = False) -> None:
        if len(pages[-1]) >= lines_per_page:
            pages.append([])
        pages[-1].append((line, size, bold))
    def emit(text: str, size: float = font_size, bold: bool = False, chars: int = 88):
        for line in wrap(_latin1(text), chars):
            add_line(line, size, bold)
    emit(title, 22, True, chars=48)
    if author:
        emit(author, 13, False, chars=70)
    add_line('')
    for heading, body in chapters:
        emit(heading, 16, True, chars=58)
        add_line('')
        for paragraph in re.split(r'\n\s*\n', body.strip()):
            emit(paragraph)
            add_line('')
    if not any(pages[-1]):
        pages.pop()

    objects: list[bytes] = []
    page_refs = []
    # Object order: 1 catalog, 2 pages, 3.. fonts and content per page.
    font_regular, font_bold = 3, 4
    next_id = 5
    page_objects = []
    for page in pages:
        content_id, page_id = next_id, next_id + 1
        next_id += 2
        commands = ['BT']
        y = height - margin
        for line, size, bold in page:
            commands.append(f'/F{2 if bold else 1} {size:g} Tf')
            commands.append(f'1 0 0 1 {margin:g} {y:g} Tm')
            commands.append(f'({_pdf_escape(line)}) Tj')
            y -= leading * (size / font_size)
        commands.append('ET')
        stream = '\n'.join(commands).encode('cp1252', errors='replace')
        page_objects.append((page_id, content_id, stream))
        page_refs.append(page_id)
    objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
    kids = ' '.join(f'{p} 0 R' for p in page_refs)
    objects.append(f'<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>'.encode())
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>')
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>')
    for page_id, content_id, stream in page_objects:
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:g} {height:g}] '
                       f'/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> '
                       f'/Contents {content_id} 0 R >>'.encode())
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    output = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{number} 0 obj\n'.encode() + body + b'\nendobj\n'
    xref = len(output)
    output += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode()
    for offset in offsets:
        output += f'{offset:010d} 00000 n \n'.encode()
    output += (f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n'
               f'startxref\n{xref}\n%%EOF\n').encode()
    target.write_bytes(bytes(output))
    return target


def transcript_html(title: str, chapters: list[tuple[str, str]], *, author: str = '') -> str:
    """Render a clean standalone HTML transcript."""
    rows = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
            f'<title>{escape(title)}</title>',
            '<style>body{font-family:Georgia,serif;max-width:44em;margin:3em auto;line-height:1.65;'
            'padding:0 1em}h1{font-size:1.9em}h2{margin-top:2.4em}p{text-align:justify}</style>',
            '</head><body>', f'<h1>{escape(title)}</h1>']
    if author:
        rows.append(f'<p><em>{escape(author)}</em></p>')
    for heading, body in chapters:
        rows.append(f'<h2>{escape(heading)}</h2>')
        for paragraph in re.split(r'\n\s*\n', body.strip()):
            if paragraph.strip():
                rows.append(f'<p>{escape(paragraph.strip())}</p>')
    rows.append('</body></html>')
    return '\n'.join(rows) + '\n'


def export_transcript(target: str | Path, title: str, chapters: list[tuple[str, str]],
                      *, author: str = '') -> Path:
    """Export a transcript as .pdf, .html, or .txt chosen by suffix."""
    target = Path(target)
    if not title.strip():
        raise ValueError('Transcript needs a book title')
    if not chapters:
        raise ValueError('Transcript needs at least one chapter')
    suffix = target.suffix.lower()
    target.parent.mkdir(parents=True, exist_ok=True)
    if suffix == '.pdf':
        return write_transcript_pdf(target, title, chapters, author=author)
    if suffix in ('.html', '.htm'):
        target.write_text(transcript_html(title, chapters, author=author), encoding='utf-8')
        return target
    if suffix == '.txt':
        blocks = [title, author, '']
        for heading, body in chapters:
            blocks += [heading.upper(), '', body.strip(), '']
        target.write_text('\n'.join(x for x in blocks if x is not None), encoding='utf-8')
        return target
    raise ValueError('Transcript output must be .pdf, .html or .txt')
