"""FFmpeg-based layered timing mixer for explicitly tagged dialogues.

All commands are argv lists (no shell).  Sound names resolve only against project
imports; scripts cannot read arbitrary local files as sound effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import wave
from .fftools import find_binary
from .timeline_tags import Timeline, TimedPassage, SoundCue, MAX_MS


@dataclass
class Clip:
    source: Path
    start_ms: int
    length_ms: int | None = None
    speed: float = 1.0
    loop: bool = False
    gain: float = 1.0


def duration_ms(path: Path) -> int:
    try:
        with wave.open(str(path), 'rb') as wav:
            return round(wav.getnframes() * 1000 / wav.getframerate())
    except (wave.Error, EOFError, ValueError):
        ffprobe = find_binary('ffprobe')
        if not ffprobe:
            raise RuntimeError('FFprobe is needed to read this audio format')
        result = subprocess.run([ffprobe, '-v', 'error', '-show_entries',
                                 'format=duration', '-of', 'default=nw=1:nk=1', str(path)],
                                capture_output=True, text=True, timeout=30, check=True)
        return round(float(result.stdout.strip()) * 1000)


def resolve_sfx(name: str, imports: list[str]) -> Path:
    name = name.strip()
    # Explicitly imported files only. Filenames must be unique (case-insensitive).
    options = [Path(value).expanduser().resolve() for value in imports]
    matches = [p for p in options if p.name.casefold() == name.casefold()]
    if not matches:
        raise FileNotFoundError(f'Sound {name!r} is not imported. Use Voices → Import sound effects first.')
    if len(matches) > 1:
        raise ValueError(f'Ambiguous imported sound name: {name}')
    if not matches[0].is_file():
        raise FileNotFoundError(f'Imported sound no longer exists: {matches[0]}')
    return matches[0]


def plan_timeline(timeline: Timeline, speech_wavs: list[Path], imports: list[str],
                  *, default_pause_ms: int = 0) -> tuple[list[Clip], int]:
    if len(speech_wavs) != len(timeline.passages):
        raise ValueError('A voice clip is required for each timed passage')
    clips: list[Clip] = []
    clock = 0
    previous_start = 0
    previous_voice: Clip | None = None
    for passage, wav in zip(timeline.passages, speech_wavs):
        native = duration_ms(wav)
        if not native:
            raise ValueError('Synthesis created an empty audio clip')
        target = passage.duration_ms if passage.duration_ms is not None else native
        if target <= 0:
            raise ValueError('Speech duration must be positive')
        speed = native / target
        if not 0.1 <= speed <= 10:
            raise ValueError('Requested speaking duration would require extreme speed changes (0.1x to 10x supported)')
        pause_base = clock
        start = clock + passage.pause_ms
        if passage.overlap_ms:
            start = max(0, clock - passage.overlap_ms + passage.pause_ms)
        if passage.interrupt_ms is not None and previous_voice is not None:
            start = previous_start + passage.interrupt_ms + passage.pause_ms
            previous_voice.length_ms = max(0, start - previous_start)
        current = Clip(wav, start, target, speed)
        if current.length_ms:
            clips.append(current)
        for cue in passage.cues:
            anchor = pause_base if cue.anchor == 'pause' else start
            length = cue.length_ms
            # Unbounded one-shot effects stay inside their requested slot.
            if length is None:
                length = max(0, (passage.pause_ms if cue.anchor == 'pause' else target) - cue.start_ms)
            cue_start = anchor + cue.start_ms
            if cue.anchor == 'pause' and cue_start + (length or 0) > start:
                raise ValueError(f'Sound {cue.name!r} extends beyond the indicated pause')
            if cue.anchor == 'speech' and cue_start + (length or 0) > start + target:
                raise ValueError(f'Sound {cue.name!r} extends beyond the indicated speech')
            clips.append(Clip(resolve_sfx(cue.name, imports), cue_start, length))
        previous_voice = current
        previous_start = start
        clock = max(clock, start + target) if passage.overlap_ms else start + target
        if passage is not timeline.passages[-1]:
            clock += default_pause_ms
    clock += timeline.trailing_pause_ms
    for cue in timeline.sounds:
        if cue.anchor == 'background':
            clips.append(Clip(resolve_sfx(cue.name, imports), cue.start_ms,
                              cue.length_ms or clock, loop=cue.loop, gain=0.22))
        else:
            clips.append(Clip(resolve_sfx(cue.name, imports), cue.start_ms, cue.length_ms))
    if clock > MAX_MS:
        raise ValueError('Timed narration exceeds the 24-hour render limit')
    return clips, clock


def mix_timeline(clips: list[Clip], destination: Path, end_ms: int, control=None) -> Path:
    ffmpeg = find_binary('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required for timed pauses, sound effects, overlaps, and interruptions.')
    if not clips:
        raise ValueError('No audio clips were prepared')
    if len(clips) > 256:
        raise ValueError('This render has more than 256 overlapping/timed clips; split the chapter into sections')
    args = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error']
    filters = []
    for i, clip in enumerate(clips):
        if clip.loop:
            args += ['-stream_loop', '-1', '-t', f'{max(1, end_ms - clip.start_ms) / 1000:.3f}']
        args += ['-i', str(clip.source)]
        stages = []
        stages.append('asetpts=PTS-STARTPTS')
        speed = clip.speed
        if speed != 1:
            # atempo 0.5..2 chained, preserving speech duration in wall time.
            while speed > 2:
                stages.append('atempo=2')
                speed /= 2
            while speed < 0.5:
                stages.append('atempo=0.5')
                speed *= 2
            if abs(speed - 1) > 0.0001:
                stages.append(f'atempo={speed:.8f}')
        if clip.length_ms is not None:
            stages.extend(['apad', f'atrim=duration={clip.length_ms / 1000:.6f}'])
        stages.extend(['aresample=48000', 'aformat=sample_fmts=fltp:channel_layouts=stereo'])
        if clip.gain != 1:
            stages.append(f'volume={clip.gain:.4f}')
        stages.append(f'adelay={max(0, clip.start_ms)}:all=1')
        filters.append(f'[{i}:a]' + ','.join(stages) + f'[c{i}]')
    filters.append(''.join(f'[c{i}]' for i in range(len(clips))) +
                   f'amix=inputs={len(clips)}:duration=longest:dropout_transition=0:normalize=0,'
                   f'alimiter=limit=0.95,apad,atrim=duration={end_ms / 1000:.6f}[out]')
    destination.parent.mkdir(parents=True, exist_ok=True)
    args += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(destination)]
    if control:
        control.check()
    try:
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError('FFmpeg timeline mixing failed: ' + exc.stderr.decode('utf-8', errors='replace')[-2500:]) from exc
    if control:
        control.check()
    return destination
