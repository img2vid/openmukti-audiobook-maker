from __future__ import annotations
import importlib.resources
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from .base import EngineError, RunControl, SpeechEngine, SpeechSettings, invoke
from ..piper_models import discover_voices, get_voice, piper_binary, speaker_list
from ..voice_catalog import cached_catalog, ensure_piper_voice
from ..piper_compat import inspect_config, compatible_cli_config, python_piper_available, render_python_piper, incompatibility_message

def _normal_rate(value: int, baseline: int=175) -> int:
    return max(80, min(450, round(baseline * (1.0 + value * 0.07))))

class WindowsSAPI(SpeechEngine):
    key = 'sapi'
    label = 'Windows SAPI 5 (system voices)'
    supports_rate = True
    supports_volume = True

    def available(self) -> bool:
        return platform.system() == 'Windows' and shutil.which('powershell.exe') is not None

    def _command(self, mode: str, settings: SpeechSettings, script: Path, text_path: Path | None=None, output: Path | None=None) -> list[str]:
        args = [shutil.which('powershell.exe') or 'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned', '-File', str(script), '-Mode', mode]
        if text_path:
            args.extend(['-TextPath', str(text_path)])
        if output:
            args.extend(['-OutputPath', str(output)])
        if settings.voice:
            args.extend(['-VoiceName', settings.voice])
        args.extend(['-Rate', str(settings.rate), '-Volume', str(settings.volume)])
        return args

    def voices(self) -> list[str]:
        with importlib.resources.as_file(importlib.resources.files('openvoice').joinpath('resources/sapi.ps1')) as script:
            output = invoke(self._command('voices', SpeechSettings(), script))
        decoded = output.decode('utf-8-sig', 'replace').strip()
        try:
            names = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise EngineError(f'Could not read Windows SAPI voice list: {decoded[:300]}') from exc
        return [names] if isinstance(names, str) else list(names or [])

    def _perform(self, mode: str, text: str, settings: SpeechSettings, output: Path | None=None, control: RunControl | None=None) -> None:
        with tempfile.TemporaryDirectory(prefix='openvoice-sapi-') as work:
            file = Path(work) / 'input.txt'
            file.write_text(text, encoding='utf-8')
            with importlib.resources.as_file(importlib.resources.files('openvoice').joinpath('resources/sapi.ps1')) as script:
                invoke(self._command(mode, settings, script, file, output), control=control)

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None=None) -> None:
        self._perform('speak', text, settings, control=control)

    def render_wav(self, text: str, output: Path, settings: SpeechSettings, control: RunControl | None=None) -> None:
        self._perform('render', text, settings, output=output, control=control)

class EspeakNG(SpeechEngine):
    key = 'espeak'
    label = 'eSpeak NG (small and fast)'
    supports_pitch = True
    supports_rate = True
    supports_volume = True

    @staticmethod
    def binary() -> str | None:
        return shutil.which('espeak-ng') or shutil.which('espeak')

    def available(self) -> bool:
        return self.binary() is not None

    def voices(self) -> list[str]:
        out = invoke([self.binary() or 'espeak-ng', '--voices'])
        choices = []
        for line in out.decode('utf-8', 'replace').splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 5:
                choices.append(parts[4])
        return sorted(set(choices))

    def _args(self, settings: SpeechSettings) -> list[str]:
        args = [self.binary() or 'espeak-ng', '-s', str(_normal_rate(settings.rate)), '-p', str(max(0, min(99, round(50 + settings.pitch * 4.5)))), '-a', str(max(0, min(100, settings.volume)))]
        if settings.voice:
            args.extend(['-v', settings.voice])
        return args

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None=None) -> None:
        invoke(self._args(settings) + ['--stdin'], stdin=text.encode('utf-8'), control=control)

    def render_wav(self, text: str, output: Path, settings: SpeechSettings, control: RunControl | None=None) -> None:
        invoke(self._args(settings) + ['-w', str(output), '--stdin'], stdin=text.encode('utf-8'), control=control)

class MacOSVoice(SpeechEngine):
    key = 'macos'
    label = 'macOS system voices'
    supports_rate = True

    def available(self) -> bool:
        return platform.system() == 'Darwin' and shutil.which('say') is not None

    def voices(self) -> list[str]:
        output = invoke(['say', '-v', '?']).decode('utf-8', 'replace')
        names = []
        for line in output.splitlines():
            before_comment = line.split('#')[0].strip()
            tokens = before_comment.split()
            if len(tokens) >= 2:
                names.append(' '.join(tokens[:-1]))
        return names

    def _args(self, settings: SpeechSettings) -> list[str]:
        args = ['say', '-r', str(_normal_rate(settings.rate))]
        if settings.voice:
            args.extend(['-v', settings.voice])
        return args

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None=None) -> None:
        self._say(text, settings, control)

    def _say(self, text: str, settings: SpeechSettings, control: RunControl | None, output: Path | None=None) -> None:
        with tempfile.TemporaryDirectory(prefix='openvoice-macos-') as work:
            input_path = Path(work) / 'input.txt'
            input_path.write_text(text, encoding='utf-8')
            args = self._args(settings)
            if output:
                aiff = Path(work) / 'speech.aiff'
                args.extend(['-o', str(aiff)])
            args.extend(['-f', str(input_path)])
            invoke(args, control=control)
            if output:
                if not shutil.which('afconvert'):
                    raise EngineError('macOS afconvert is required for WAV export')
                invoke(['afconvert', '-f', 'WAVE', '-d', 'LEI16', str(aiff), str(output)], control=control)

    def render_wav(self, text: str, output: Path, settings: SpeechSettings, control: RunControl | None=None) -> None:
        self._say(text, settings, control, output=output)

class Piper(SpeechEngine):
    key = 'piper'
    label = 'Piper neural voices (local, CPU-capable)'

    def available(self) -> bool:
        return piper_binary() is not None or python_piper_available()

    def voices(self) -> list[str]:
        return sorted({*[v.name for v in discover_voices()],
                       *[v.key for v in cached_catalog()]}, key=str.casefold)

    def render_wav(self, text: str, output: Path, settings: SpeechSettings, control: RunControl | None=None) -> None:
        # All render paths (including multi-character, batch and video) use
        # the same on-demand, checksum-verified Piper downloader.
        if settings.model:
            if settings.model.lower().endswith('.onnx'):
                selected = Path(settings.model).expanduser()
            else:
                selected = ensure_piper_voice(settings.model, control=control)
        elif settings.voice and not settings.voice.isdecimal():
            selected = ensure_piper_voice(settings.voice, control=control)
        else:
            voice = get_voice()
            if voice is None:
                raise EngineError('Choose a Piper voice from the Voice list')
            selected = voice.model
        if not selected.is_file():
            raise EngineError(f'Piper model does not exist: {selected}')
        config = Path(str(selected) + '.json')
        if not config.is_file():
            raise EngineError(f'Piper voice configuration is missing: {config.name}')
        config_data, problems = inspect_config(config)
        length_scale = max(0.45, min(1.8, 1.0 / (1.0 + settings.rate * 0.065)))
        binary = piper_binary()
        speaker = settings.speaker_id
        if speaker is None and settings.voice.isdecimal():  # legacy numeric --voice
            speaker = int(settings.voice)
        if speaker is not None:
            if type(speaker) is not int or not 0 <= speaker < len(speaker_list(selected)):
                raise EngineError(f'Piper speaker ID {speaker!r} is unavailable for {selected.name}. '
                                  f'Choose an ID between 0 and {len(speaker_list(selected))-1}.')
        if problems and compatible_cli_config(config_data, problems) is None:
            if python_piper_available():
                render_python_piper(text, selected, config, output, length_scale, speaker)
                return
            raise EngineError(incompatibility_message(selected, problems))
        from ..acceleration import piper_gpu_enabled
        if piper_gpu_enabled() and python_piper_available():
            render_python_piper(text, selected, config, output, length_scale, speaker)
            return
        if not binary:
            if python_piper_available():
                render_python_piper(text, selected, config, output, length_scale, speaker)
                return
            raise EngineError('Piper is not installed. Install its executable or run python -m pip install piper-tts.')
        args = [binary, '--model', str(selected), '--output_file', str(output)]
        with tempfile.TemporaryDirectory(prefix='openmukti-piper-config-') as work:
            compatible = compatible_cli_config(config_data, problems)
            if compatible is not None:
                temporary_config = Path(work) / 'compatible.onnx.json'
                temporary_config.write_text(json.dumps(compatible, ensure_ascii=False), encoding='utf-8')
                args.extend(['--config', str(temporary_config)])
            if speaker is not None:
                args.extend(['--speaker', str(speaker)])
            if settings.rate:
                args.extend(['--length_scale', f'{length_scale:.3f}'])
            try:
                invoke(args, stdin=text.encode('utf-8'), control=control)
            except EngineError as exc:
                if 'not a single codepoint' in str(exc):
                    raise EngineError(incompatibility_message(selected, problems or {'phoneme_id_map':['unsupported phoneme']})) from exc
                raise

    def speak(self, text: str, settings: SpeechSettings, control: RunControl | None=None) -> None:
        with tempfile.TemporaryDirectory(prefix='openmukti-piper-') as work:
            audio = Path(work) / 'speech.wav'
            self.render_wav(text, audio, settings, control)
            play_wav(audio, control)

def play_wav(path: Path, control: RunControl | None=None) -> None:
    if platform.system() == 'Windows':
        powershell = shutil.which('powershell.exe') or shutil.which('powershell')
        if not powershell:
            raise EngineError('Windows PowerShell is unavailable. Export the WAV audio or install Windows PowerShell.')
        resource = importlib.resources.files('openvoice').joinpath('resources/play_wav.ps1')
        with importlib.resources.as_file(resource) as script:
            invoke([powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'RemoteSigned', '-File', str(script), '-WavPath', str(path.resolve())], control=control)
        return
    if shutil.which('afplay'):
        command = ['afplay', str(path)]
    elif shutil.which('aplay'):
        command = ['aplay', '-q', str(path)]
    elif shutil.which('paplay'):
        command = ['paplay', str(path)]
    elif shutil.which('ffplay'):
        command = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'error', str(path)]
    else:
        raise EngineError('No audio player available. Install aplay, paplay or ffplay; or export a WAV file.')
    invoke(command, control=control)
class Flite(SpeechEngine):
    key = 'flite'
    label = 'Flite (offline English via FFmpeg)'
    supports_rate = True
    supports_volume = True

    def available(self):
        from ..fftools import find_binary
        binary = find_binary('ffmpeg')
        if not binary:
            return False
        try:
            return b' flite ' in invoke([binary, '-hide_banner', '-filters'])
        except EngineError:
            return False

    def voices(self):
        return ['kal', 'kal16', 'awb', 'rms', 'slt'] if self.available() else []

    def render_wav(self, text, output, settings, control=None):
        from ..fftools import find_binary
        voice = settings.voice or 'slt'
        if voice not in self.voices():
            raise EngineError(f'Unavailable Flite voice: {voice}')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'speech.txt').write_text(text, encoding='utf-8')
            invoke([find_binary('ffmpeg'), '-nostdin', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', f'flite=textfile=speech.txt:voice={voice}',
                    '-af', f'atempo={_normal_rate(settings.rate)/175},volume={settings.volume/100}',
                    str(output.resolve())], cwd=folder, control=control)

    def speak(self, text, settings, control=None):
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'speech.wav'
            self.render_wav(text, audio, settings, control)
            play_wav(audio, control)


BUILTINS: list[type[SpeechEngine]] = [WindowsSAPI, EspeakNG, MacOSVoice, Piper, Flite]
