from __future__ import annotations
import subprocess
import wave
from pathlib import Path
from .fftools import find_binary

class AudioError(RuntimeError):
    pass

def combine_wav(inputs: list[Path], target: Path, pause_ms: int=0, *, progress=None, control=None) -> None:
    if not inputs:
        raise AudioError('No audio chunks produced')
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(inputs[0]), 'rb') as first:
            params = first.getparams()
        with wave.open(str(target), 'wb') as output:
            output.setnchannels(params.nchannels)
            output.setsampwidth(params.sampwidth)
            output.setframerate(params.framerate)
            for index, path in enumerate(inputs):
                with wave.open(str(path), 'rb') as source:
                    if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (params.nchannels, params.sampwidth, params.framerate, params.comptype):
                        raise AudioError('Audio engine produced incompatible WAV formats across chunks')
                    while True:
                        if control:
                            control.check()
                        block = source.readframes(32768)
                        if not block:
                            break
                        output.writeframesraw(block)
                if index < len(inputs) - 1 and pause_ms:
                    if params.comptype != 'NONE':
                        raise AudioError('Cannot insert silence into compressed WAV')
                    frame_count = round(params.framerate * pause_ms / 1000)
                    silence_byte = b'\x80' if params.sampwidth == 1 else b'\x00'
                    output.writeframesraw(silence_byte * frame_count * params.sampwidth * params.nchannels)
                if progress:
                    progress(index + 1, len(inputs))
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioError(f'Cannot combine WAV audio: {exc}') from exc

def convert_wav(source: Path, destination: Path, *, progress=None, control=None) -> None:
    ffmpeg = find_binary('ffmpeg')
    if not ffmpeg:
        raise AudioError('FFmpeg is unavailable. Use an Openmukti Audiobook Maker build with integrated media tools.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-i', str(source), str(destination)]
    if progress is not None:
        from .progress import run_ffmpeg
        with wave.open(str(source), 'rb') as audio:
            duration = audio.getnframes() / audio.getframerate()
        run_ffmpeg(args, control=control, progress=progress, duration=duration)
        return
    proc = subprocess.run(args, capture_output=True, check=False)
    if proc.returncode:
        raise AudioError(proc.stderr.decode('utf-8', 'replace').strip() or 'FFmpeg conversion failed')

def write_raw_pcm(wav_file: Path, output) -> None:
    with wave.open(str(wav_file), 'rb') as wav:
        if wav.getcomptype() != 'NONE':
            raise AudioError('Raw output requires uncompressed PCM WAV')
        while True:
            frames = wav.readframes(16384)
            if not frames:
                break
            output.write(frames)
