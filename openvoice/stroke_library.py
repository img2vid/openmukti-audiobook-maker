"""OpenMukti Stroke Studio trajectory packs.

A stroke pack stores *real trajectories*, not glyph outlines or typeface data.
Each key is an arbitrary Unicode grapheme cluster (including multi-codepoint
Indic conjuncts). This allows authors to create culturally correct stroke order
with a mouse, tablet or future digitizer on any writing system.

Format: {"format":"openmukti-strokes", "version":1, "glyphs":{
  "ক": {"strokes": [[[x,y,pressure], ...], ...]}}}
Positions and pressures are in the range [0,1]. Stroke order is significant.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 16 * 1024 * 1024

@dataclass(frozen=True)
class Trajectory:
    points: tuple[tuple[float, float, float], ...]

@dataclass(frozen=True)
class StrokeLibrary:
    glyphs: dict[str, tuple[Trajectory, ...]]

    def lookup(self, cluster: str) -> tuple[Trajectory, ...] | None:
        return self.glyphs.get(cluster)

    def save(self, filename: str | Path) -> None:
        destination = Path(filename).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = {'format':'openmukti-strokes', 'version':1, 'glyphs':{
            key:{'strokes':[[[round(x,6),round(y,6),round(p,5)] for x,y,p in stroke.points]
                            for stroke in strokes]} for key,strokes in self.glyphs.items()}}
        destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def with_glyph(self, text: str, paths: list[list[tuple[float,float,float]]]) -> StrokeLibrary:
        if not text or len(text) > 64:
            raise ValueError('A stroke template must have 1-64 Unicode characters')
        trajectories = tuple(Trajectory(tuple(tuple(map(float,p)) for p in path)) for path in paths)
        _check_entry(text, trajectories)
        return StrokeLibrary({**self.glyphs, text:trajectories})


def _check_entry(key: str, strokes: tuple[Trajectory, ...]):
    if not isinstance(key,str) or not key or len(key)>64 or not 1 <= len(strokes) <= 128:
        raise ValueError('Invalid character label or stroke count in pen library')
    for path in strokes:
        if not 1 <= len(path.points) <= 4096:
            raise ValueError('Each stroke must contain 1-4096 points')
        for point in path.points:
            if len(point) != 3 or not all(isinstance(v,(int,float)) and math.isfinite(v) and 0<=v<=1 for v in point):
                raise ValueError('Stroke coordinates/pressure must be numbers between 0 and 1')


def load_stroke_library(filename: str | Path | None) -> StrokeLibrary:
    if not filename:
        return StrokeLibrary({})
    source=Path(filename).expanduser()
    if source.stat().st_size > MAX_BYTES:
        raise ValueError('Stroke library exceeds 16 MB; split it into smaller packs')
    data=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or data.get('format')!='openmukti-strokes' or data.get('version') != 1:
        raise ValueError('Expected a version 1 OpenMukti stroke library JSON')
    entries=data.get('glyphs')
    if not isinstance(entries,dict) or len(entries)>5000:
        raise ValueError('Stroke pack must contain up to 5000 characters')
    glyphs={}
    for key, entry in entries.items():
        if not isinstance(entry,dict) or not isinstance(entry.get('strokes'),list):
            raise ValueError('Malformed stroke pack entry')
        strokes=tuple(Trajectory(tuple(tuple(point) for point in points)) for points in entry['strokes'])
        _check_entry(key,strokes)
        glyphs[key]=strokes
    return StrokeLibrary(glyphs)
