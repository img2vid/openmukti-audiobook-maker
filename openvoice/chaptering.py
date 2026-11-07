from __future__ import annotations
import re

HEADING = re.compile(r'^(?:(?:chapter|chap\.?|part|book|section)\s+(?:\d{1,4}|[IVXLCDM]{1,12}|one|two|three|four|five|six|seven|eight|nine|ten)(?:\s*[:.\-–]\s*.*|\s+\S.*)?|\d{1,3}[.])$', re.I)


def split_chapters(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    points = [(i, line.strip()) for i, line in enumerate(lines) if HEADING.fullmatch(line.strip()) and len(line.strip()) < 110]
    if not points:
        return [('Chapter 1', text.strip())] if text.strip() else []
    chapters = []
    start = '\n'.join(lines[:points[0][0]]).strip()
    if len(start.split()) > 70:
        chapters.append(('Introduction', start))
    for j, (i, title) in enumerate(points):
        next_i = points[j+1][0] if j+1 < len(points) else len(lines)
        body = '\n'.join(lines[i:next_i]).strip()
        if body:
            chapters.append((title, body))
    return chapters
