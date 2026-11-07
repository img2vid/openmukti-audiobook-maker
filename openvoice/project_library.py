"""Project library: a searchable local index of audiobook projects.

The library is a single JSON document (by default ``library.json`` in a
folder of the user's choice) recording project files with their category,
tags, favorite flag, notes and bookmarks. It never moves or modifies the
indexed project files; entries point at existing paths and are validated
on demand.

Implements library-level features: global project search, batch renaming,
categories, tags, favorites, notes, bookmarks, duplicate detection,
storage analysis, health checks and long-term archiving.
"""
from __future__ import annotations
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

FORMAT = 'openmukti-library'
VERSION = 1
MAX_NOTE_LENGTH = 100000
MAX_TAG_LENGTH = 120
AUDIO_SUFFIXES = {'.wav', '.mp3', '.flac', '.ogg', '.opus', '.aac', '.m4a', '.m4b', '.aiff', '.wma'}
VIDEO_SUFFIXES = {'.mp4', '.mkv', '.mov', '.webm', '.avi'}
MODEL_SUFFIXES = {'.onnx', '.bin', '.pt', '.pth', '.safetensors', '.gguf', '.tflite'}
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.svg'}
FONT_SUFFIXES = {'.ttf', '.otf', '.ttc', '.woff', '.woff2'}
TEXT_SUFFIXES = {'.txt', '.md', '.rtf', '.docx', '.odt', '.epub', '.fb2', '.html', '.htm', '.pdf'}
CACHE_NAMES = {'cache', 'caches', '.cache', 'tmp', 'temp', '__pycache__'}


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _clean_tag(value: str) -> str:
    tag = ' '.join(str(value).split()).strip().casefold()
    if not tag:
        raise ValueError('Tag must not be empty')
    if len(tag) > MAX_TAG_LENGTH:
        raise ValueError(f'Tag is longer than {MAX_TAG_LENGTH} characters')
    return tag


@dataclass
class Bookmark:
    """A named position or task reminder inside a project."""
    name: str
    note: str = ''
    position: int = 0
    created: str = ''

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError('Bookmark name must not be empty')
        if self.position < 0:
            raise ValueError('Bookmark position must be 0 or greater')
        if not self.created:
            self.created = _now()


@dataclass
class LibraryEntry:
    """One indexed project file with its organizational metadata."""
    path: str
    name: str = ''
    category: str = 'uncategorized'
    tags: list[str] = field(default_factory=list)
    favorite: bool = False
    notes: str = ''
    bookmarks: list[Bookmark] = field(default_factory=list)
    added: str = ''
    modified: str = ''

    def __post_init__(self) -> None:
        if not self.name:
            self.name = Path(self.path).stem
        self.category = ' '.join(str(self.category).split()) or 'uncategorized'
        self.tags = sorted({_clean_tag(t) for t in self.tags})
        if len(self.notes) > MAX_NOTE_LENGTH:
            raise ValueError(f'Project notes exceed {MAX_NOTE_LENGTH} characters')
        stamp = _now()
        if not self.added:
            self.added = stamp
        if not self.modified:
            self.modified = stamp

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


class ProjectLibrary:
    """Load, edit and save a project library index."""

    def __init__(self, index_file: str | Path):
        self.index_file = Path(index_file).expanduser().resolve()
        self.entries: list[LibraryEntry] = []
        if self.index_file.is_file():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.index_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f'Cannot read project library: {exc}') from exc
        if not isinstance(data, dict) or data.get('format') != FORMAT:
            raise ValueError('Unsupported project library format')
        if int(data.get('version', 0)) > VERSION:
            raise ValueError('Project library was saved by a newer application version')
        entries = []
        for item in data.get('projects', []):
            if not isinstance(item, dict) or not item.get('path'):
                raise ValueError('Project library contains an invalid entry')
            bookmarks = [Bookmark(**b) for b in item.get('bookmarks', [])]
            item = {k: v for k, v in item.items() if k != 'bookmarks'}
            entries.append(LibraryEntry(bookmarks=bookmarks, **item))
        self.entries = entries

    def save(self) -> Path:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {'format': FORMAT, 'version': VERSION, 'saved': _now(),
                   'projects': [e.to_dict() for e in self.entries]}
        self.index_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return self.index_file

    # --- membership -----------------------------------------------------
    def find(self, path_or_name: str) -> LibraryEntry:
        key = str(path_or_name)
        for entry in self.entries:
            if entry.path == key or entry.name == key:
                return entry
        resolved = str(Path(key).expanduser().resolve())
        if resolved != key:
            for entry in self.entries:
                if entry.path == resolved:
                    return entry
        raise ValueError(f'Project is not in the library: {path_or_name}')

    def add(self, path: str | Path, *, category: str = 'uncategorized',
            tags: list[str] | None = None, favorite: bool = False, name: str = '') -> LibraryEntry:
        location = str(Path(path).expanduser().resolve())
        if not Path(location).exists():
            raise FileNotFoundError(f'Project does not exist: {location}')
        for entry in self.entries:
            if entry.path == location:
                raise ValueError(f'Project is already in the library: {location}')
        entry = LibraryEntry(path=location, name=name, category=category,
                             tags=list(tags or []), favorite=favorite)
        self.entries.append(entry)
        return entry

    def remove(self, path_or_name: str) -> LibraryEntry:
        entry = self.find(path_or_name)
        self.entries.remove(entry)
        return entry

    # --- organization ---------------------------------------------------
    def set_category(self, path_or_name: str, category: str) -> LibraryEntry:
        entry = self.find(path_or_name)
        entry.category = ' '.join(str(category).split()) or 'uncategorized'
        entry.modified = _now()
        return entry

    def set_tags(self, path_or_name: str, tags: list[str]) -> LibraryEntry:
        entry = self.find(path_or_name)
        entry.tags = sorted({_clean_tag(t) for t in tags})
        entry.modified = _now()
        return entry

    def set_favorite(self, path_or_name: str, favorite: bool = True) -> LibraryEntry:
        entry = self.find(path_or_name)
        entry.favorite = bool(favorite)
        entry.modified = _now()
        return entry

    def set_notes(self, path_or_name: str, notes: str) -> LibraryEntry:
        entry = self.find(path_or_name)
        if len(notes) > MAX_NOTE_LENGTH:
            raise ValueError(f'Project notes exceed {MAX_NOTE_LENGTH} characters')
        entry.notes = notes
        entry.modified = _now()
        return entry

    def add_bookmark(self, path_or_name: str, name: str, note: str = '', position: int = 0) -> Bookmark:
        entry = self.find(path_or_name)
        bookmark = Bookmark(name=name, note=note, position=position)
        entry.bookmarks = [b for b in entry.bookmarks if b.name != bookmark.name]
        entry.bookmarks.append(bookmark)
        entry.modified = _now()
        return bookmark

    # --- search ---------------------------------------------------------
    def search(self, query: str = '', *, category: str = '', tag: str = '',
               favorites_only: bool = False, include_project_text: bool = False) -> list[LibraryEntry]:
        """Search names, categories, tags and notes; optionally project text.

        Text search reads the ``text`` field of ``.oamproj`` manifests without
        extracting bundled assets, so large projects stay fast to search.
        """
        needle = ' '.join(str(query).split()).casefold()
        tag_needle = _clean_tag(tag) if tag else ''
        results = []
        for entry in self.entries:
            if favorites_only and not entry.favorite:
                continue
            if category and entry.category.casefold() != category.casefold():
                continue
            if tag_needle and tag_needle not in entry.tags:
                continue
            if needle:
                haystack = '\n'.join([entry.name, entry.category, entry.notes, ' '.join(entry.tags)]).casefold()
                if needle not in haystack:
                    if include_project_text and needle in read_project_text(entry.path).casefold():
                        results.append(entry)
                    continue
            results.append(entry)
        return sorted(results, key=lambda e: (not e.favorite, e.name.casefold()))

    def categories(self) -> list[str]:
        return sorted({e.category for e in self.entries}, key=str.casefold)

    def all_tags(self) -> list[str]:
        return sorted({t for e in self.entries for t in e.tags})

    # --- batch renaming -------------------------------------------------
    def batch_rename(self, pattern: str, replacement: str, *, regex: bool = False,
                     dry_run: bool = False) -> list[tuple[str, str]]:
        """Rename library display names; optionally rename files on disk.

        With ``regex`` the pattern is a regular expression and the replacement
        may use backreferences such as ``\\1``. Returns ``(old, new)`` pairs.
        File renaming applies only to regular files, refuses collisions, and
        updates the stored path so the index never points at stale names.
        """
        if not pattern:
            raise ValueError('Choose a rename pattern')
        matcher = re.compile(pattern) if regex else None
        planned: list[tuple[LibraryEntry, str]] = []
        for entry in self.entries:
            new_name = matcher.sub(replacement, entry.name) if matcher else entry.name.replace(pattern, replacement)
            new_name = new_name.strip()
            if new_name and new_name != entry.name:
                planned.append((entry, new_name))
        taken = {e.name.casefold() for e in self.entries if all(e is not p for p, _ in planned)}
        new_names = [name.casefold() for _, name in planned]
        if len(new_names) != len(set(new_names)):
            raise ValueError('Batch rename would map several projects to the same name')
        for _, new_name in planned:
            if new_name.casefold() in taken:
                raise ValueError(f'Batch rename would create a duplicate name: {new_name}')
        changes = []
        for entry, new_name in planned:
            changes.append((entry.name, new_name))
            if not dry_run:
                entry.name = new_name
                entry.modified = _now()
        return changes

    # --- analysis -------------------------------------------------------
    def duplicates(self) -> list[list[LibraryEntry]]:
        """Group entries whose project files have identical SHA-256 content."""
        hashes: dict[str, list[LibraryEntry]] = {}
        for entry in self.entries:
            path = Path(entry.path)
            if not path.is_file():
                continue
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            hashes.setdefault(digest.hexdigest(), []).append(entry)
        return [group for group in hashes.values() if len(group) > 1]

    def storage_analysis(self, folder: str | Path) -> dict:
        """Summarize disk usage by content class below a folder."""
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise FileNotFoundError(f'Folder does not exist: {root}')
        groups = {'audio': 0, 'video': 0, 'models': 0, 'images': 0, 'fonts': 0,
                  'text': 0, 'cache': 0, 'other': 0}
        files = 0
        for path in root.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            files += 1
            size = path.stat().st_size
            suffix = path.suffix.lower()
            if any(part.casefold() in CACHE_NAMES for part in path.relative_to(root).parts[:-1]):
                groups['cache'] += size
            elif suffix in AUDIO_SUFFIXES:
                groups['audio'] += size
            elif suffix in VIDEO_SUFFIXES:
                groups['video'] += size
            elif suffix in MODEL_SUFFIXES:
                groups['models'] += size
            elif suffix in IMAGE_SUFFIXES:
                groups['images'] += size
            elif suffix in FONT_SUFFIXES:
                groups['fonts'] += size
            elif suffix in TEXT_SUFFIXES:
                groups['text'] += size
            else:
                groups['other'] += size
        return {'folder': str(root), 'files': files, 'bytes_by_group': groups,
                'total_bytes': sum(groups.values())}


def read_project_text(path: str | Path) -> str:
    """Read the manuscript text of a .oamproj without extracting assets."""
    location = Path(path).expanduser().resolve()
    if location.suffix.lower() != '.oamproj' or not location.is_file():
        return ''
    try:
        with zipfile.ZipFile(location, 'r') as archive:
            data = json.loads(archive.read('project.json'))
    except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        return ''
    if not isinstance(data, dict) or data.get('format') != 'openmukti-project':
        return ''
    return str(data.get('text', ''))


def health_check(path: str | Path) -> dict:
    """Validate a project file and report problems without modifying it.

    For ``.oamproj`` packages this verifies the manifest structure, the
    resource table, and the ZIP integrity (CRC) of every bundled asset.
    For other files it reports existence, readability and size.
    """
    location = Path(path).expanduser().resolve()
    problems: list[str] = []
    warnings: list[str] = []
    if not location.exists():
        return {'path': str(location), 'healthy': False, 'problems': ['File does not exist'], 'warnings': []}
    if not location.is_file():
        return {'path': str(location), 'healthy': False, 'problems': ['Path is not a file'], 'warnings': []}
    size = location.stat().st_size
    if location.suffix.lower() == '.oamproj':
        try:
            with zipfile.ZipFile(location, 'r') as archive:
                names = archive.namelist()
                if names.count('project.json') != 1:
                    problems.append('Missing or duplicated project.json manifest')
                else:
                    data = json.loads(archive.read('project.json'))
                    if data.get('format') != 'openmukti-project':
                        problems.append('Unrecognized project format marker')
                    resources = data.get('resources', {})
                    missing = sorted(set(resources) - set(names))
                    extra = sorted(set(names) - set(resources) - {'project.json'})
                    if missing:
                        problems.append(f'Missing bundled assets: {len(missing)}')
                    if extra:
                        warnings.append(f'Unexpected extra files: {len(extra)}')
                    if not str(data.get('text', '')).strip():
                        warnings.append('Project contains no text')
                damaged = archive.testzip()
                if damaged:
                    problems.append(f'Corrupt archive member: {damaged}')
        except zipfile.BadZipFile:
            problems.append('File is not a readable project archive')
        except (json.JSONDecodeError, AttributeError) as exc:
            problems.append(f'Manifest is not readable: {exc}')
    elif size == 0:
        problems.append('File is empty')
    return {'path': str(location), 'healthy': not problems, 'problems': problems,
            'warnings': warnings, 'size_bytes': size}
