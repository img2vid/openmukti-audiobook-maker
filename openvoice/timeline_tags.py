"""Safe, deterministic bracket-tag timeline grammar for layered spoken audio.

Times are stored as milliseconds, never evaluated as Python expressions.  The
parser does not access the filesystem; sound assets are resolved separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re

MAX_MS = 24 * 60 * 60 * 1000
NUMBER = r'(?:\d+(?:\.\d+)?|\.\d+)'
TIME = re.compile(rf'^\s*({NUMBER})\s*(milliseconds?|msecs?|msec|ms|seconds?|secs?|sec|s|minutes?|mins?|min|m|hours?|hrs?|hr|h)\s*$', re.I)
WORDS = {'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10', 'half': '0.5', 'quarter': '0.25'}
UNITS = {'ms': 1, 'msec': 1, 'msecs': 1, 'millisecond': 1, 'milliseconds': 1,
         's': 1000, 'sec': 1000, 'secs': 1000, 'second': 1000, 'seconds': 1000,
         'm': 60000, 'min': 60000, 'mins': 60000, 'minute': 60000, 'minutes': 60000,
         'h': 3600000, 'hr': 3600000, 'hrs': 3600000, 'hour': 3600000, 'hours': 3600000}
TAG = re.compile(r'\[([^\[\]\n]{1,600})\]')
SFX = re.compile(r'^(?:(?:sfx|sound(?: effect)?|audio|play)\s*[:=]?\s*)([^()]+?)(?:\s*\(([^()]*)\))?$', re.I)
RANGE = re.compile(r'^\s*(.*?)\s*(?:-|–|—|\bto\b|\.\.)\s*(.*?)\s*$', re.I)

@dataclass(frozen=True)
class SoundCue:
    name: str
    start_ms: int = 0
    length_ms: int | None = None
    anchor: str = 'speech'  # pause, speech, absolute, background
    loop: bool = False

@dataclass
class TimedPassage:
    speaker: str
    text: str
    pause_ms: int = 0
    duration_ms: int | None = None
    cues: list[SoundCue] = field(default_factory=list)
    overlap_ms: int = 0
    interrupt_ms: int | None = None

@dataclass
class Timeline:
    passages: list[TimedPassage] = field(default_factory=list)
    sounds: list[SoundCue] = field(default_factory=list)
    trailing_pause_ms: int = 0


def parse_duration(value: str) -> int:
    """Supports 500ms, 0.5 sec, two seconds, 1m 30s, 01:02:03.25, etc."""
    raw = value.strip().lower().replace('_', ' ')
    raw = re.sub(r'\b([a-z]+|\d+)\s+and\s+a\s+(half|quarter)\b',
                 lambda m: m.group(1) + ' plus ' + m.group(2), raw)
    raw = re.sub(r'\b([a-z]+|\d+)\s+plus\s+(half|quarter)\s+([a-z]+)',
                 lambda m: str(Decimal(WORDS.get(m.group(1), m.group(1))) + Decimal(WORDS[m.group(2)])) + ' ' + m.group(3)
                 if m.group(1) in WORDS or m.group(1).isdigit() else m.group(0), raw)
    for word, number in WORDS.items():
        raw = re.sub(r'\b' + word + r'\b', number, raw)
    raw = re.sub(r'\b(?:and|of|a|an)\b', ' ', raw)
    if ':' in raw:
        pieces = raw.split(':')
        if len(pieces) not in (2, 3) or any(not re.fullmatch(NUMBER, x.strip()) for x in pieces):
            raise ValueError('Invalid clock duration: ' + value)
        numbers = [Decimal(x) for x in pieces]
        if any(x >= 60 for x in numbers[1:]):
            raise ValueError('Clock duration must use seconds/minutes below 60')
        total = sum(x * 60 ** (len(numbers) - i - 1) for i, x in enumerate(numbers)) * 1000
    else:
        parts = list(re.finditer(rf'({NUMBER})\s*([a-z]+)', raw))
        if not parts or re.sub(r'\s+', '', re.sub(rf'{NUMBER}\s*[a-z]+', '', raw)):
            raise ValueError('Invalid duration: ' + value)
        try:
            total = sum(Decimal(p.group(1)) * UNITS[p.group(2)] for p in parts)
        except KeyError as exc:
            raise ValueError('Unknown duration unit in: ' + value) from exc
    if total < 0 or total > MAX_MS:
        raise ValueError('Duration must be between 0 and 24 hours')
    return int(total.to_integral_value(rounding='ROUND_HALF_UP'))


def _time_or_none(value: str) -> int | None:
    try:
        return parse_duration(value)
    except ValueError:
        return None


def _split_fields(tag: str) -> list[str]:
    # Commas inside SFX parentheses are not field separators.
    return [x.strip() for x in re.split(r',\s*(?![^()]*\))|\s*;\s*(?![^()]*\))', tag) if x.strip()]


def _cue(field: str, anchor: str) -> SoundCue | None:
    found = SFX.match(field)
    if not found:
        return None
    name = found.group(1).strip().strip('"\'')
    if not name or len(name) > 240:
        raise ValueError('Invalid sound effect name')
    start, length = 0, None
    if found.group(2):
        span = RANGE.match(found.group(2))
        if span:
            start = parse_duration(span.group(1))
            end = parse_duration(span.group(2))
            if end <= start:
                raise ValueError('Sound effect end must exceed its start')
            length = end - start
        else:
            start = parse_duration(found.group(2))
    return SoundCue(name, start, length, anchor)


def parse_timeline(text: str, speakers: list[str] | tuple[str, ...]) -> Timeline:
    """Unknown bracket contents are preserved as spoken text, not discarded."""
    names = {name.casefold(): name for name in speakers}
    if 'narrator' not in names:
        names['narrator'] = 'Narrator'
    speaker = names['narrator']
    timeline = Timeline()
    pending = TimedPassage(speaker, '')

    def flush():
        nonlocal pending
        if pending.text.strip():
            pending.text = pending.text.strip()
            timeline.passages.append(pending)
            pending = TimedPassage(speaker, '')

    def attribute(field: str) -> bool:
        nonlocal speaker
        name = re.sub(r'^(?:speaker\s*[:=]\s*|character\s*[:=]\s*|spoken by\s+|narrated by\s+|(?:let|have)\s+)', '', field, flags=re.I)
        name = re.sub(r'\s+(?:speaks?|says?|is speaking|talks?|talking|narrates?|speaking|say this|read this)$', '', name, flags=re.I)
        resolved = names.get(name.strip().casefold())
        if resolved:
            flush()
            speaker = resolved
            pending.speaker = resolved
            return True
        return False

    def token(field: str, *, bare_is_duration: bool = False) -> bool:
        nonlocal pending
        f = field.strip()
        if attribute(f):
            return True
        # IPA in square brackets is translated into the application's native syntax.
        ipa = re.match(r'^(?:ipa|phonemes?|pronounce (?:as|using ipa))\s*[:=]?\s*(.+)$', f, re.I)
        if ipa:
            pending.text += '<ipa:' + ipa.group(1).strip() + '>'
            return True
        pauses = re.match(r'^(?:remain silent for|be silent for|wait for|pause for|pause|p|wait|silence|delay)\s*(?:[:=]|\s+)?\s*(.*?)\s*$', f, re.I)
        if pauses and pauses.group(1):
            amount = _time_or_none(pauses.group(1))
            if amount is not None:
                pending.pause_ms += amount
                return True
        dur = re.match(r'^(?:speech duration|speaking duration|say this in|duration|speak for|say in|take|last|fit to|length)\s*(?:[:=]|\s+)?\s*(.*?)$', f, re.I)
        if dur:
            amount = _time_or_none(dur.group(1))
            if amount is not None:
                pending.duration_ms = amount
                return True
        overlap = re.match(r'^(?:overlap|talk over|speak over|start before previous ends|simultaneous(?:ly)?)\s*(?:[:=]|\s+)?\s*(.*)$', f, re.I)
        if overlap:
            pending.overlap_ms = _time_or_none(overlap.group(1)) or 0
            return True
        interrupt = re.match(r'^(?:interrupt|cut off|stop previous|interruption)\s*(?:after|at|[:=])?\s*(.*)$', f, re.I)
        if interrupt:
            pending.interrupt_ms = _time_or_none(interrupt.group(1)) or 0
            return True
        background = re.match(r'^(?:background|ambient|ambience|loop)\s*(?:sound|audio|sfx)?\s*[:=]\s*(.+)$', f, re.I)
        if background:
            cue = SoundCue(background.group(1).strip().strip('"\''), 0, None, 'background', True)
            timeline.sounds.append(cue)
            return True
        cue = _cue(f, 'pause' if pending.duration_ms is None and pending.pause_ms else 'speech')
        if cue:
            pending.cues.append(cue)
            return True
        amount = _time_or_none(f)
        if amount is not None:
            if bare_is_duration:
                pending.duration_ms = amount
            elif pending.pause_ms == 0 and pending.duration_ms is None:
                pending.pause_ms = amount
            else:
                pending.duration_ms = amount
            return True
        return False

    pos = 0
    for match in TAG.finditer(text):
        before = text[pos:match.start()]
        if before.strip():
            pending.text += before
            flush()
        fields = _split_fields(match.group(1))
        # Prevent partially interpreting a completely unknown tag.
        if not fields or not any(token(x) for x in fields[:1]):
            pending.text += match.group(0)
        else:
            bare_fields = [x for x in fields[1:] if _time_or_none(x) is not None]
            speaker_first = fields[0].strip().casefold() in {k.casefold() for k in speakers}
            # [Mary, 3s] means speech duration; [Mary, 500ms, 3s]
            # means initial silence followed by a timed utterance.
            for extra in fields[1:]:
                as_duration = (speaker_first and len(bare_fields) == 1 and
                               _time_or_none(extra) is not None and
                               not any(re.match(r'^(?:pause|p|wait|delay)\b', other, re.I)
                                       for other in fields[1:]))
                if not token(extra, bare_is_duration=as_duration):
                    raise ValueError('Unknown audio tag field: ' + extra)
        pos = match.end()
    pending.text += text[pos:]
    flush()
    if pending.pause_ms and not pending.text:
        timeline.trailing_pause_ms = pending.pause_ms
    return timeline


def has_timeline_tags(text: str) -> bool:
    for match in TAG.finditer(text):
        fields = _split_fields(match.group(1))
        for field in fields:
            if (_time_or_none(field) is not None or
                re.match(r'^(?:pause|p|wait|silence|delay|duration|speech duration|speak for|overlap|talk over|interrupt|cut off|sfx|sound|audio|play|background|ambient|ambience|loop|ipa|phoneme)\b', field, re.I)):
                return True
    return False
