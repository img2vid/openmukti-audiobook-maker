"""Unicode-aware audiobook video: typewriter or real stroke-painted ink.

Supports optional hand-authored trajectories via Stroke Studio. Automatic
medial-axis path reconstruction is a fallback; its output is pen-painted but it
cannot substitute for a real person's handwriting or traditional stroke order.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from .progress import emit
from .text_layout import load_font, text_length, draw_text, layout_status

MODES = ('none', 'typewriter', 'handwriting', 'calligraphy', 'scroll-up',
         'scroll-down', 'scroll-left', 'scroll-right', 'slide-up', 'slide-down',
         'slide-left', 'slide-right', 'fade', 'zoom', 'karaoke', 'static')


@dataclass(frozen=True)
class TimedToken:
    text: str
    prefix: str
    start: float
    end: float


@dataclass(frozen=True)
class CaptionCue:
    start: float
    end: float
    text: str


def visible_book_text(text: str) -> str:
    """Remove character-control markers, not the natural-language text."""
    from .ipa_pronunciation import display_inline_ipa
    return display_inline_ipa(re.sub(r'(?m)(?<!\w)\[(?:Narrator|[\w][^\]\n]{0,159})\](?=\s|$)', '', text, flags=re.I)).strip()


def graphemes(text: str) -> list[str]:
    try:
        import regex
        clusters=regex.findall(r'\X',text)
    except ImportError:
        clusters=list(text)
    # Some installed regex versions predate Indic conjunct rules (GB9c).
    # Also keep spacing vowel signs, ZWJ sequences and emoji modifiers intact
    # in the standard-library fallback.
    result=[]
    for cluster in clusters:
        char=cluster[0]
        previous=result[-1] if result else ''
        last=previous.rstrip('\u200d\u200c')[-1:] if previous else ''
        linker=bool(last and ('VIRAMA' in unicodedata.name(last,'') or 'HALANT' in unicodedata.name(last,'')))
        extend=unicodedata.category(char).startswith('M') or char in '\u200d\u200c' or 0x1f3fb<=ord(char)<=0x1f3ff
        if result and (extend or previous.endswith('\u200d') or linker):
            result[-1]+=cluster
        else:
            result.append(cluster)
    return result


def _units(text: str) -> list[tuple[str, str]]:
    """Keep whitespace context; never insert synthetic spaces into CJK text."""
    result: list[tuple[str, str]] = []
    prefix = ''
    for item in re.findall(r'\s+|\S+', text, flags=re.UNICODE):
        if item.isspace():
            prefix = '\n' if '\n' in item else ' '
            continue
        cluster = graphemes(item)
        # In no-space orthographies a full chapter cannot be animated as one word.
        no_spaces_script = any('\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' or '\u0e00' <= c <= '\u0e7f'
                               or '\u1780' <= c <= '\u17ff' for c in item)
        if no_spaces_script or len(cluster) > 40:
            for index, char in enumerate(cluster):
                result.append((char, prefix if index == 0 else ''))
        else:
            result.append((item, prefix))
        prefix = ''
    return result


def _weight(word: str) -> float:
    return max(.7, min(25.0, math.sqrt(max(1, len(graphemes(word)))) * 1.5))


def estimate_timing(text: str, duration: float, offset: float = 0.0) -> list[TimedToken]:
    units = _units(text)
    if not units:
        return []
    weights = [_weight(word) for word, _ in units]
    total = sum(weights)
    cursor = offset
    result = []
    for index, ((word, prefix), weight) in enumerate(zip(units, weights)):
        end = offset + duration if index == len(units) - 1 else cursor + duration * weight / total
        result.append(TimedToken(word, prefix, cursor, end))
        cursor = end
    return result


def _time(value: str) -> float:
    parts = value.strip().replace(',', '.').split(':')
    if len(parts) == 2:
        parts.insert(0, '0')
    if len(parts) != 3:
        raise ValueError('Timestamp must be HH:MM:SS.mmm')
    return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])


def load_cues(path: str | Path, duration: float) -> list[CaptionCue]:
    """Import word/phrase-aligned JSON, standard SRT or WebVTT.

    JSON accepts [{'start':0,'end':0.3,'text':'Hello'}] or {'segments':[...]}.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'Timing file not found: {path}')
    if path.suffix.lower() == '.json':
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(raw, dict):
            raw = raw.get('words', raw.get('segments', raw.get('cues', [])))
        if not isinstance(raw, list):
            raise ValueError('Timing JSON must contain a list of word/phrase timestamps')
        cues = [CaptionCue(float(v['start']), float(v['end']), str(v['text'])) for v in raw]
    elif path.suffix.lower() in ('.srt', '.vtt'):
        source = path.read_text(encoding='utf-8-sig')
        source = re.sub(r'\r\n?', '\n', source)
        cues = []
        for block in re.split(r'\n\s*\n', source):
            lines = block.strip().splitlines()
            for index, line in enumerate(lines):
                if '-->' not in line:
                    continue
                left, right = line.split('-->', 1)
                start, end = _time(left), _time(right.strip().split()[0])
                caption = '\n'.join(lines[index+1:]).strip()
                from html import unescape
                caption = unescape(re.sub(r'<[^>]*>', '', caption))
                if caption:
                    cues.append(CaptionCue(start, end, caption))
                break
    else:
        raise ValueError('Timing file must be JSON, SRT or WebVTT')
    if not cues:
        raise ValueError('The timing file has no readable cues')
    previous = -1.0
    for cue in cues:
        if not (math.isfinite(cue.start) and math.isfinite(cue.end)) or cue.start < previous or cue.end <= cue.start or cue.start < 0 or cue.end > duration + .25:
            raise ValueError('Cue timestamps must be chronological, positive and inside the audio duration')
        previous = cue.start
    return cues


def timed_text(text: str, duration: float, timing_file: str = '') -> list[TimedToken]:
    if timing_file:
        return [token for cue in load_cues(timing_file, duration)
                for token in estimate_timing(cue.text, cue.end - cue.start, cue.start)]
    return estimate_timing(visible_book_text(text), duration)


def _direction(text: str) -> str:
    for char in text:
        bid = unicodedata.bidirectional(char)
        if bid in ('R', 'AL'):
            return 'rtl'
        if bid == 'L':
            return 'ltr'
    return 'ltr'


@lru_cache(maxsize=1)
def _font_candidates() -> tuple[Path, ...]:
    import sys
    import glob
    from shutil import which
    # Bundled OFL Noto fonts work even when the Windows machine has no fonts
    # for Bengali or other complex scripts installed. PyInstaller includes
    # these through openvoice package data.
    resource_fonts = Path(__file__).resolve().parent / 'resources' / 'fonts'
    candidates = sorted(resource_fonts.glob('*.ttf')) if resource_fonts.is_dir() else []
    if which('fc-list'):
        try:
            listing = subprocess.run(['fc-list', '-f', '%{file}\n'], capture_output=True, text=True, timeout=6, check=False)
            candidates.extend(Path(line) for line in listing.stdout.splitlines() if line.lower().endswith(('.ttf', '.otf', '.ttc')))
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not which('fc-list') or len(candidates) < 3:
        directories = ([Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'] if os.name == 'nt'
                       else [Path('/usr/share/fonts'), Path.home()/'.local/share/fonts', Path('/Library/Fonts'), Path('/System/Library/Fonts')])
        for folder in directories:
            if folder.is_dir():
                candidates.extend(Path(file) for ext in ('ttf','otf','ttc') for file in glob.glob(str(folder/'**'/f'*.{ext}'), recursive=True))
    # Prefer wide-coverage Noto and hand-drawn fonts where installed.
    def rank(path):
        s = path.name.lower()
        return (0 if 'noto' in s else 1 if 'free' in s or 'unifont' in s else 2,
                0 if 'regular' in s else 1, s)
    return tuple(sorted(set(candidates), key=rank))


@lru_cache(maxsize=512)
def _coverage(path: str) -> frozenset[int]:
    try:
        from fontTools.ttLib import TTFont
        font=TTFont(path,lazy=True,fontNumber=0)
        data=frozenset((font.getBestCmap() or {}).keys())
        font.close()
        return data
    except (ImportError,OSError,ValueError,KeyError):
        return frozenset()


class ScriptFont:
    """Font fallback by grapheme cluster, preserving shaping within each script run.

    Complex intra-run glyph shaping is delegated to Pillow/RAQM. Cross-script BiDi
    punctuation order may require manual editing for unusually mixed-direction lines.
    """
    def __init__(self, primary, candidates: tuple[Path,...], size: int):
        self.primary=primary
        self.candidates=candidates
        self.size=size
        self._font_cache={str(primary.path):primary}
        self._cluster_cache={}

    def _for(self, cluster):
        needed=frozenset(ord(c) for c in cluster if unicodedata.category(c) != 'Cf')
        if not needed:return self.primary
        if needed in self._cluster_cache:return self._cluster_cache[needed]
        primary=str(self.primary.path)
        font=self.primary
        if not needed.issubset(_coverage(primary)):
            for path in self.candidates:
                if needed.issubset(_coverage(str(path))):
                    try:
                        font=self._font_cache.get(str(path))
                        if font is None:
                            font=load_font(path,self.size)
                            self._font_cache[str(path)]=font
                        break
                    except (OSError,ValueError):pass
        self._cluster_cache[needed]=font
        return font

    def _runs(self,text):
        runs=[]
        for cluster in graphemes(text):
            font=self._for(cluster)
            if runs and runs[-1][0] is font: runs[-1]=(font,runs[-1][1]+cluster)
            else:runs.append((font,cluster))
        return runs

    def getlength(self,text,direction='ltr'):
        return sum(text_length(font,chunk,_direction(chunk)) for font,chunk in self._runs(text))

    def draw_text(self,drawer,xy,text,fill,direction='ltr'):
        runs=self._runs(text)
        if direction=='rtl':runs=list(reversed(runs))
        cursor=xy[0]
        for font,chunk in runs:
            d=_direction(chunk)
            draw_text(drawer,(cursor,xy[1]),chunk,font,fill,d)
            cursor+=text_length(font,chunk,d)


def _script_hint(text: str) -> str:
    """Choose a script-matched fallback family before attempting mixed runs."""
    scripts = ('BENGALI', 'DEVANAGARI', 'ARABIC', 'TAMIL', 'TELUGU',
               'KANNADA', 'MALAYALAM', 'GUJARATI', 'GURMUKHI', 'SINHALA',
               'THAI', 'LAO', 'KHMER', 'MYANMAR', 'HEBREW', 'GEORGIAN',
               'ARMENIAN', 'ETHIOPIC', 'ORIYA')
    counts = {name: 0 for name in scripts}
    for char in text:
        if char.isspace():
            continue
        name = unicodedata.name(char, '')
        for script in scripts:
            if name.startswith(script + ' '):
                counts[script] += 1
                break
    return max(scripts, key=lambda v: counts[v]) if max(counts.values(), default=0) else ''


def pick_font(text: str, size: int, preferred: str = '', *, handwriting: bool = False,
              calligraphy: bool = False):
    """Choose font with actual Unicode coverage, using bundled OFL script faces.

    A user-selected font is respected, and missing glyphs fall back per script
    run. Handwriting and calligraphy prioritize expressive/serif letterforms,
    rather than pretending that a plain computer face is hand-written.
    """
    hint = _script_hint(text)
    installed = list(_font_candidates())
    def preference(path):
        name=path.stem.casefold()
        script_match = bool(hint and (hint.casefold() in name or
                        (hint == 'BENGALI' and 'atma' in name) or
                        (hint == 'DEVANAGARI' and 'kalam' in name)))
        handwritten = any(word in name for word in
                          ('atma', 'kalam', 'caveat', 'hand', 'script',
                           'cursive', 'chancery', 'brush'))
        serif = 'serif' in name
        if handwriting:
            style = 0 if handwritten else (1 if serif else 2)
        elif calligraphy:
            style = 0 if serif else (1 if handwritten else 2)
        else:
            style = 0 if 'sans' in name else 1
        return (0 if script_match else 1,
                style if handwriting or calligraphy else 0,
                0 if 'regular' in name else 1, name)
    ordered = sorted(installed, key=preference)
    if preferred:
        candidate=Path(preferred).expanduser()
        if not candidate.is_file():
            raise ValueError(f'Video font does not exist: {candidate}')
        ordered.insert(0,candidate)
    needs = frozenset(ord(c) for c in text if not c.isspace()
                      and unicodedata.category(c) != 'Cf')
    if hint and not preferred:
        wanted=frozenset(ord(char) for char in text
                         if unicodedata.name(char,'').startswith(hint+' '))
        for candidate in ordered:
            name=candidate.stem.casefold()
            family=(hint.casefold() in name or
                    (hint=='BENGALI' and 'atma' in name) or
                    (hint=='DEVANAGARI' and 'kalam' in name))
            if not family or not wanted.issubset(_coverage(str(candidate))):
                continue
            try:
                selected=load_font(candidate,size)
                return (selected if needs.issubset(_coverage(str(candidate))) else
                        ScriptFont(selected,tuple(ordered),size))
            except (OSError, ValueError):
                continue
    default = None
    for candidate in ordered:
        if not candidate.is_file():
            continue
        try:
            supported=_coverage(str(candidate))
            # With fontTools installed we can reliably reject missing glyphs;
            # otherwise let Pillow try but do not claim universal coverage.
            if needs and supported and not needs.issubset(supported):
                if default is None:
                    default = candidate
                continue
            face=load_font(candidate,size)
            if needs and not supported:
                # No cmap analyzer: keep the face as a last-resort fallback.
                if default is None:
                    default = candidate
                continue
            return face
        except (OSError,ValueError,ImportError,KeyError):
            continue
    if default is None:
        raise RuntimeError('No usable fonts found. Install Noto fonts or select a font.')
    try:
        primary=load_font(default,size)
    except (OSError,ValueError) as exc:
        raise RuntimeError(f'Video font could not be loaded: {default}') from exc
    return ScriptFont(primary,tuple(ordered),size)

def _measure(font, text: str, direction: str) -> float:
    return font.getlength(text,direction=direction) if isinstance(font,ScriptFont) else text_length(font,text,direction)


@dataclass
class Page:
    lines: list[str]
    starts: list[float]
    ends: list[float]
    progress_weights: list[float]
    word_steps: list[list[tuple[float, float, float, float]]]
    stroke_labels: list[list[str]]
    beginning: float
    ending: float
    direction: str


def paginate(tokens: list[TimedToken], font, max_width: int, max_lines: int, duration: float) -> list[Page]:
    pages: list[Page] = []
    lines, starts, ends, counts, steps, labels = [], [], [], [], [], []
    current = ''
    current_start = current_end = 0.0
    count = 0
    current_steps: list[tuple[float,float,float,float]] = []
    current_labels: list[str] = []

    def flush_line():
        nonlocal current, current_start, current_end, count, current_steps, current_labels
        if current.strip():
            lines.append(current.strip()); starts.append(current_start); ends.append(current_end); counts.append(count); steps.append(current_steps); labels.append(current_labels)
        current = ''; count = 0; current_steps = []; current_labels = []

    def flush_page():
        if lines:
            pages.append(Page(lines[:], starts[:], ends[:], counts[:], steps[:], labels[:], starts[0], ends[-1], _direction(' '.join(lines))))
            lines.clear(); starts.clear(); ends.clear(); counts.clear(); steps.clear(); labels.clear()

    for token in tokens:
        source = token.text
        pieces = [source]
        direction = _direction(source)
        if _measure(font, source, direction) > max_width:
            pieces = graphemes(source)
        for i, part in enumerate(pieces):
            prefix = token.prefix if i == 0 else ''
            if '\n' in prefix and current:
                flush_line()
            separator = ' ' if prefix == ' ' and current else ''
            trial = current + separator + part
            if current and _measure(font, trial, _direction(trial)) > max_width:
                flush_line()
                if len(lines) >= max_lines:
                    flush_page()
                trial = part
            if not current:
                current_start = token.start
            # The graphemes inside a long token share its interval proportionally.
            part_start = token.start + (token.end - token.start) * i / len(pieces)
            part_end = token.start + (token.end - token.start) * (i + 1) / len(pieces)
            current_end = part_end
            # Keep grapheme clusters atomic. Typewriter must never display a
            # half vowel sign, Indic conjunct, emoji-ZWJ sequence, etc.
            # The final ink is always drawn from the COMPLETE shaped line.
            old = current
            current = trial
            additions = graphemes(part)
            head = old + separator
            for cluster_index, cluster in enumerate(additions):
                before = head + ''.join(additions[:cluster_index])
                after = before + cluster
                a = _measure(font,before,_direction(current)) if before else 0.0
                b = _measure(font,after,_direction(current))
                ts = part_start + (part_end-part_start)*cluster_index/len(additions)
                te = part_start + (part_end-part_start)*(cluster_index+1)/len(additions)
                current_steps.append((ts,te,max(0,a),max(0,b)))
                current_labels.append(cluster)
            count += 1
        if len(lines) >= max_lines:
            flush_page()
    flush_line(); flush_page()
    for i, page in enumerate(pages):
        page.ending = pages[i + 1].beginning if i + 1 < len(pages) else duration
    return pages


def _hex(value: str) -> tuple[int, int, int]:
    from PIL import ImageColor
    try:
        return ImageColor.getrgb(value if not re.fullmatch(r'[0-9a-fA-F]{6}', value) else '#'+value)
    except ValueError as exc:
        raise ValueError(f'Invalid color: {value}') from exc


def _cover(path: Path | None, size: tuple[int,int], fit: str, background: tuple[int,int,int]):
    from PIL import Image, ImageOps
    width,height=size
    output=Image.new('RGB',size,background)
    if path is None:
        return output
    with Image.open(path) as source:
        source=ImageOps.exif_transpose(source).convert('RGB')
        if fit=='cover':
            return ImageOps.fit(source,size,method=Image.Resampling.LANCZOS,centering=(.5,.5))
        contained=ImageOps.contain(source,size,method=Image.Resampling.LANCZOS)
        output.paste(contained,((width-contained.width)//2,(height-contained.height)//2))
    return output


class PagePainter:
    def __init__(self, pages: list[Page], size: tuple[int,int], font, *, mode: str, color: str, panel_opacity: int,
                 stroke_library=None, strict_strokes: bool = False, paper_grain: int = 14, brush_dryness: int = 12):
        self.pages=pages
        self.size=size
        self.font=font
        self.mode=mode
        self.ink=_hex(color)
        self.panel_opacity=panel_opacity
        self._cache_index=-1
        self._cached=None
        self.line_height=round(font.size*1.40)
        self.nib_angle=-32
        self.pen_width=0
        self.stroke_library=stroke_library
        self.strict_strokes=strict_strokes
        self.paper_grain=paper_grain
        self.brush_dryness=brush_dryness
        self.pen_tool='auto'
        self.panel_rgb=(0,0,0)
        self.safe_margin=.09

    def _layout(self, page: Page):
        from PIL import Image, ImageDraw
        width,height=self.size
        layer=Image.new('RGBA',self.size,(0,0,0,0))
        painter=ImageDraw.Draw(layer)
        # Leave enough cover visible above/below the readable text panel.
        total=len(page.lines)*self.line_height
        top=max(12,(height-total)//2)
        ink_layer=Image.new('RGBA',self.size,(0,0,0,0))
        draw=ImageDraw.Draw(ink_layer)
        boxes=[]
        strokes=[]
        for idx,line in enumerate(page.lines):
            direction = _direction(line)
            x=(width-round(_measure(self.font,line,direction)))//2
            y=top+idx*self.line_height
            if self.mode in ('handwriting','calligraphy'):
                import zlib
                amplitude=min(3,max(1,round(self.font.size*.045)))
                seed=zlib.crc32(line.encode('utf-8'))
                y+=seed%(2*amplitude+1)-amplitude
            if isinstance(self.font,ScriptFont):
                self.font.draw_text(draw,(x,y),line,fill=(*self.ink,255),direction=direction)
            else:
                draw_text(draw,(x,y),line,self.font,(*self.ink,255),direction)
            boxes.append((x,y,max(1,round(_measure(self.font,line,direction))),direction))
            if self.mode in ('typewriter','handwriting','calligraphy'):
                from .ink_engine import prepare_line, stylize_step
                pen_mode=self.mode in ('handwriting','calligraphy')
                line_steps=prepare_line(ink_layer,x,y,boxes[-1][2],self.line_height,
                                        direction,page.word_steps[idx],trace=pen_mode,
                                        clusters=page.stroke_labels[idx],library=self.stroke_library,
                                        strict=self.strict_strokes if pen_mode else False)
                if pen_mode:
                    for step in line_steps:
                        stylize_step(step,calligraphy=self.mode=='calligraphy',
                                     font_size=self.font.size,color=self.ink,
                                     nib_angle=self.nib_angle,pen_width=self.pen_width,
                                     paper_grain=self.paper_grain,brush_dryness=self.brush_dryness,pen_tool=self.pen_tool)
                strokes.append(line_steps)
        pad=max(12,round(font_size_from_font(self.font)*.32))
        upper=max(0,top-pad)
        lower=min(height, top+total+pad)
        painter.rounded_rectangle((max(0,width*.055),upper,min(width,width*.945),lower),radius=min(25,pad),fill=(*self.panel_rgb,self.panel_opacity))
        return layer,ink_layer,boxes,strokes

    def render(self, image, timestamp: float):
        from PIL import Image, ImageDraw
        if not self.pages:
            return image
        starts=[p.beginning for p in self.pages]
        index=max(0,min(len(self.pages)-1,bisect.bisect_right(starts,timestamp)-1))
        page=self.pages[index]
        if self._cache_index!=index:
            self._cached=self._layout(page)
            self._cache_index=index
        panel, ink, boxes, strokes = self._cached
        canvas=image.convert('RGBA')
        from .compute import composite
        composite(canvas,panel)
        mode=self.mode
        elapsed=max(0,timestamp-page.beginning)
        length=max(.001,page.ending-page.beginning)
        phase=max(0,min(1,elapsed/length))
        if mode in ('none','static'):
            composite(canvas,ink)
        elif mode in ('typewriter','handwriting','calligraphy','karaoke'):
            overlay=Image.new('RGBA',self.size,(0,0,0,0))
            cursor=None
            if mode in ('handwriting','calligraphy'):
                # The distinct OpenMukti pen engine traces each pre-shaped
                # grapheme at its own timestamp; no rectangular text wipe.
                from .ink_engine import draw_step
                for line_steps in strokes:
                    for step in line_steps:
                        if timestamp >= step.end:
                            overlay.alpha_composite(step.source,(step.left,step.top))
                        elif timestamp > step.start:
                            frac=(timestamp-step.start)/max(1e-6,step.end-step.start)
                            fragment,tip=draw_step(step,frac,
                                                   calligraphy=(mode=='calligraphy'),
                                                   font_size=self.font.size,
                                                   nib_angle=self.nib_angle,
                                                   pen_width=self.pen_width,
                                                   paper_grain=self.paper_grain,brush_dryness=self.brush_dryness,pen_tool=self.pen_tool)
                            if fragment is not None:
                                overlay.alpha_composite(fragment,(step.left,step.top))
                            if tip is not None:cursor=tip
                composite(canvas,overlay)
                if cursor:
                    # Visible pen nib at the current stroke tip.
                    d=ImageDraw.Draw(canvas)
                    px,py=cursor
                    radius=max(2,round(self.font.size*.045))
                    if mode=='calligraphy':
                        d.line((px-radius*2,py+radius,px+radius*2,py-radius),
                               fill=(*self.ink,235),width=max(2,radius))
                    else:
                        d.ellipse((px-radius,py-radius,px+radius,py+radius),
                                  fill=(*self.ink,225))
            elif mode=='karaoke':
                composite(canvas,ink)
                marking=ImageDraw.Draw(canvas)
                for idx,(x,y,w,direction) in enumerate(boxes):
                    if not page.starts[idx] <= timestamp < page.ends[idx]:
                        continue
                    steps=page.word_steps[idx]
                    a=b=0.0
                    for ts,te,left,right in steps:
                        if ts<=timestamp<te:
                            a,b=left,right
                            break
                    total=max(.001,steps[-1][3]) if steps else 1
                    if direction=='rtl':
                        rightedge=x+w-round(w*a/total)
                        leftedge=x+w-round(w*b/total)
                    else:
                        leftedge=x+round(w*a/total)
                        rightedge=x+round(w*b/total)
                    if rightedge>leftedge:
                        marking.rounded_rectangle((leftedge,y+self.line_height-5,
                                                  rightedge,y+self.line_height-1),
                                                  radius=2,fill=(255,190,70,255))
            else:
                # Reveal one completely shaped grapheme section at once.
                # No intermediate partial rectangular wipe through a matra,
                # Indic conjunct, Arabic join or emoji ZWJ sequence.
                for line_steps in strokes:
                    for step in line_steps:
                        if timestamp < step.start + .60*(step.end-step.start):
                            if step.start <= timestamp < step.end:
                                cursor=(step.left,step.top)
                            continue
                        overlay.alpha_composite(step.source,(step.left,step.top))
                composite(canvas,overlay)
                if cursor:
                    d=ImageDraw.Draw(canvas)
                    d.line((cursor[0],cursor[1],cursor[0],cursor[1]+self.font.size),
                           fill=(*self.ink,255),width=2)
        elif mode.startswith('scroll-') or mode.startswith('slide-'):
            # Scroll progresses over the entire page; slide enters from the edge.
            width,height=self.size
            progress = phase if mode.startswith('scroll-') else max(0,1-min(1,elapsed/max(.35,length*.20)))
            if mode.startswith('scroll-'):
                offset=round((progress-.5)*.65*(height if mode.endswith(('up','down')) else width))
                if mode.endswith(('up','left')): offset=-offset
            else:
                offset=round(progress*(height if mode.endswith(('up','down')) else width))
                if mode.endswith(('up','left')): offset=-offset
            shift=(0,offset) if mode.endswith(('up','down')) else (offset,0)
            moving=Image.new('RGBA',self.size,(0,0,0,0))
            moving.paste(ink,shift)
            composite(canvas,moving)
        elif mode=='fade':
            duplicate=ink.copy(); duplicate.putalpha(ink.getchannel('A').point(lambda v:round(v*min(1,elapsed/max(.3,length*.18)))))
            composite(canvas,duplicate)
        elif mode=='zoom':
            from PIL import Image
            scale=.70+.30*min(1,elapsed/max(.35,length*.22))
            resized=ink.resize((max(2,int(self.size[0]*scale)),max(2,int(self.size[1]*scale))),Image.Resampling.BICUBIC)
            tmp=Image.new('RGBA',self.size,(0,0,0,0))
            tmp.paste(resized,((self.size[0]-resized.width)//2,(self.size[1]-resized.height)//2))
            composite(canvas,tmp)
        return canvas.convert('RGB')


def font_size_from_font(font) -> int:
    return getattr(font,'size',32)


def render_animated_frames(images: list[Path], audio: Path, destination: Path, text: str, *,
                           video_options, duration: float, size: tuple[int,int], ffmpeg: str,
                           control=None, status: Callable | None = None):
    """Stream RGB frames straight to FFmpeg; memory doesn't grow with book length."""
    from PIL import Image
    board = None
    if video_options.storyboard:
        from .storyboard import Storyboard
        board = Storyboard.load(video_options.storyboard, audio)
    if video_options.animation not in MODES or (video_options.animation == 'none' and not board):
        raise ValueError('Choose an animated text mode or a storyboard')
    width,height=size
    painter = None
    if video_options.animation != 'none':
        if not text.strip() and not video_options.timing_file:
            raise ValueError('Animated videos require book text or a timing file')
        tokens = timed_text(text,duration,video_options.timing_file)
        if not tokens:
            raise ValueError('No words could be found to animate')
        font_size = video_options.font_size or max(14,round(min(width,height)*.065))
        font=pick_font(''.join(token.text for token in tokens)[:20000],font_size,video_options.font_path,
                       handwriting=video_options.animation == 'handwriting',
                       calligraphy=video_options.animation == 'calligraphy')
        if not layout_status()['raqm']:
            # A broken native wheel cannot shape Bengali/Indic/Arabic correctly.
            # Explicitly point the user to the portable build instead of encoding
            # unreadable glyphs; the Windows builder MUST catch this in preflight.
            complex_script=any('\u0590'<=c<='\u08ff' or '\u0900'<=c<='\u109f' or
                               '\u1780'<=c<='\u17ff' or '\ua980'<=c<='\ua9df' for t in tokens for c in t.text)
            if complex_script:
                raise RuntimeError('This installed build lacks the complex-script text renderer '
                                   '(Pillow RAQM/HarfBuzz). Install the repaired Windows standalone build '
                                   'which includes and verifies it; an existing EXE cannot be fixed by '
                                   'installing a font outside the EXE.')
            emit(status,.68,'Using basic Latin text layout; complex scripts unavailable')
        padding=max(12,int(width*video_options.safe_margin))
        max_width=max(30,width-2*padding)
        pages=paginate(tokens,font,max_width,max(1,min(8,int(height*.50/(font_size*1.4)))),duration)
        from .stroke_library import load_stroke_library
        library=load_stroke_library(video_options.stroke_library) if video_options.animation in ('handwriting','calligraphy') else None
        painter=PagePainter(pages,size,font,mode=video_options.animation,color=video_options.text_color,
                            panel_opacity=video_options.panel_opacity,stroke_library=library,
                            strict_strokes=video_options.strict_strokes,
                            paper_grain=video_options.paper_grain,brush_dryness=video_options.brush_dryness)
        if video_options.caption_preset!='custom':
            style={'white on black':((255,255,255),(0,0,0)),'yellow on black':((255,255,0),(0,0,0)),
                   'black on white':((0,0,0),(255,255,255))}[video_options.caption_preset]
            painter.ink,painter.panel_rgb=style
            painter.panel_opacity=255
        painter.safe_margin=video_options.safe_margin
        painter.pen_width=video_options.pen_width
        painter.pen_tool=video_options.pen_tool
        painter.nib_angle=video_options.nib_angle
    from .video import VIDEO_FORMATS
    vcodec,acodec=VIDEO_FORMATS[destination.suffix.lower()]
    count=max(1,math.ceil(duration*video_options.fps))
    base_colors=_hex(video_options.background)
    @lru_cache(maxsize=1)
    def cover_at(index):
        if images:return _cover(images[index],size,video_options.fit,base_colors)
        return Image.new('RGB',size,board.data.get('background',base_colors) if board else base_colors)
    from .video_devices import arguments, encode

    def encode_frames(encoder, device):
        prefix, codec_args = arguments(encoder, video_options.crf, size, video_options.fps, device=device)
        command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *prefix, '-f', 'rawvideo',
                   '-pixel_format', 'rgb24', '-video_size', f'{width}x{height}', '-framerate',
                   str(video_options.fps), '-i', 'pipe:0', '-i', str(audio),
                   '-map', '0:v:0', '-map', '1:a:0', *codec_args, '-c:a', acodec]
        if acodec=='aac': command.extend(['-b:a','160k','-ar','48000','-ac','2'])
        else: command.extend(['-b:a','128k','-ar','48000','-ac','2'])
        if destination.suffix.lower() in ('.mov','.mp4'):
            command.extend(['-movflags','+faststart'])
        command.extend(['-t',f'{duration:.5f}','-shortest',str(destination)])
        destination.parent.mkdir(parents=True,exist_ok=True)
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        import threading
        errors=[]
        def errors_worker():
            if process.stderr:
                errors.append(process.stderr.read()[-3000:])
        watcher=threading.Thread(target=errors_worker,daemon=True); watcher.start()
        try:
            next_emit=-1
            for frame in range(count):
                if control: control.check()
                timestamp=frame/video_options.fps
                picture=cover_at(min(len(images)-1,int(timestamp/duration*len(images))) if images else 0)
                if board:
                    picture = board.paint(picture,timestamp,duration)
                rendered = painter.render(picture,timestamp) if painter else picture
                if board:
                    rendered = board.paint(rendered,timestamp,duration,foreground=True)
                try:
                    process.stdin.write(rendered.tobytes())
                except BrokenPipeError as exc:
                    raise RuntimeError('FFmpeg stopped while receiving animation frames') from exc
                now=frame//max(1,video_options.fps)
                if now>next_emit:
                    next_emit=now
                    emit(status, .70+.28*(frame+1)/count, f'Writing animated video · {frame+1:,} / {count:,} frames', (frame+1)/count)
            process.stdin.close()
            result=process.wait()
            watcher.join(timeout=2)
            if process.stderr:process.stderr.close()
            if result:
                error=(errors[-1] if errors else b'').decode('utf-8','replace')
                raise RuntimeError('FFmpeg animation encoding failed: '+error[-1500:])
        except BaseException:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
            if process.stderr:process.stderr.close()
            raise

    encode(ffmpeg, vcodec, encode_frames, status, control)
