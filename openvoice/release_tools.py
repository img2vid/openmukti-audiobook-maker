"""Offline publication and engineering tools for the desktop application."""
import hashlib
from html import escape
from importlib import metadata
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED


def caption_export(source, target):
    from .animated_video import load_cues
    target = Path(target)
    if target.resolve() == Path(source).resolve():
        raise ValueError('Select a separate subtitle output')
    kind = target.suffix.lower()
    if kind not in {'.srt', '.vtt'}:
        raise ValueError('Choose an SRT or VTT output')
    def clock(ms):
        seconds, fraction = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        separator = ',' if kind == '.srt' else '.'
        return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{fraction:03}'
    rows = ['WEBVTT', ''] if kind == '.vtt' else []
    for index, cue in enumerate(load_cues(source, float('inf')), 1):
        start = round(cue.start * 1000)
        end = max(start + 1, round(cue.end * 1000))
        rows.extend([str(index), f'{clock(start)} --> {clock(end)}', escape(cue.text, quote=False), ''])
    target.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def release_archive(folder, output):
    folder, output = Path(folder).resolve(), Path(output).resolve()
    if not folder.is_dir() or output.is_relative_to(folder):
        raise ValueError('Choose an existing release folder and an output ZIP outside it')
    manifest = {}
    with NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        stage = Path(handle.name)
    try:
        with ZipFile(stage, 'w', compression=ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob('*')):
                if path.is_symlink() or not path.is_file():
                    continue
                name = path.relative_to(folder).as_posix()
                if name.casefold() == 'sha256.json':
                    raise ValueError('sha256.json is reserved for the generated manifest')
                digest = hashlib.sha256()
                with path.open('rb') as src, archive.open(name, 'w', force_zip64=True) as dest:
                    while data := src.read(1024 * 1024):
                        digest.update(data)
                        dest.write(data)
                manifest[name] = digest.hexdigest()
            if not manifest:
                raise ValueError('Release folder is empty')
            archive.writestr('sha256.json', json.dumps(manifest, indent=2, ensure_ascii=False))
        stage.replace(output)
    finally:
        stage.unlink(missing_ok=True)


def environment_inventory():
    rows = []
    for package in metadata.distributions():
        record = package.metadata
        rows.append({'name': record.get('Name'), 'version': package.version,
                     'license': record.get('License-Expression') or record.get('License') or 'Unspecified'})
    return sorted(rows, key=lambda row: (row['name'] or '').casefold())


def quality_report(path):
    """Measure decoded audio with FFmpeg's EBU R128 and silence filters."""
    from .fftools import find_binary
    import re
    import subprocess
    path = Path(path).resolve(strict=True)
    executable = find_binary('ffmpeg')
    if not executable:
        raise RuntimeError('Audio analysis requires FFmpeg')
    command = [executable, '-nostdin', '-hide_banner', '-nostats', '-i', str(path),
               '-map', '0:a:0', '-af', 'silencedetect=noise=-50dB:d=1,loudnorm=print_format=json',
               '-f', 'null', '-']
    result = subprocess.run(command, capture_output=True, text=True, errors='replace')
    if result.returncode:
        raise ValueError(result.stderr[-1200:])
    meter = json.loads(result.stderr[result.stderr.rindex('{'):].strip())
    intervals = re.findall(r'silence_end: ([\d.e+\-]+) \| silence_duration: ([\d.e+\-]+)', result.stderr)
    peak = float(meter['input_tp'])
    return {'integrated_loudness_LUFS': meter['input_i'], 'true_peak_dBTP': meter['input_tp'],
            'peak_at_or_above_0_dBTP': peak >= 0, 'loudness_range_LU': meter['input_lra'],
            'silence_threshold_dB': -50, 'minimum_silence_seconds': 1,
            'silences': [{'start': max(0, round(float(end)-float(duration), 6)), 'end': float(end)}
                         for end, duration in intervals]}


def publish_book(description, target):
    """Publish a local ordered chapter manifest as an RSS feed or M4B."""
    from .audiofx import audio_info
    from .fftools import find_binary
    from urllib.parse import urlsplit
    from xml.etree import ElementTree as ET
    import math
    import mimetypes
    import subprocess
    import tempfile
    description, target = Path(description).resolve(), Path(target).resolve()
    data = json.loads(description.read_text(encoding='utf-8-sig'))
    chapters = data['chapters']
    if not chapters or not data['title'].strip():
        raise ValueError('Add a book title and at least one chapter')
    paths = [(description.parent / c['file']).resolve(strict=True) for c in chapters]
    if target in paths or target == description:
        raise ValueError('Output must be separate from all inputs')
    def url(value):
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError('RSS links and enclosure URLs must be absolute HTTP(S) URLs')
        return value
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        stage = Path(folder) / ('book' + target.suffix.lower())
        if stage.suffix == '.xml':
            root = ET.Element('rss', version='2.0')
            channel = ET.SubElement(root, 'channel')
            for key, value in [('title', data['title']), ('description', data.get('description') or data['title']),
                               ('link', url(data['link'])), ('language', data.get('language', 'en'))]:
                ET.SubElement(channel, key).text = value
            for chapter, path in zip(chapters, paths):
                item = ET.SubElement(channel, 'item')
                ET.SubElement(item, 'title').text = chapter['title']
                enclosure = url(chapter['url'])
                ET.SubElement(item, 'guid', isPermaLink='true').text = enclosure
                ET.SubElement(item, 'enclosure', url=enclosure, length=str(path.stat().st_size),
                              type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
            ET.ElementTree(root).write(stage, encoding='utf-8', xml_declaration=True)
        elif stage.suffix == '.m4b':
            executable = find_binary('ffmpeg')
            if not executable:
                raise RuntimeError('M4B encoding requires FFmpeg')
            def value(text):
                return ''.join(('\\' if c in '=;#\\' else '') + c for c in str(text).replace('\r', ' ').replace('\n', ' '))
            meta = [';FFMETADATA1', 'title='+value(data['title'])]
            for key in ('artist', 'album', 'language', 'comment'):
                if data.get(key):
                    meta.append(key+'='+value(data[key]))
            total = 0.0
            concat = []
            def run(args):
                subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error', *args], cwd=folder, check=True)
            for index, (chapter, path) in enumerate(zip(chapters, paths)):
                name = f'chapter-{index}.flac'
                run(['-i', str(path), '-map', '0:a:0', '-ar', '44100', '-ac', '2', name])
                duration = audio_info(Path(folder)/name)['duration_seconds']
                if not math.isfinite(duration) or duration <= 0:
                    raise ValueError(f'Empty audio chapter: {path.name}')
                start = round(total*1000)
                total += duration
                meta.extend(['[CHAPTER]', 'TIMEBASE=1/1000', f'START={start}', f'END={round(total*1000)}', 'title='+value(chapter['title'])])
                concat.append(f"file '{name}'")
            (Path(folder)/'chapters.txt').write_text('\n'.join(concat)+'\n', encoding='utf-8')
            (Path(folder)/'meta.txt').write_text('\n'.join(meta)+'\n', encoding='utf-8')
            run(['-f','concat','-i','chapters.txt','-f','ffmetadata','-i','meta.txt','-map','0:a:0','-map_metadata','1',
                 '-map_chapters','1','-c:a','aac','-b:a','96k','-movflags','+faststart','-f','mp4',str(stage)])
        else:
            raise ValueError('Choose .m4b or .xml output')
        stage.replace(target)


def package_subtitles(output, tracks):
    """Keep the original Unicode subtitle bytes, keyed by language."""
    import re
    import shutil
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp:
        root = Path(temp)
        seen = set()
        for entry in tracks:
            language, separator, filename = entry.partition('=')
            if not separator or not re.fullmatch(r'[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*', language):
                raise ValueError('Each track needs a language tag and file, e.g. bn=subtitles.srt')
            path = Path(filename)
            suffix = path.suffix.lower()
            if suffix not in {'.ass', '.vtt', '.srt'} or not path.is_file() or not path.stat().st_size:
                raise ValueError(f'Choose a nonempty ASS, WebVTT or SRT track: {filename}')
            if language.lower() in seen or path.resolve() == Path(output).resolve():
                raise ValueError('Choose distinct language tags and a separate output file')
            seen.add(language.lower())
            shutil.copyfile(path, root / ('captions.' + language.lower() + suffix))
        release_archive(root, output)


def compare_recordings(reference, candidate, max_error):
    """Compare aligned integer PCM audio in blocks. Error uses full-scale units."""
    import math
    import wave
    if not 0 <= max_error <= 2:
        raise ValueError('Maximum RMS error must be between 0 and 2')
    with wave.open(str(reference), 'rb') as ref, wave.open(str(candidate), 'rb') as new:
        def layout(audio):
            return (audio.getframerate(), audio.getnchannels(), audio.getsampwidth(), audio.getnframes())
        if layout(ref) != layout(new):
            return {'passed': False, 'reason': 'PCM format or length changed',
                    'reference_layout': layout(ref), 'candidate_layout': layout(new)}
        frames = ref.getnframes()
        width = ref.getsampwidth()
        if not frames or width not in (1, 2, 3, 4):
            raise ValueError('Choose nonempty integer PCM WAV recordings')
        energy = 0
        for start in range(0, frames, 8192):
            length = min(8192, frames - start)
            a, b = ref.readframes(length), new.readframes(length)
            if len(a) != length * width * ref.getnchannels() or len(b) != len(a):
                raise ValueError('Truncated WAV data')
            if a != b:
                for offset in range(0, len(a), width):
                    delta = (int.from_bytes(a[offset:offset+width], 'little', signed=width > 1)
                             - int.from_bytes(b[offset:offset+width], 'little', signed=width > 1))
                    energy += delta * delta
        error = math.sqrt(energy / (frames * ref.getnchannels())) / (1 << (width * 8 - 1))
        return {'passed': error <= max_error, 'rms_error': error, 'max_rms_error': max_error,
                'duration_seconds': frames / ref.getframerate()}
