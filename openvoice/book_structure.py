"""Chapter, section and book-structure tools.

Heuristic chapter detection with configurable rules, hierarchical section
management, table-of-contents generation, scene-break detection, repeated
header/footer detection, page-number removal, duration estimation, and
chapter completion tracking. Everything is offline and CPU-only.
"""
from __future__ import annotations
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

CHAPTER_WORDS = ('chapter', 'chap\\.?', 'part', 'book', 'section', 'prologue', 'epilogue',
                 'act', 'scene', 'interlude', 'prelude', 'volume')
ROMAN = '[IVXLCDM]{1,12}'
NUMBER_WORDS = ('one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|'
                'fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty')
STATUS_ORDER = ('drafted', 'reviewed', 'completed')
MAX_TITLE_LENGTH = 140

_BUILTIN_RULES = [
    ('markdown', re.compile(r'^(#{1,6})\s+(.+?)\s*#*$')),
    ('keyword', re.compile(
        rf'^((?:{"|".join(CHAPTER_WORDS)})\s+(?:\d{{1,4}}|{ROMAN}|(?:{NUMBER_WORDS}))(?:\s*[:.\-–—]\s*.*)?)$', re.I)),
    ('numbered', re.compile(r'^(\d{1,3})[.)]\s+(.+)$')),
    ('all-caps', None),  # handled procedurally: short fully uppercase line
]


def _is_all_caps_heading(line: str) -> bool:
    letters = [c for c in line if unicodedata.category(c).startswith('L')]
    return (3 <= len(line) <= 60 and len(letters) >= 3
            and all(not c.islower() for c in letters)
            and not line.rstrip().endswith(('.', '!', '?', ',', ';', ':')))


@dataclass
class Section:
    """One chapter or section of a book, with production metadata."""
    title: str
    text: str
    level: int = 1                       # 1 part, 2 chapter, 3 subsection…
    status: str = 'drafted'              # drafted | reviewed | completed
    description: str = ''
    keywords: list[str] = field(default_factory=list)
    notes: str = ''

    def __post_init__(self) -> None:
        self.title = self.title.strip() or 'Untitled section'
        if self.status not in STATUS_ORDER:
            raise ValueError(f'Status must be one of: {", ".join(STATUS_ORDER)}')
        self.keywords = [k.strip() for k in self.keywords if k.strip()]
        self.level = min(6, max(1, int(self.level)))

    def words(self) -> int:
        return len(re.findall(r"\b[\w’'-]+\b", self.text, flags=re.UNICODE))

    def to_dict(self) -> dict:
        return asdict(self)


def detect_chapters(text: str, custom_rules: list[str] | None = None,
                    max_title_length: int = MAX_TITLE_LENGTH) -> list[Section]:
    """Split a manuscript into sections using layered heading heuristics.

    Recognized headings, highest priority first: custom regular expressions,
    Markdown ``#`` headings, ``Chapter 12`` / ``Part IV`` keyword headings,
    ``12. Title`` numbered headings, and short ALL-CAPS lines. Custom rules
    are full-line regular expressions whose first capture group (or the whole
    match) becomes the title.
    """
    if not text.strip():
        return []
    compiled_custom = []
    for rule in custom_rules or []:
        try:
            compiled_custom.append(re.compile(rule))
        except re.error as exc:
            raise ValueError(f'Invalid custom chapter rule {rule!r}: {exc}') from exc
    lines = text.splitlines()
    points: list[tuple[int, str, int]] = []  # line index, title, heading level
    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or len(line) > max_title_length:
            continue
        custom = next((rx.fullmatch(line) for rx in compiled_custom if rx.fullmatch(line)), None)
        if custom:
            points.append((i, (custom.group(1) if custom.groups() else custom.group()).strip(), 1))
            continue
        match = _BUILTIN_RULES[0][1].fullmatch(line)
        if match:
            points.append((i, match.group(2).strip(), min(6, len(match.group(1)) + 1)))
            continue
        match = _BUILTIN_RULES[1][1].fullmatch(line)
        if match:
            points.append((i, match.group(1).strip(), 1))
            continue
        match = _BUILTIN_RULES[2][1].fullmatch(line)
        if match and len(match.group(2)) >= 2:
            points.append((i, f'{match.group(1)}. {match.group(2).strip()}', 2))
            continue
        from .editorial_studio import section_kind
        if len(line.split())<=12 and not line.endswith(('.','!','?')) and section_kind(line)!='chapter':
            points.append((i,line,1))
            continue
        if _is_all_caps_heading(line):
            points.append((i, line.title() if line.isupper() else line, 1))
    sections: list[Section] = []
    front = '\n'.join(lines[:points[0][0]]).strip() if points else ''
    if front:
        sections.append(Section('Front matter', front, level=1))
    if not points:
        return [Section('Complete text', text.strip())]
    for j, (i, title, level) in enumerate(points):
        end = points[j + 1][0] if j + 1 < len(points) else len(lines)
        body = '\n'.join(lines[i + 1:end]).strip()
        sections.append(Section(title, body, level=level))
    return sections or [Section('Complete text', text.strip())]


def hierarchy(sections: list[Section]) -> list[dict]:
    """Nest flat sections into parts/chapters/subsections by heading level."""
    root: list[dict] = []
    stack: list[dict] = []
    for section in sections:
        node = {'section': section, 'children': []}
        while stack and stack[-1]['section'].level >= section.level:
            stack.pop()
        (stack[-1]['children'] if stack else root).append(node)
        stack.append(node)
    return root


def table_of_contents(sections: list[Section], *, style: str = 'markdown') -> str:
    """Render detected structure as Markdown, plain text, or JSON."""
    if style == 'json':
        return json.dumps([{'level': s.level, 'title': s.title, 'words': s.words(),
                            'status': s.status} for s in sections], ensure_ascii=False, indent=2)
    rows = []
    for index, section in enumerate(sections, 1):
        indent = '  ' * (section.level - 1)
        if style == 'markdown':
            rows.append(f'{indent}- **{section.title}** ({section.words()} words)')
        else:
            rows.append(f'{indent}{index}. {section.title}')
    return '\n'.join(rows)


def detect_scene_breaks(text: str) -> list[dict]:
    """Locate scene breaks: thematic separators or marked transitions."""
    breaks = []
    offset = 0
    separator = re.compile(r'^\s*(?:[*#_]\s*){3,}$|^\s*(?:—\s*){2,}$|^\s*-{3,}\s*$')
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped and separator.match(stripped):
            breaks.append({'line': number, 'offset': offset, 'marker': stripped})
        offset += len(line) + 1
    return breaks


def split_into_pages(text: str) -> list[str]:
    """Split text on form feeds or explicit page markers."""
    return re.split(r'\f|\n\s*---\s*PAGE\s*---\s*\n', text, flags=re.I)


def detect_headers_footers(text: str, *, min_repeats: int = 3) -> dict:
    """Detect page headers/footers repeated across form-feed pages."""
    pages = split_into_pages(text)
    if len(pages) < min_repeats:
        return {'pages': len(pages), 'headers': [], 'footers': []}

    def edge_lines(edge: str) -> list[str]:
        values = []
        for page in pages:
            lines = [x.strip() for x in page.splitlines() if x.strip()]
            if not lines:
                continue
            values.append(lines[0] if edge == 'first' else lines[-1])
        return values

    def recurring(values: list[str]) -> list[dict]:
        found = {}
        for value in values:
            key = re.sub(r'\d+', '#', value).casefold()
            found.setdefault(key, []).append(value)
        return [{'pattern': k, 'examples': sorted(set(v))[:3], 'pages': len(v)}
                for k, v in found.items() if len(v) >= min_repeats]

    return {'pages': len(pages), 'headers': recurring(edge_lines('first')),
            'footers': recurring(edge_lines('last'))}


def remove_page_numbers(text: str) -> str:
    """Remove lines containing only a printed page number."""
    pattern = re.compile(r'(?m)^[ \t]*(?:page\s+)?(?:\d{1,5}|[ivxlcdm]{1,8})[ \t]*$', re.I)
    return pattern.sub('', text)


def estimate_durations(sections: list[Section], *, wpm: int = 160,
                       pause_seconds: float = 0.8) -> dict:
    """Estimate narration time per section from word count and punctuation."""
    if wpm < 1:
        raise ValueError('Words per minute must be positive')
    estimates = []
    total = 0.0
    for section in sections:
        words = section.words()
        pauses = len(re.findall(r'[.!?…]', section.text)) * 0.35
        pauses += len(re.findall(r'[,;:—–-]', section.text)) * 0.15
        pauses += len(re.findall(r'\n\s*\n', section.text)) * pause_seconds
        seconds = words * 60.0 / wpm + pauses
        total += seconds
        estimates.append({'title': section.title, 'words': words,
                          'estimated_seconds': round(seconds, 1)})
    return {'sections': estimates, 'total_estimated_seconds': round(total, 1),
            'words_per_minute': wpm}


def reorder_sections(sections: list[Section], order: list[int]) -> list[Section]:
    """Return sections in the given 1-based order permutation."""
    if sorted(order) != list(range(1, len(sections) + 1)):
        raise ValueError(f'Order must be a permutation of 1..{len(sections)}')
    return [sections[i - 1] for i in order]


def split_section(section: Section, position: int, *, second_title: str = '') -> tuple[Section, Section]:
    """Split a section at a character offset without losing metadata."""
    if not 0 < position < len(section.text):
        raise ValueError('Split position must lie inside the section text')
    first = Section(section.title, section.text[:position].rstrip(), level=section.level,
                    status=section.status, description=section.description,
                    keywords=list(section.keywords), notes=section.notes)
    title = second_title.strip() or f'{section.title} (continued)'
    second = Section(title, section.text[position:].lstrip(), level=section.level,
                     status='drafted', keywords=list(section.keywords))
    return first, second


def merge_sections(first: Section, second: Section, *, title: str = '') -> Section:
    """Combine two adjacent sections, keeping the earlier workflow status."""
    status = first.status if STATUS_ORDER.index(first.status) <= STATUS_ORDER.index(second.status) else second.status
    merged = Section(title.strip() or first.title,
                     (first.text.rstrip() + '\n\n' + second.text.lstrip()).strip(),
                     level=min(first.level, second.level), status=status,
                     description=first.description or second.description,
                     keywords=sorted(set(first.keywords) | set(second.keywords)),
                     notes='\n'.join(x for x in (first.notes, second.notes) if x))
    return merged


# --- completion tracking ------------------------------------------------

def load_status(path: str | Path) -> dict:
    """Load a chapter-status JSON file, or start an empty one."""
    location = Path(path)
    if not location.is_file():
        return {'format': 'openmukti-chapter-status', 'version': 1, 'chapters': {}}
    data = json.loads(location.read_text(encoding='utf-8'))
    if data.get('format') != 'openmukti-chapter-status':
        raise ValueError('Unsupported chapter status file')
    return data


def set_status(path: str | Path, chapter: str, status: str) -> dict:
    """Mark a chapter as drafted, reviewed, or completed."""
    if status not in STATUS_ORDER:
        raise ValueError(f'Status must be one of: {", ".join(STATUS_ORDER)}')
    data = load_status(path)
    data['chapters'][chapter] = status
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return data


def completion_summary(path: str | Path) -> dict:
    """Summarize chapter completion counts for dashboards."""
    chapters = load_status(path).get('chapters', {})
    counts = {status: sum(1 for v in chapters.values() if v == status) for status in STATUS_ORDER}
    counts['untracked'] = 0
    counts['total'] = len(chapters)
    return counts
