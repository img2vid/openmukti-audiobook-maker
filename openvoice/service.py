from __future__ import annotations
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from .audio import combine_wav, convert_wav
from .engines import RunControl, SpeechEngine, SpeechSettings
from .processing import apply_replacements, load_replacements, normalize_text, split_text
from .texttools import transform
from .progress import emit
from .ipa_pronunciation import load_pronunciations, segment_pronunciations, PronunciationSegment, PronunciationError, render_ipa_wav, parse_inline_ipa

@dataclass(frozen=True)
class JobOptions:
    chunk_size: int = 450
    pause_ms: int = 80
    repair_ocr: bool = False
    dictionaries: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()
    ipa_dictionaries: tuple[str, ...] = ()
    language: str = 'und'
    cache_dir: str = ''
    refresh_cache: bool = False

def prepared_chunks(text: str, options: JobOptions) -> list[str]:
    text = normalize_text(text, repair_ocr=options.repair_ocr)
    if options.dictionaries:
        text = apply_replacements(text, load_replacements(options.dictionaries))
    if options.operations:
        text = transform(text, options.operations)
    return split_text(text, max_chars=options.chunk_size)

def prepared_speech_units(text: str, options: JobOptions, language: str = '') -> list[PronunciationSegment]:
    rules = load_pronunciations(options.ipa_dictionaries) if options.ipa_dictionaries else []
    units: list[PronunciationSegment] = []
    for part in parse_inline_ipa(text):
        if part.ipa:
            units.append(part)
            continue
        content = normalize_text(part.text, repair_ocr=options.repair_ocr)
        if options.dictionaries:
            content = apply_replacements(content, load_replacements(options.dictionaries))
        if options.operations:
            content = transform(content, options.operations)
        if not content.strip():
            continue
        lang = language or options.language
        if rules and lang in ('', 'auto', 'und'):
            from .character_voices import detect_language
            lang, _ = detect_language(content)
        for segment in segment_pronunciations(content, rules, lang):
            if segment.ipa:
                units.append(segment)
            else:
                units.extend(PronunciationSegment(chunk) for chunk in split_text(segment.text, max_chars=options.chunk_size))
    return units


def render_speech_unit(unit: PronunciationSegment, output: Path, engine: SpeechEngine, settings: SpeechSettings, control=None) -> None:
    if not unit.ipa:
        engine.render_wav(unit.text,output,settings,control)
    elif getattr(engine,'key','')=='piper':
        try:
            render_ipa_wav(unit.ipa,output,settings,control)
        except PronunciationError:
            if not unit.spoken:
                raise
            engine.render_wav(unit.spoken,output,settings,control)
    elif unit.spoken:
        engine.render_wav(unit.spoken,output,settings,control)
    else:
        raise PronunciationError(f'This voice engine does not support direct IPA. Use Piper Python with a compatible ONNX voice or add a spoken fallback for {unit.text!r}.')


def speak_text(text: str, engine: SpeechEngine, settings: SpeechSettings, options: JobOptions=JobOptions(), control: RunControl | None=None, progress: Callable[[int, int], None] | None=None, *, status=None) -> int:
    emit(status, 0, 'Preparing speech')
    units = prepared_speech_units(text, options)
    if not units:
        raise ValueError('There is no text to speak')
    for index, unit in enumerate(units, 1):
        emit(status, (index - 1) / len(units), f'Speaking chunk {index} of {len(units)}')
        if control:
            control.check()
        if unit.ipa:
            from .engines.builtin import play_wav
            with tempfile.TemporaryDirectory(prefix='openmukti-ipa-preview-') as work:
                path = Path(work)/'pronunciation.wav'
                render_speech_unit(unit,path,engine,settings,control)
                play_wav(path,control)
        else:
            engine.speak(unit.text,settings,control)
        if progress:
            progress(index,len(units))
        emit(status, index / len(units), f'Spoken {index} of {len(units)} chunks', index / len(units))
    return len(units)

def render_text(text: str, output: str | Path, engine: SpeechEngine, settings: SpeechSettings, options: JobOptions=JobOptions(), control: RunControl | None=None, progress: Callable[[int, int], None] | None=None, *, status=None) -> Path:
    emit(status, 0, 'Preparing narration')
    output = Path(output).expanduser()
    ext = output.suffix.lower()
    if ext not in {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.opus', '.aac', '.aiff', '.wma'}:
        raise ValueError('Supported outputs: wav, mp3, flac, ogg, m4a, opus, aac, aiff and wma')
    chunks = prepared_speech_units(text, options)
    if not chunks:
        raise ValueError('There is no text to render')
    if options.pause_ms < 0 or options.pause_ms > 15000:
        raise ValueError('Pause between chunks must be between 0 and 15000 ms')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='openvoice-render-') as work:
        temp = Path(work)
        from .render_cache import renderer_for
        render_unit = renderer_for(options, render_speech_unit)
        files = []
        for index, part in enumerate(chunks, 1):
            emit(status, .02 + .78 * (index - 1) / len(chunks), f'Generating speech · chunk {index} of {len(chunks)}')
            if control:
                control.check()
            chunk_file = temp / f'part-{index:06d}.wav'
            render_unit(part, chunk_file, engine, settings, control)
            if not chunk_file.is_file() or chunk_file.stat().st_size < 44:
                raise RuntimeError(f'Speech engine did not produce a WAV file for chunk {index}')
            files.append(chunk_file)
            if progress:
                progress(index, len(chunks))
            emit(status, .02 + .78 * index / len(chunks), f'Generated {index} of {len(chunks)} speech chunks', index / len(chunks))
        combined = temp / 'combined.wav'
        emit(status, .80, 'Merging narration chunks')
        combine_wav(files, combined, pause_ms=options.pause_ms, control=control,
                    progress=(lambda n,t: emit(status, .80 + .08*n/t, f'Merging audio · part {n} of {t}', n/t)) if status else None)
        if control:
            control.check()
        finalized = combined
        if ext != '.wav':
            finalized = temp / f'converted{ext}'
            emit(status, .88, f'Encoding {ext[1:].upper()} audio')
            convert_wav(combined, finalized, control=control,
                        progress=(lambda value: emit(status, .88 + .10*value, f'Encoding {ext[1:].upper()} audio', value)) if status else None)
        emit(status, .98, 'Saving final audio file')
        fd, staging_path = tempfile.mkstemp(prefix='.openvoice-', suffix=ext, dir=str(output.parent))
        os.close(fd)
        try:
            import shutil
            shutil.copyfile(finalized, staging_path)
            if control:
                control.check()
            os.replace(staging_path, output)
        finally:
            if os.path.exists(staging_path):
                os.unlink(staging_path)
    emit(status, 1, f'Audio saved: {output.name}', 1)
    return output
