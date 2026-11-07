"""Exercise real FFmpeg audio and the engine/profile integration without model downloads."""

import array
import io
import json
import math
import shutil
import tempfile
import unittest
import wave
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from openvoice.character_voices import CharacterProfile, VoiceProject, parse_passages
from openvoice.engines import SpeechEngine, SpeechSettings
from openvoice.multivoice import render_multivoice
from openvoice.service import JobOptions
from openvoice.voice_design import design_for_profile


class ToneEngine(SpeechEngine):
    key = "piper"

    def __init__(self, native_volume=False):
        self.supports_volume = native_volume
        self.calls = []

    def render_wav(self, text, output, settings, control=None):
        self.calls.append((text, settings))
        gain = settings.volume / 100 if self.supports_volume else 1
        samples = array.array(
            "h",
            (
                round(10000 * gain * math.sin(2 * math.pi * 440 * i / 24000))
                for i in range(12000)
            ),
        )
        with wave.open(str(output), "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(samples.tobytes())


def metrics(path):
    with wave.open(str(path)) as wav:
        data = array.array("h", wav.readframes(wav.getnframes()))
        duration = len(data) / wav.getframerate()
    rms = math.sqrt(sum(x * x for x in data) / max(1, len(data)))
    rising = sum(a <= 0 < b for a, b in zip(data, data[1:]))
    return rms, rising / duration


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg required")
class AudioProfileTests(unittest.TestCase):
    def render(self, folder, name, p, base=SpeechSettings(), native=False):
        engine = ToneEngine(native)
        out = Path(folder) / (name + ".wav")
        project = VoiceProject([CharacterProfile("Narrator", design_strength=0), p])
        with patch("openvoice.multivoice.get_engine", return_value=engine):
            render_multivoice(
                "[Alice] Hello.",
                out,
                project,
                default_settings=base,
                speech_options=JobOptions(pause_ms=0),
            )
        return metrics(out), engine.calls

    def test_piper_character_and_master_volume_are_applied_to_actual_audio(self):
        with tempfile.TemporaryDirectory() as d:
            baseline, _ = self.render(
                d, "base", CharacterProfile("Alice", voice="fixture", design_strength=0)
            )
            half, _ = self.render(
                d,
                "half",
                CharacterProfile(
                    "Alice", voice="fixture", volume=50, design_strength=0
                ),
            )
            quarter, _ = self.render(
                d,
                "quarter",
                CharacterProfile(
                    "Alice", voice="fixture", volume=50, design_strength=0
                ),
                SpeechSettings(volume=50),
            )
            silent, _ = self.render(
                d,
                "silent",
                CharacterProfile("Alice", voice="fixture", volume=0, design_strength=0),
            )
            self.assertAlmostEqual(half[0] / baseline[0], 0.5, delta=0.01)
            self.assertAlmostEqual(quarter[0] / baseline[0], 0.25, delta=0.01)
            self.assertEqual(silent[0], 0)

    def test_native_engine_volume_is_not_applied_twice(self):
        with tempfile.TemporaryDirectory() as d:
            baseline, _ = self.render(
                d,
                "base",
                CharacterProfile("Alice", voice="fixture", design_strength=0),
                native=True,
            )
            half, _ = self.render(
                d,
                "half",
                CharacterProfile(
                    "Alice", voice="fixture", volume=50, design_strength=0
                ),
                native=True,
            )
            self.assertAlmostEqual(half[0] / baseline[0], 0.5, delta=0.01)

    def test_pitch_affects_real_waveform_and_rate_reaches_engine(self):
        p = CharacterProfile(
            "Alice",
            voice="fixture",
            pitch=6,
            rate=2,
            gender="Female",
            age="Teen",
            characteristics="gentle",
            design_strength=80,
        )
        with tempfile.TemporaryDirectory() as d:
            (_, frequency), calls = self.render(d, "pitched", p, SpeechSettings(rate=1))
            self.assertGreater(frequency, 500)
            expected = max(
                -10, min(10, 1 + p.rate + design_for_profile(p).speed_adjust)
            )
            self.assertEqual(calls[0][1].rate, expected)

    def test_different_characters_can_use_different_speakers_from_one_model(self):
        project = VoiceProject([
            CharacterProfile("Narrator", voice="shared-model", speaker_id=0, design_strength=0),
            CharacterProfile("Alice", voice="shared-model", speaker_id=2, design_strength=0),
            CharacterProfile("Bob", voice="shared-model", speaker_id=3, design_strength=0),
        ])
        with tempfile.TemporaryDirectory() as d:
            engine = ToneEngine()
            with patch("openvoice.multivoice.get_engine", return_value=engine):
                render_multivoice(
                    "[Alice] Hello. [Bob] Goodbye.", Path(d) / "speakers.wav", project,
                    speech_options=JobOptions(pause_ms=0),
                )
            self.assertEqual([setting.speaker_id for _, setting in engine.calls], [2, 3])
            self.assertTrue(all(setting.voice == 'shared-model' for _, setting in engine.calls))

    def test_unconfigured_character_uses_master_piper_speaker(self):
        project = VoiceProject([
            CharacterProfile("Narrator", design_strength=0),
            CharacterProfile("Alice", design_strength=0),
        ])
        with tempfile.TemporaryDirectory() as d:
            engine = ToneEngine()
            with patch("openvoice.multivoice.get_engine", return_value=engine):
                render_multivoice(
                    "[Alice] Hello.", Path(d) / "master.wav", project,
                    default_settings=SpeechSettings(model="shared.onnx", speaker_id=5),
                    speech_options=JobOptions(pause_ms=0),
                )
            self.assertEqual(engine.calls[0][1].speaker_id, 5)
            self.assertEqual(engine.calls[0][1].model, 'shared.onnx')

    def test_global_pitch_works_for_engine_without_native_pitch(self):
        with tempfile.TemporaryDirectory() as d:
            (_, frequency), _ = self.render(
                d,
                "masterpitch",
                CharacterProfile("Alice", voice="fixture", design_strength=0),
                SpeechSettings(pitch=6),
            )
            self.assertGreater(frequency, 490)

    def test_system_language_selection_preserves_explicit_master_voice(self):
        p = CharacterProfile("Alice", language="fr", design_strength=0)
        project = VoiceProject([CharacterProfile("Narrator", design_strength=0), p])
        with tempfile.TemporaryDirectory() as d:
            engine = ToneEngine()
            engine.key = "espeak"
            render_multivoice(
                "[Alice] Bonjour.",
                Path(d) / "fr.wav",
                project,
                default_engine=engine,
                speech_options=JobOptions(pause_ms=0),
            )
            self.assertEqual(engine.calls[0][1].voice, "fr")
            render_multivoice(
                "[Alice] Bonjour.",
                Path(d) / "custom.wav",
                project,
                default_engine=engine,
                default_settings=SpeechSettings(voice="custom-french-voice"),
                speech_options=JobOptions(pause_ms=0),
            )
            self.assertEqual(engine.calls[-1][1].voice, "custom-french-voice")

    def test_unconfigured_voices_do_not_speak_control_tags(self):
        project = [CharacterProfile("Narrator"), CharacterProfile("Alice")]
        passages = parse_passages(
            'Alice said, "Hello." Bob said, "Welcome."', project, auto_tag=True
        )
        self.assertFalse(any("[" in p.text for p in passages))
        self.assertTrue(
            any(p.speaker == "Alice" and "Hello" in p.text for p in passages)
        )
        self.assertTrue(
            any(p.speaker == "Narrator" and "Welcome" in p.text for p in passages)
        )

    def test_aliases_drive_untagged_export_after_identity_revelation(self):
        profiles = [CharacterProfile("Narrator"), CharacterProfile("The old man")]
        parts = parse_passages(
            '"Hello," the old man said. The old man was named Elias.',
            profiles,
            auto_tag=True,
        )
        self.assertTrue(
            any(p.speaker == "The old man" and "Hello" in p.text for p in parts)
        )


class CommandAndArchiveTests(unittest.TestCase):
    def test_cli_infers_and_exports_review_report(self):
        from openvoice.cli import main

        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "voices.json"
            report = Path(d) / "analysis.json"
            names = Path(d) / "names.txt"
            names.write_text("xyzzzy\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                result = main(
                    [
                        "character-profiles",
                        "-t",
                        'xyzzzy said, "Hello."',
                        "--names",
                        str(names),
                        "--report",
                        str(report),
                        "-w",
                        str(out),
                    ]
                )
            self.assertEqual(result, 0)
            self.assertEqual(VoiceProject.load(out).profiles[1].name, "xyzzzy")
            self.assertEqual(
                json.loads(report.read_text())["quotations"][0]["speaker"], "xyzzzy"
            )

    def test_archived_model_automatic_value_tracks_relocated_model(self):
        from openvoice.project_archive import ProjectData, save_project, load_project

        with tempfile.TemporaryDirectory() as d:
            model = Path(d) / "fixture.onnx"
            model.write_bytes(b"fixture")
            Path(str(model) + ".json").write_text("{}")
            profile = CharacterProfile(
                "Alice",
                voice=str(model),
                auto_values={"voice": str(model)},
                inference={"voice": {"suggested": str(model)}},
            )
            data = ProjectData(
                voice_project=VoiceProject([CharacterProfile("Narrator"), profile])
            )
            archive = Path(d) / "project.oamproj"
            save_project(archive, data)
            restored = load_project(
                archive, Path(d) / "restored"
            ).voice_project.profiles[1]
            self.assertEqual(restored.voice, restored.auto_values["voice"])
            self.assertEqual(restored.voice, restored.inference["voice"]["suggested"])
            self.assertNotEqual(restored.voice, str(model))


if __name__ == "__main__":
    unittest.main()
