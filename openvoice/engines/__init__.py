from __future__ import annotations
from importlib.metadata import entry_points
from .base import EngineError, RunControl, SpeechEngine, SpeechSettings
from .builtin import BUILTINS
from .neural import NEURAL_BUILTINS
from ..piper_models import discover_voices

def all_engines() -> dict[str, SpeechEngine]:
    registry: dict[str, SpeechEngine] = {engine.key: engine() for engine in [*BUILTINS, *NEURAL_BUILTINS]}
    from ..desktop_prefs import read
    if read().get('permissions',{}).get('native_plugins',True) is False:
        return registry
    try:
        discovered = entry_points(group='openvoice.engines')
    except TypeError:
        discovered = entry_points().get('openvoice.engines', [])
    for entry in discovered:
        try:
            cls = entry.load()
            engine = cls()
            if not isinstance(engine, SpeechEngine) or not engine.key or engine.key in registry:
                continue
            registry[engine.key] = engine
        except Exception:
            continue
    return registry

def get_engine(name: str, model: str='', voice: str='') -> SpeechEngine:
    registry = all_engines()
    if name != 'auto':
        chosen = registry.get(name)
        if chosen is None:
            raise EngineError(f"Unknown engine {name!r}. Available IDs: {', '.join(registry)}")
        if not chosen.available():
            raise EngineError(f'Engine {name!r} is not installed or not supported on this OS')
        return chosen
    # An explicitly chosen catalog voice must select Piper even before ONNX
    # assets are downloaded. Do not turn ordinary system voices into Piper.
    from ..voice_catalog import catalog_voice
    from ..piper_models import get_voice
    piper_selection = bool(voice and (get_voice(voice) or catalog_voice(voice)))
    if piper_selection and not registry['piper'].available():
        raise EngineError('A Piper voice was selected, but the Piper speech runtime is unavailable. Install the Piper CPU runtime before speaking.')
    if registry['piper'].available() and (model or piper_selection or discover_voices()):
        return registry['piper']
    import sys
    preferred = {'win32': 'sapi', 'darwin': 'macos'}.get(sys.platform, 'espeak')
    for key in (preferred, 'espeak', 'sapi', 'macos', 'flite'):
        engine = registry[key]
        if engine.available():
            return engine
    raise EngineError('No speech engine found. Windows: use a SAPI voice; Linux: install espeak-ng; macOS: use say; or install Piper and a model.')
__all__ = ['SpeechEngine', 'SpeechSettings', 'RunControl', 'EngineError', 'all_engines', 'get_engine']
