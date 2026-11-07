"""Opt-in CPU resource profiles and capability reporting for local speech engines.

A GPU vendor/driver is never assumed to support every model or backend.
Unrecognized providers fall back to CPU instead of failing startup.
"""
from __future__ import annotations
import importlib.util
import os
import shutil
from pathlib import Path

PROFILES = {
    'low': {'threads': 1, 'description': 'Minimum resource use for low-memory/older systems'},
    'balanced': {'threads': 2, 'description': 'Moderate CPU use for everyday systems'},
    'fast': {'threads': max(2, min(8, os.cpu_count() or 2)), 'description': 'Use additional CPU cores when available'},
}
ORT_PROVIDERS = {
    'CUDAExecutionProvider': 'NVIDIA CUDA',
    'ROCMExecutionProvider': 'AMD ROCm',
    'DmlExecutionProvider': 'DirectML (various Windows GPUs)',
    'CoreMLExecutionProvider': 'Apple CoreML',
    'OpenVINOExecutionProvider': 'Intel OpenVINO',
    'TensorrtExecutionProvider': 'NVIDIA TensorRT',
    'CPUExecutionProvider': 'CPU',
}


def apply_cpu_profile(profile: str) -> dict:
    if profile not in PROFILES:
        raise ValueError('CPU profile must be low, balanced or fast')
    amount = PROFILES[profile]['threads']
    for variable in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                     'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
        os.environ[variable] = str(amount)
    os.environ['OPENMUKTI_CPU_PROFILE'] = profile
    return {'profile':profile,'threads':amount,'description':PROFILES[profile]['description']}


def gpu_preference(enabled: bool) -> None:
    os.environ['OPENMUKTI_GPU_MODE'] = 'auto' if enabled else 'cpu'
    os.environ['OPENMUKTI_PIPER_GPU'] = '1' if enabled else '0'


def hardware_status(folder: str | Path = '.') -> dict:
    """Describe local capabilities; reported availability is not a claim that all TTS engines use them."""
    root = Path(folder).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    space = shutil.disk_usage(root)
    providers, warnings = [], []
    if importlib.util.find_spec('onnxruntime') is not None:
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
        except Exception as exc:
            warnings.append('ONNX Runtime provider discovery failed: ' + str(exc)[:160])
    from .fftools import find_binary
    from .video_devices import H264, VP9, advertised, candidates
    ff = find_binary('ffmpeg')
    encoders = sorted(advertised(ff).intersection(H264 + VP9)) if ff else []
    working = {codec: [name for name, _ in candidates(ff, codec) if name != codec]
               for codec in ('libx264', 'libvpx-vp9')} if ff else {}
    from .compute import context
    backend=context()
    legacy={}
    if os.environ.get('OPENMUKTI_GPU_MODE','auto')=='auto':
        import json,subprocess
        from .job_queue import cli_process
        try:
            cmd,env=cli_process()
            check=subprocess.run(cmd+['_gl-probe'],capture_output=True,env=env,timeout=10)
            legacy=json.loads(check.stdout) if check.returncode==0 else {'available':False}
        except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired):
            legacy={'available':False}
    return {'egl_es2_compositor':legacy,'opencl_pixel_and_pcm_device': backend[3] if backend else None, 'video_hardware_encoders_in_build': encoders, 'video_hardware_encoders_passing_probe': working,
            'logical_cpus':os.cpu_count() or 1,
            'cpu_profile':os.environ.get('OPENMUKTI_CPU_PROFILE','system-default'),
            'cpu_profile_presets':PROFILES,
            'gpu_requested':os.environ.get('OPENMUKTI_GPU_MODE','auto') == 'auto',
            'onnxruntime_providers':[{'id':p,'name':ORT_PROVIDERS.get(p, p)} for p in providers],
            'disk_free_bytes':space.free,
            'disk_total_bytes':space.total,
            'warnings':warnings,
            'notes':['GPU execution requires a compatible driver, hardware and TTS engine backend.',
                     'Piper checks accelerator providers in its own ONNX Runtime installation.',
                     'Unlisted or older GPUs may still work using CPU fallback.',
                     'Kokoro, Coqui and compatible Pocket versions try PyTorch devices. Kitten uses its ONNX Runtime.',
                     'OpenCV OpenCL filters and optional PyOpenCL audio analysis use compatible GPU drivers.']}
