"""Device selection inside the Piper inference process."""
import os
import warnings

PROVIDERS = ('CUDAExecutionProvider', 'ROCMExecutionProvider', 'MIGraphXExecutionProvider',
             'DmlExecutionProvider', 'CoreMLExecutionProvider', 'OpenVINOExecutionProvider',
             'TensorrtExecutionProvider', 'WebGpuExecutionProvider')


def gpu_enabled():
    return os.environ.get('OPENMUKTI_GPU_MODE', 'auto') == 'auto'


def piper_gpu_enabled():
    return gpu_enabled() and os.environ.get('OPENMUKTI_PIPER_GPU', '1') != '0'


class _FallbackSession:
    def __init__(self, accelerated, cpu_factory):
        self.session = accelerated
        self.cpu_factory = cpu_factory

    def __getattr__(self, name):
        return getattr(self.session, name)

    def run(self, *args, **kwargs):
        try:
            return self.session.run(*args, **kwargs)
        except Exception as exc:
            if self.cpu_factory is None:
                raise
            warnings.warn(f'Piper accelerator failed during inference. Retrying on CPU: {exc}')
            self.session = self.cpu_factory()
            self.cpu_factory = None
        return self.session.run(*args, **kwargs)


def load_voice(voice_class, model, config):
    def cpu_voice():
        return voice_class.load(str(model), config_path=str(config), use_cuda=False)

    if not piper_gpu_enabled():
        return cpu_voice()
    try:
        import onnxruntime as ort
        available = ort.get_available_providers()
    except (ImportError, RuntimeError, OSError):
        return cpu_voice()
    for provider in PROVIDERS:
        if provider not in available:
            continue
        try:
            if provider == 'CUDAExecutionProvider':
                voice = voice_class.load(str(model), config_path=str(config), use_cuda=True)
                session = voice.session
                if provider not in session.get_providers():
                    continue
            else:
                options = ort.SessionOptions()
                if provider == 'DmlExecutionProvider':
                    options.enable_mem_pattern = False
                    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                accelerator = (provider, {'device_type': 'GPU'}) if provider == 'OpenVINOExecutionProvider' else provider
                session = ort.InferenceSession(str(model), sess_options=options,
                                               providers=[accelerator, 'CPUExecutionProvider'])
                if provider not in session.get_providers():
                    continue
                voice = cpu_voice()
            voice.session = _FallbackSession(session, lambda: cpu_voice().session)
            return voice
        except Exception as exc:
            warnings.warn(f'Piper could not initialize {provider}: {exc}')
    return cpu_voice()
