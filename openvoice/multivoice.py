from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
from dataclasses import replace
from .audio import combine_wav, convert_wav
from .engines import RunControl, SpeechSettings, get_engine, SpeechEngine
from .service import JobOptions, prepared_speech_units, render_speech_unit
from .fftools import find_binary
from .character_voices import VoiceProject, parse_passages
from .ipa_pronunciation import display_inline_ipa
from .voice_design import design_for_profile, process_character_audio
from .progress import emit, subprogress
from .timeline_tags import has_timeline_tags, parse_timeline
from .timeline_audio import plan_timeline, mix_timeline

AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".ogg",
    ".opus",
    ".aac",
    ".aiff",
    ".wma",
}


def render_multivoice(
    text: str,
    destination: str | Path,
    project: VoiceProject,
    *,
    control: RunControl | None = None,
    progress=None,
    auto_tag: bool = False,
    default_engine: SpeechEngine | None = None,
    default_settings: SpeechSettings | None = None,
    speech_options: JobOptions = JobOptions(),
    status=None,
) -> Path:
    emit(status, 0, "Preparing character narration")
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio export format")
    if has_timeline_tags(text):
        return _render_timed_multivoice(
            text, destination, project, control=control, progress=progress,
            default_engine=default_engine, default_settings=default_settings,
            speech_options=speech_options, status=status,
        )
    passage_list = parse_passages(text, project.profiles, auto_tag=auto_tag, speaker_rules=project.speaker_rules)
    if not passage_list:
        raise ValueError("No spoken passages found")
    profiles = {p.name.casefold(): p for p in project.profiles}
    narrator = profiles.get("narrator")
    if narrator is None:
        raise ValueError("Narrator voice profile is required")
    ipa_files = tuple(
        dict.fromkeys([*speech_options.ipa_dictionaries, *project.pronunciation_files])
    )
    sections = [
        (p, part)
        for p in passage_list
        for part in prepared_speech_units(
            p.text,
            JobOptions(
                chunk_size=speech_options.chunk_size,
                pause_ms=speech_options.pause_ms,
                repair_ocr=speech_options.repair_ocr,
                dictionaries=speech_options.dictionaries,
                operations=speech_options.operations,
                ipa_dictionaries=ipa_files,
                language=p.language,
            ),
            language=next(
                (
                    x.language
                    for x in project.profiles
                    if x.name.casefold() == p.speaker.casefold()
                    and x.language not in ("auto", "und")
                ),
                p.language,
            ),
        )
    ]
    if not sections:
        raise ValueError("No text after processing")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="openmukti-multivoice-") as temporary:
        work = Path(temporary)
        from .render_cache import renderer_for
        render_unit = renderer_for(speech_options, render_speech_unit)
        files = []
        ffmpeg = find_binary("ffmpeg")
        for index, (passage, segment) in enumerate(sections, 1):
            emit(
                status,
                0.02 + 0.78 * (index - 1) / len(sections),
                f"Generating {passage.speaker} · passage {index} of {len(sections)}",
            )
            if control:
                control.check()
            profile = profiles.get(passage.speaker.casefold(), narrator)
            base = default_settings or SpeechSettings()
            selected = profile.voice
            if profile.engine != 'auto':
                engine = get_engine(profile.engine, profile.model)
                engine_key = engine.key
            elif selected:
                engine = get_engine('piper')  # existing saved projects retain Piper behavior
                engine_key = 'piper'
            else:
                engine = default_engine or get_engine('auto')
                engine_key = engine.key
            original = work / f"{index:06d}-raw.wav"
            model_path = profile.model or (selected if engine_key == 'piper' and selected.lower().endswith('.onnx') else (base.model if not selected and profile.engine == 'auto' else ''))
            voice_name = selected if engine_key != 'piper' or not model_path else '' 
            design = design_for_profile(profile)
            gain = (
                max(0, min(1, base.volume * profile.volume / 10000))
                if not getattr(engine, "supports_volume", False)
                else 1.0
            )
            if base.pitch and not getattr(engine, "supports_pitch", False):
                design = replace(
                    design,
                    semitones=round(
                        max(-9, min(9, design.semitones + base.pitch * 0.55)), 2
                    ),
                )
            if (
                not selected
                and not base.voice
                and engine_key == "espeak"
                and profile.language not in ("", "auto", "und")
            ):
                voice_name = profile.language.replace("_", "-").lower()
            adjusted_rate = max(
                -10, min(10, base.rate + profile.rate + design.speed_adjust)
            )
            render_unit(
                segment,
                original,
                engine,
                SpeechSettings(
                    voice=voice_name or (base.voice if not selected and profile.engine == "auto" else ""),
                    model=model_path,
                    speaker_id=(profile.speaker_id if engine_key == "piper" and selected else base.speaker_id),
                    rate=adjusted_rate,
                    pitch=base.pitch,
                    volume=max(0, min(100, round(base.volume * profile.volume / 100))),
                    language=profile.language if profile.language not in ('auto','und','') else base.language,
                ),
                control,
            )
            if not original.is_file() or original.stat().st_size < 44:
                raise RuntimeError(f"No speech output for passage {index}")
            normalized = work / f"{index:06d}.wav"
            emit(
                status,
                0.02 + 0.78 * (index - 0.3) / len(sections),
                f"Processing {passage.speaker} voice · passage {index} of {len(sections)}",
            )
            if ffmpeg:
                process_character_audio(
                    original, normalized, design, control=control, gain=gain
                )
            else:
                if (
                    design.semitones
                    or design.bass_db
                    or design.treble_db
                    or design.energy_db
                    or design.compression
                    or gain != 1
                ):
                    raise RuntimeError(
                        "FFmpeg is required to apply character voice age, gender and personality effects."
                    )
                shutil.copy2(original, normalized)
            files.append(normalized)
            if progress:
                progress(index, len(sections), passage.speaker)
            emit(
                status,
                0.02 + 0.78 * index / len(sections),
                f"Completed {index} of {len(sections)} voice passages",
                index / len(sections),
            )
        joined = work / "narration.wav"
        emit(status, 0.80, "Merging character voices")
        try:
            combine_wav(
                files,
                joined,
                pause_ms=speech_options.pause_ms,
                control=control,
                progress=(
                    lambda n, t: emit(
                        status,
                        0.80 + 0.08 * n / t,
                        f"Merging voice passage {n} of {t}",
                        n / t,
                    )
                )
                if status
                else None,
            )
        except Exception as exc:
            if not ffmpeg:
                raise RuntimeError(
                    "Mixed voices use different WAV formats; FFmpeg is required to normalize them"
                ) from exc
            raise
        converted = work / ("narration" + destination.suffix.lower())
        if destination.suffix.lower() == ".wav":
            converted = joined
        else:
            emit(status, 0.88, "Encoding character narration")
            convert_wav(
                joined,
                converted,
                control=control,
                progress=(
                    lambda value: emit(
                        status,
                        0.88 + 0.10 * value,
                        "Encoding character narration",
                        value,
                    )
                )
                if status
                else None,
            )
        emit(status, 0.98, "Saving character narration")
        staged = destination.with_name("." + destination.name + ".partial")
        try:
            shutil.copy2(converted, staged)
            if control:
                control.check()
            os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)
    emit(status, 1, f"Audio saved: {destination.name}", 1)
    return destination


def _render_timed_multivoice(text, destination, project, *, control=None,
                             progress=None, default_engine=None, default_settings=None,
                             speech_options=JobOptions(), status=None):
    """Render passages separately and mix them on a millisecond audio timeline.

    The untagged rendering path is intentionally reused: engine selection,
    character voice design, IPA dictionaries, and Piper handling stay identical.
    """
    scene = parse_timeline(text, [p.name for p in project.profiles] +
                           [a for p in project.profiles for a in p.aliases])
    if not scene.passages:
        raise ValueError('Timed script has no spoken passages')
    destination = Path(destination).expanduser().resolve()
    if destination.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError('Unsupported audio export format')
    with tempfile.TemporaryDirectory(prefix='openmukti-timeline-') as temporary:
        root = Path(temporary)
        sounds = []
        for number, passage in enumerate(scene.passages, 1):
            if control:
                control.check()
            source = root / f'voice-{number:05d}.wav'
            render_multivoice(
                f'[{passage.speaker}] {passage.text}', source, project,
                control=control, default_engine=default_engine,
                default_settings=default_settings,
                speech_options=replace(speech_options, pause_ms=0),
                status=subprogress(status, (number - 1) * .84 / len(scene.passages),
                                   number * .84 / len(scene.passages)),
            )
            sounds.append(source)
            if progress:
                progress(number, len(scene.passages), passage.speaker)
        clips, length_ms = plan_timeline(scene, sounds, project.sound_files,
                                         default_pause_ms=speech_options.pause_ms)
        mixed = mix_timeline(clips, root / 'mixed.wav', length_ms, control=control)
        staged = root / ('output' + destination.suffix.lower())
        if destination.suffix.lower() == '.wav':
            staged = mixed
        else:
            convert_wav(mixed, staged, control=control,
                        progress=lambda ratio: emit(status, .92 + .07 * ratio,
                                                    'Encoding timed narration'))
        destination.parent.mkdir(parents=True, exist_ok=True)
        final = destination.with_name('.' + destination.name + '.partial')
        try:
            shutil.copy2(staged, final)
            if control:
                control.check()
            os.replace(final, destination)
        finally:
            final.unlink(missing_ok=True)
    emit(status, 1, f'Timed narration saved: {destination.name}', 1)
    return destination

def render_multivoice_video(
    text: str,
    images: list[str | Path],
    destination: str | Path,
    project: VoiceProject,
    *,
    video_options=None,
    control=None,
    progress=None,
    auto_tag: bool = False,
    default_engine=None,
    default_settings=None,
    speech_options: JobOptions = JobOptions(),
    status=None,
):
    from .video import VideoOptions, render_video

    with tempfile.TemporaryDirectory(prefix="openmukti-voice-video-") as work:
        narration = render_multivoice(
            text,
            Path(work) / "audio.wav",
            project,
            control=control,
            progress=progress,
            auto_tag=auto_tag,
            default_engine=default_engine,
            default_settings=default_settings,
            speech_options=speech_options,
            status=subprogress(status, 0, 0.55),
        )
        return render_video(
            images,
            destination,
            audio=narration,
            text="\n".join(display_inline_ipa(p.text) for p in
                (parse_timeline(text, [q.name for q in project.profiles]).passages
                 if has_timeline_tags(text)
                 else parse_passages(text, project.profiles, auto_tag=auto_tag, speaker_rules=project.speaker_rules))),
            video_options=video_options or VideoOptions(),
            control=control,
            status=subprogress(status, 0.55, 1),
        )
