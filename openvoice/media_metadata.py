"""Local audio metadata / embedded cover writing via FFmpeg without reencoding audio."""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from .fftools import find_binary

AUDIO = {'.mp3','.flac','.m4a','.m4b','.ogg','.opus','.wav'}
KEYS = {'title','artist','album','album_artist','genre','date','track','disc','composer','comment','language','copyright','description','publisher'}
COVER_FORMATS = {'.png','.jpg','.jpeg'}
EMBEDDED_ART_FORMATS = {'.mp3','.flac','.m4a','.m4b'}


def tag_audio(source: str | Path, output: str | Path, *, tags: dict[str,str], cover: str | Path | None = None) -> Path:
    """Copy audio bits and write metadata into a new file; original is untouched."""
    original = Path(source).expanduser().resolve()
    dest = Path(output).expanduser().resolve()
    if not original.is_file() or original.suffix.lower() not in AUDIO:
        raise ValueError('Choose an existing supported audio file')
    if dest == original:
        raise ValueError('Choose a different output path to preserve the original audio')
    if dest.suffix.lower() != original.suffix.lower():
        raise ValueError('Input and output extensions must match for lossless audio stream copying')
    if not isinstance(tags, dict) or len(tags) > 32:
        raise ValueError('Invalid audio metadata fields')
    for key, value in tags.items():
        if key not in KEYS or not isinstance(value, str) or len(value) > 10000:
            raise ValueError('Invalid metadata key or value: ' + str(key))
    image = Path(cover).expanduser().resolve() if cover else None
    if image:
        if image.suffix.lower() not in COVER_FORMATS or not image.is_file():
            raise ValueError('Embedded cover must be an existing JPG or PNG image')
        if original.suffix.lower() not in EMBEDDED_ART_FORMATS:
            raise ValueError('This format does not reliably support attached cover artwork')
        if image.stat().st_size > 50 * 1024 * 1024:
            raise ValueError('Cover artwork is too large (maximum 50 MB)')
    ffmpeg = find_binary('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is required for metadata editing')
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.openmukti-tags-', suffix=dest.suffix, dir=dest.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-i', str(original)]
        if image:
            cmd += ['-i', str(image), '-map', '0:a:0', '-map', '1:v:0', '-c:a', 'copy',
                    '-c:v', 'mjpeg', '-disposition:v:0', 'attached_pic']
        else:
            cmd += ['-map', '0:a', '-c:a', 'copy']
        cmd += ['-map_metadata', '0']
        for key, value in tags.items():
            cmd += ['-metadata', f'{key}={value}']
        if dest.suffix.lower() == '.mp3':
            cmd += ['-id3v2_version', '3']
        cmd += [str(temp)]
        finished = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if finished.returncode or not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError('Audio metadata writing failed: ' + finished.stderr[:800])
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return dest
