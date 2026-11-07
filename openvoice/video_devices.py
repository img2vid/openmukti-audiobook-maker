"""Choose encoders by encoding real frames, then retry the same job if a device fails."""
from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

from .acceleration import gpu_enabled
from .engines.base import Cancelled
from .progress import emit

# Each hardware path preserves the container's chosen bitstream.
H264 = ('h264_nvenc', 'h264_amf', 'h264_qsv', 'h264_videotoolbox',
        'h264_vaapi', 'h264_v4l2m2m', 'h264_mf', 'h264_omx', 'h264_rkmpp')
VP9 = ('vp9_qsv', 'vp9_vaapi', 'vp9_v4l2m2m', 'vp9_rkmpp')


@lru_cache(maxsize=8)
def advertised(binary):
    try:
        out = subprocess.run([binary, '-hide_banner', '-encoders'], capture_output=True,
                             timeout=6, check=True, text=True, errors='replace')
        return set(re.findall(r'^\s*V\S*\s+(\w+)', out.stdout, re.M))
    except (OSError, subprocess.SubprocessError):
        return set()


def arguments(encoder, quality, size, fps, filters='', device=''):
    prefix = []
    chain = [filters] if filters else []
    width, height = size
    bitrate = max(120000, round(width * height * fps * .1 * 2 ** ((23 - quality) / 6)))
    if encoder.endswith('_vaapi'):
        prefix = ['-vaapi_device', device]
        chain.extend(['format=nv12', 'hwupload'])
    else:
        chain.append('format=yuv420p')
    out = ['-vf', ','.join(chain), '-c:v', encoder]
    if encoder == 'libx264':
        out += ['-preset', 'veryfast', '-crf', str(quality)]
    elif encoder == 'libvpx-vp9':
        out += ['-deadline', 'realtime', '-cpu-used', '5', '-b:v', '0', '-crf', str(min(45, quality+8))]
    elif encoder.endswith('_nvenc'):
        out += ['-rc', 'vbr', '-cq', str(max(1, quality)), '-b:v', str(bitrate)]
    else:
        out += ['-b:v', str(bitrate)]
        if encoder.endswith('_videotoolbox'):
            out += ['-allow_sw', '0']
        elif encoder.endswith('_mf'):
            out += ['-hw_encoding', '1']
    return prefix, out


@lru_cache(maxsize=128)
def probe(binary, encoder, device):
    prefix, output = arguments(encoder, 23, (320, 240), 24, device=device)
    command = [binary, '-hide_banner', '-loglevel', 'error', '-nostdin', *prefix,
               '-f', 'lavfi', '-i', 'color=black:s=320x240:r=24', '-frames:v',
               '3', *output, '-f', 'null', '-']
    try:
        return subprocess.run(command, timeout=8, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def candidates(binary, software):
    if gpu_enabled():
        for encoder in H264 if software == 'libx264' else VP9:
            if encoder not in advertised(binary):
                continue
            devices = sorted(Path('/dev/dri').glob('renderD*')) if encoder.endswith('_vaapi') else ['']
            for device in devices:
                if probe(binary, encoder, str(device)):
                    yield encoder, str(device)
    yield software, ''


def encode(binary, software, run, status=None, control=None):
    for encoder, device in candidates(binary, software):
        if control:
            control.check()
        emit(status, .70, 'Encoding video with ' + encoder)
        try:
            run(encoder, device)
            return
        except Cancelled:
            raise
        except (OSError, RuntimeError) as exc:
            if control:
                control.check()
            if encoder == software:
                raise
            emit(status, .70, f'{encoder} failed. Trying another encoder ({str(exc)[-160:]})')
