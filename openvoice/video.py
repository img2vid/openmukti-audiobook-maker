from __future__ import annotations
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .fftools import find_binary
from .engines import RunControl, SpeechEngine, SpeechSettings
from .ipa_pronunciation import display_inline_ipa
from .service import JobOptions, render_text
from .progress import emit, subprogress, run_ffmpeg

ASPECTS = {'16:9': (16, 9), '9:16': (9, 16), '1:1': (1, 1), '4:3': (4, 3), '3:4': (3, 4), '3:2': (3, 2), '2:3': (2, 3), '21:9': (21, 9), '9:21': (9, 21), '5:4': (5, 4), '4:5': (4, 5)}
HEIGHTS = {'360p': 360, '480p': 480, '720p': 720, '1080p': 1080, '1440p': 1440, '2160p': 2160}
VIDEO_FORMATS = {'.mp4': ('libx264', 'aac'), '.mkv': ('libx264', 'aac'), '.mov': ('libx264', 'aac'), '.webm': ('libvpx-vp9', 'libopus')}
IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tif', '.tiff'}

@dataclass(frozen=True)
class VideoOptions:
    aspect: str = '16:9'
    resolution: str = '720p'
    fps: int = 30
    fit: str = 'contain'
    background: str = 'black'
    captions: bool = False
    crf: int = 23
    animation: str = 'none'  # Classic cover slideshow by default
    timing_file: str = ''  # Optional JSON/SRT/VTT alignment for accurate sync
    font_path: str = ''  # Optional .ttf/.otf supporting the requested script
    font_size: int = 0  # 0 automatically fits the output resolution
    text_color: str = 'FFFFFF'
    panel_opacity: int = 165
    dimensions: str = ''  # Exact custom width x height, e.g. 2560x1080
    pen_width: int = 0  # 0 = stroke-width chosen from text size
    nib_angle: int = -32  # Calligraphy broad-edge nib angle, degrees
    stroke_library: str = ''  # Optional genuine hand-drawn Unicode path pack
    strict_strokes: bool = False  # Fail instead of automatic font-guided reconstruction
    paper_grain: int = 14  # 0..80, procedural paper texture
    brush_dryness: int = 12  # 0..80, dry brush pigment gaps
    pen_tool: str = 'auto'  # auto/pencil/ballpoint/fountain/brush/broad-nib
    storyboard: str = ''  # Local layered artwork and timed video design
    caption_preset: str = 'custom'
    safe_margin: float = .09


def video_size(aspect: str, resolution: str, dimensions: str = '') -> tuple[int, int]:
    if dimensions.strip():
        match = re.fullmatch(r'\s*(\d{2,5})\s*[xX×]\s*(\d{2,5})\s*', dimensions)
        if not match:
            raise ValueError('Custom dimensions must look like 1920x1080')
        width, height = map(int, match.groups())
        if width > 7680 or height > 7680 or width < 16 or height < 16 or width % 2 or height % 2:
            raise ValueError('Custom dimensions must be even numbers between 16 and 7680 pixels')
        return width, height
    if aspect not in ASPECTS:
        match = re.fullmatch(r'([1-9]\d{0,3}):([1-9]\d{0,3})', aspect)
        if not match:
            raise ValueError('Aspect must be a preset or a custom ratio such as 17:10')
        a, b = map(int, match.groups())
    else:
        a, b = ASPECTS[aspect]
    if resolution not in HEIGHTS:
        raise ValueError('Resolution must be: ' + ', '.join(HEIGHTS))
    height = HEIGHTS[resolution]
    width = round(height * a / b / 2) * 2
    if width < 16 or width > 7680:
        raise ValueError('Aspect ratio produces an unusably narrow or oversized output. Choose custom dimensions.')
    return width, height


def binary(name: str) -> str:
    return find_binary(name)


def _run(command: list[str], control: RunControl | None = None, *, progress=None, duration=None) -> None:
    if progress is not None:
        return run_ffmpeg(command, control=control, progress=progress, duration=duration)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    try:
        while True:
            try:
                _, errors = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if control is not None:
                    control.check()
        if process.returncode:
            raise RuntimeError('FFmpeg error: ' + errors[-1600:].strip())
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        raise


def audio_duration(audio: str | Path) -> float:
    probe = binary('ffprobe')
    if not probe:
        raise RuntimeError('FFprobe is required for audiobook videos. Install FFmpeg and FFprobe or place both beside the executable.')
    result = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(audio)], text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError('Cannot inspect audio: ' + result.stderr[-500:])
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise ValueError('Audio duration is unavailable') from exc
    if not (0 < seconds < 2592000):
        raise ValueError('Audio duration must be between 0 and 30 days')
    return seconds


def _srt_time(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3600000)
    minutes, ms = divmod(ms, 60000)
    whole, milli = divmod(ms, 1000)
    return f'{hours:02}:{minutes:02}:{whole:02},{milli:03}'


def write_approximate_captions(text: str, seconds: float, destination: str | Path) -> Path:
    words = text.split()
    if not words:
        raise ValueError('Captions need narration text')
    batches = [' '.join(words[index:index + 11]) for index in range(0, len(words), 11)]
    weights = [max(1, len(batch.split())) for batch in batches]
    total = sum(weights)
    output = []
    cursor = 0.0
    for index, (part, weight) in enumerate(zip(batches, weights), 1):
        end = seconds if index == len(batches) else cursor + seconds * weight / total
        output.append(f'{index}\n{_srt_time(cursor)} --> {_srt_time(end)}\n{part}\n')
        cursor = end
    target = Path(destination)
    target.write_text('\n'.join(output), encoding='utf-8')
    return target


def _concat_image_list(images: list[Path], duration: float, target: Path) -> None:
    per_image = duration / len(images)
    lines = ['ffconcat version 1.0']
    for image in images:
        name = image.resolve().as_posix().replace("'", "'\\''")
        lines.extend([f"file '{name}'", f'duration {per_image:.8f}'])
    name = images[-1].resolve().as_posix().replace("'", "'\\''")
    lines.append(f"file '{name}'")
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def render_video(images: list[str | Path], output: str | Path, *, audio: str | Path | None = None, text: str = '', engine: SpeechEngine | None = None, settings: SpeechSettings | None = None, speech_options: JobOptions = JobOptions(), video_options: VideoOptions = VideoOptions(), control: RunControl | None = None, progress: Callable[[int, int], None] | None = None, status=None) -> Path:
    emit(status, 0, 'Preparing audiobook video')
    # Validate the user's inputs before probing external video tools so that
    # a missing FFmpeg installation never masks a more actionable input error.
    if not images and video_options.animation == 'none' and not video_options.storyboard:
        raise ValueError('Choose at least one cover image, or enable animated text mode')
    ffmpeg = binary('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required for audiobook videos. Install it or place FFmpeg beside the executable.')
    picture_paths = [Path(p).expanduser().resolve() for p in images]
    for path in picture_paths:
        if path.suffix.lower() not in IMAGE_FORMATS or not path.is_file():
            raise ValueError(f'Image does not exist or its format is unsupported: {path}')
    target = Path(output).expanduser().resolve()
    if target.suffix.lower() not in VIDEO_FORMATS:
        raise ValueError('Supported video formats: MP4, MKV, MOV, WebM')
    opts = video_options
    width, height = video_size(opts.aspect, opts.resolution, opts.dimensions)
    if opts.fps not in (24, 25, 30, 60):
        raise ValueError('FPS must be 24, 25, 30 or 60')
    if opts.fit not in ('contain', 'cover'):
        raise ValueError('Image fit must be contain or cover')
    if not re.fullmatch(r'(?:[0-9a-fA-F]{6}|black|white|gray|navy)', opts.background):
        raise ValueError('Background must be a six-digit hexadecimal RGB color or black, white, gray, navy')
    if not 0<=opts.safe_margin<=.35 or opts.caption_preset not in ('custom','white on black','yellow on black','black on white'):
        raise ValueError('Invalid subtitle safe margin or color preset')
    if not 0 <= opts.crf <= 45:
        raise ValueError('CRF must be between 0 and 45')
    if not audio and not text.strip():
        raise ValueError('Supply an existing audio file or narration text')
    if opts.captions and not text.strip() and not opts.timing_file:
        raise ValueError('Captions require narration text or a timing file')
    from .animated_video import MODES
    if opts.animation not in MODES:
        raise ValueError('Unsupported animated text style: ' + opts.animation)
    if (not 0 <= opts.panel_opacity <= 255 or not 0 <= opts.font_size <= 250
            or not 0 <= opts.pen_width <= 40 or not -80 <= opts.nib_angle <= 80
            or not 0 <= opts.paper_grain <= 80 or not 0 <= opts.brush_dryness <= 80
            or opts.pen_tool not in ('auto','pencil','ballpoint','fountain','brush','broad-nib')
            or (opts.stroke_library and not Path(opts.stroke_library).is_file())
            or (opts.font_path and not Path(opts.font_path).is_file())):
        raise ValueError('Check font, stroke library, pen settings, paper grain and brush dryness (0-80)')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.openvoice-video-', dir=target.parent) as directory:
        work = Path(directory)
        if audio:
            sound = Path(audio).expanduser().resolve()
            if not sound.is_file():
                raise ValueError(f'Audio file does not exist: {sound}')
        else:
            if engine is None or settings is None:
                raise ValueError('A speech engine and voice settings are needed for text narration')
            sound = work / 'narration.wav'
            render_text(text, sound, engine, settings, speech_options, control=control, progress=progress,
                        status=subprogress(status, 0, .55))
        if control:
            control.check()
        duration = audio_duration(sound)
        if opts.animation != 'none' or opts.storyboard:
            from .animated_video import render_animated_frames, load_cues, timed_text
            emit(status, .60, 'Preparing synchronized text and image cover')
            staged = work / ('output' + target.suffix.lower())
            render_animated_frames(picture_paths, sound, staged, text, video_options=opts,
                                   duration=duration, size=(width, height), ffmpeg=ffmpeg,
                                   control=control, status=status)
            if control: control.check()
            if not staged.is_file() or staged.stat().st_size <= 0:
                raise RuntimeError('Animated video encoder did not produce a file')
            emit(status, .98, 'Saving animated audiobook video')
            os.replace(staged, target)
            if opts.captions:
                if opts.timing_file:
                    cues = load_cues(opts.timing_file, duration)
                    target.with_suffix('.srt').write_text('\n'.join(f'{i}\n{_srt_time(c.start)} --> {_srt_time(c.end)}\n{c.text}\n' for i,c in enumerate(cues,1)), encoding='utf-8')
                else:
                    from .animated_video import visible_book_text
                    write_approximate_captions(visible_book_text(text), duration, target.with_suffix('.srt'))
            emit(status, 1, f'Animated video saved: {target.name}', 1)
            return target
        emit(status, .55, 'Preparing video images')
        normalized = []
        for number, picture in enumerate(picture_paths, 1):
            normalized_picture = work / f'slide-{number:06d}.png'
            if opts.fit == 'contain':
                prep_filter = f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={opts.background},setsar=1,format=rgb24'
            else:
                prep_filter = f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,format=rgb24'
            _run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(picture), '-vf', prep_filter, '-frames:v', '1', str(normalized_picture)], control)
            if not normalized_picture.is_file() or not normalized_picture.stat().st_size:
                raise RuntimeError(f'Cannot prepare image: {picture}')
            normalized.append(normalized_picture)
            emit(status, .55 + .15 * len(normalized) / len(picture_paths),
                 f'Preparing image {len(normalized)} of {len(picture_paths)}', len(normalized) / len(picture_paths))
        concat = work / 'images.ffconcat'
        _concat_image_list(normalized, duration, concat)
        from .video_devices import arguments, encode
        video_codec, audio_codec = VIDEO_FORMATS[target.suffix.lower()]
        staged = work / ('output' + target.suffix.lower())

        def encode_slides(encoder, device):
            prefix, codec_args = arguments(encoder, opts.crf, (width, height), opts.fps,
                                           f'fps={opts.fps}', device)
            cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *prefix,
                   '-safe', '0', '-f', 'concat', '-i', str(concat), '-i', str(sound),
                   '-map', '0:v:0', '-map', '1:a:0', *codec_args, '-r', str(opts.fps),
                   '-c:a', audio_codec, '-b:a', '160k' if audio_codec == 'aac' else '128k',
                   '-ar', '48000', '-ac', '2']
            if target.suffix.lower() in {'.mp4', '.mov'}:
                cmd += ['-movflags', '+faststart']
            cmd += ['-t', f'{duration:.5f}', '-shortest', str(staged)]
            if status:
                _run(cmd, control, duration=duration, progress=lambda value:
                     emit(status, .70 + .28*value, 'Encoding with ' + encoder, value))
            else:
                _run(cmd, control)

        encode(ffmpeg, video_codec, encode_slides, status, control)
        if not staged.is_file() or staged.stat().st_size <= 0:
            raise RuntimeError('Video encoder did not produce a file')
        if control:
            control.check()
        emit(status, .98, 'Saving video and captions')
        os.replace(staged, target)
        if opts.captions:
            write_approximate_captions(display_inline_ipa(text), duration, target.with_suffix('.srt'))
    emit(status, 1, f'Video saved: {target.name}', 1)
    return target
