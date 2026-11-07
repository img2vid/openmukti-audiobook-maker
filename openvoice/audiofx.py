from __future__ import annotations
import json
import os
import shutil
from .fftools import find_binary
import subprocess
import tempfile
import wave
from .progress import emit, run_ffmpeg
from pathlib import Path
FORMATS = ('wav', 'mp3', 'flac', 'ogg', 'm4a', 'opus', 'aac', 'aiff', 'wma')

def audio_info(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Audio file not found: {path}')
    info = {'path': str(path), 'bytes': path.stat().st_size, 'format': path.suffix.lower().lstrip('.')}
    if path.suffix.lower() == '.wav':
        with wave.open(str(path), 'rb') as source:
            info.update(channels=source.getnchannels(), sample_rate=source.getframerate(), sample_width_bits=source.getsampwidth() * 8, frames=source.getnframes(), duration_seconds=round(source.getnframes() / source.getframerate(), 4))
        return info
    probe = find_binary('ffprobe')
    if not probe:
        raise RuntimeError('FFprobe is unavailable. Use an Openmukti Audiobook Maker build with integrated media tools.')
    run = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration:stream=sample_rate,channels,codec_name', '-of', 'json', str(path)], capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr[:500])
    data = json.loads(run.stdout)
    info['duration_seconds'] = float(data.get('format', {}).get('duration', 0))
    info['streams'] = data.get('streams', [])
    return info

def process_audio(inputs: list[str | Path], output: str | Path, *, operation: str='convert', start: float=0, duration: float=0, speed: float=1, gain: float=0, sample_rate: int=0, channels: int=0, fade_seconds: float=1, compression: int=0, eq_frequency: float=1000, eq_gain: float=0, pan: float=0, silence_db: float=-45, silence_duration: float=0.3, status=None, control=None) -> Path:
    emit(status, 0, 'Preparing audio processing')
    ffmpeg = find_binary('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('FFmpeg is unavailable. Use an Openmukti Audiobook Maker build with integrated media tools.')
    if not inputs:
        raise ValueError('At least one audio input is required')
    output = Path(output).expanduser()
    if output.suffix.lower().lstrip('.') not in FORMATS:
        raise ValueError('Unsupported audio output format')
    if not 0.25 <= speed <= 4 or not -60 <= gain <= 30:
        raise ValueError('Speed must be 0.25..4 and gain must be -60..30 dB')
    if not 0 <= start <= 24 * 3600 or not 0 <= duration <= 24 * 3600:
        raise ValueError('Invalid trim bounds')
    if sample_rate and (not 8000 <= sample_rate <= 192000):
        raise ValueError('Sample rate must be 8000..192000')
    if channels not in (0, 1, 2):
        raise ValueError('Channels must be 1 or 2')
    if not 0 <= fade_seconds <= 60 or not 0 <= compression <= 100:
        raise ValueError('Invalid fade or compression value')
    allowed = {'convert', 'join', 'trim', 'speed', 'gain', 'normalize', 'reverse', 'fade-in', 'fade-out', 'mono', 'stereo', 'resample', 'denoise', 'compress', 'deess', 'equalize', 'pan', 'trim-silence'}
    if operation not in allowed:
        raise ValueError(f'Unknown audio operation: {operation}')
    if not 20 <= eq_frequency <= 20000 or not -24 <= eq_gain <= 24:
        raise ValueError('EQ frequency must be 20..20000 Hz and gain -24..24 dB')
    if not -1 <= pan <= 1:
        raise ValueError('Stereo pan must be -1 (left) through +1 (right)')
    if not -90 <= silence_db <= -10 or not 0.05 <= silence_duration <= 30:
        raise ValueError('Silence threshold or minimum duration is invalid')
    if operation == 'join' and len(inputs) < 2:
        raise ValueError('Joining requires two or more files')
    if operation != 'join' and len(inputs) != 1:
        raise ValueError('Only join accepts multiple files')
    input_paths = [Path(p).expanduser().resolve() for p in inputs]
    for path in input_paths:
        if not path.is_file():
            raise ValueError(f'Missing audio input: {path}')
    if output.resolve() in input_paths:
        raise ValueError('Output cannot be the same as an input')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.openvoice-audio-',dir=output.parent) as work:
        staging = Path(work) / ('processed' + output.suffix.lower())
        if (input_paths[0].suffix.lower()=='.wav' and output.suffix.lower()=='.wav'
                and not sample_rate and not channels and len(input_paths)==1):
            from .compute import pcm_effect
            if pcm_effect(input_paths[0],staging,operation=operation,gain=gain,pan=pan,
                          fade_seconds=fade_seconds,duration=duration,control=control,status=status):
                if control:control.check()
                os.replace(staging,output)
                emit(status,1,'Audio saved')
                return output
        cmd = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y']
        for path in input_paths:
            cmd += ['-i', str(path)]
        if operation == 'join':
            connections = ''.join((f'[{i}:a:0]' for i in range(len(input_paths))))
            cmd += ['-filter_complex', f'{connections}concat=n={len(input_paths)}:v=0:a=1[a]', '-map', '[a]']
        else:
            filters = []
            if operation == 'trim':
                if not duration:
                    raise ValueError('Trim requires a positive duration')
                filters.append(f'atrim=start={start}:duration={duration}')
                filters.append('asetpts=PTS-STARTPTS')
            if operation == 'speed':
                filters.append(f'atempo={speed}')
            if operation == 'gain':
                filters.append(f'volume={gain}dB')
            if operation == 'normalize':
                filters.append('loudnorm=I=-16:TP=-1.5:LRA=11')
            if operation == 'reverse':
                filters.append('areverse')
            if operation == 'fade-in':
                filters.append(f'afade=t=in:st=0:d={fade_seconds}')
            if operation == 'fade-out':
                if duration <= 0:
                    raise ValueError('Fade-out requires --duration (total audio duration)')
                filters.append(f'afade=t=out:st={max(0, duration - fade_seconds)}:d={fade_seconds}')
            if operation == 'denoise':
                filters.append('afftdn')
            if operation == 'compress':
                threshold = -40 + compression * 0.3
                filters.append(f'acompressor=threshold={10 ** (threshold / 20):.5f}:ratio=3:attack=15:release=150')
            if operation == 'deess':
                # FFmpeg built-in deesser filter, with a moderate safe default.
                filters.append('deesser=i=0.35:m=0.5:f=0.5')
            if operation == 'equalize':
                filters.append(f'equalizer=f={eq_frequency}:t=q:w=1:g={eq_gain}')
            if operation == 'pan':
                # Maintain stereo; at center preserve L/R, at extremes mute opposite side.
                filters.append(f'pan=stereo|c0={1-max(0,pan):.5f}*c0|c1={1+min(0,pan):.5f}*c1')
            if operation == 'trim-silence':
                # Remove leading/trailing long silences, not pauses inside narration.
                filt = f'silenceremove=start_periods=1:start_duration={silence_duration}:start_threshold={silence_db}dB:stop_periods=-1:stop_duration={silence_duration}:stop_threshold={silence_db}dB'
                filters.append(filt)
            if filters:
                cmd += ['-af', ','.join(filters)]
        if operation == 'mono':
            channels = 1
        if operation == 'stereo':
            channels = 2
        if channels:
            cmd += ['-ac', str(channels)]
        if sample_rate:
            cmd += ['-ar', str(sample_rate)]
        cmd += [str(staging)]
        if status:
            try:
                seconds = sum(audio_info(p)['duration_seconds'] for p in input_paths)
                if operation == 'trim': seconds = min(duration, max(0, seconds-start))
                if operation == 'speed': seconds /= speed
            except (OSError, ValueError, RuntimeError):
                seconds = None
            emit(status, .02, f'Processing audio: {operation}')
            run_ffmpeg(cmd,control=control,duration=seconds,
                       progress=lambda value: emit(status,.02+.96*value,f'Processing audio: {operation}',value))
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f'FFmpeg failed: {result.stderr[:1600]}')
        if not staging.is_file() or staging.stat().st_size == 0:
            raise RuntimeError('Audio processing produced no output')
        fd, tmp_name = tempfile.mkstemp(prefix='.openvoice-', suffix=output.suffix, dir=output.parent)
        os.close(fd)
        try:
            emit(status, .98, 'Saving processed audio')
            shutil.copyfile(staging, tmp_name)
            if control: control.check()
            os.replace(tmp_name, output)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
    emit(status, 1, f'Audio saved: {output.name}', 1)
    return output
