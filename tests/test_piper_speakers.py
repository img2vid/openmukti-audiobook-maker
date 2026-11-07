"""Regression coverage for local Piper models containing multiple speakers."""
import json
import io
from contextlib import redirect_stdout
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice.character_voices import CharacterProfile, VoiceProject
from openvoice.engines.base import EngineError, SpeechSettings
from openvoice.engines.builtin import Piper
from openvoice.piper_models import speaker_list, speaker_id_from_label, speaker_label
from openvoice.project_archive import ProjectData, load_project, save_project


class PiperSpeakerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.model = self.root / 'en_US-multi.onnx'
        self.model.write_bytes(b'fake-onnx-model')

    def config(self, **kwargs):
        config = {'num_speakers': 4, 'speaker_id_map': {'zero': 0, 'Alice': 2, 'Bob': 3},
                  'phoneme_id_map': {}, 'phoneme_map': {}}
        config.update(kwargs)
        Path(str(self.model) + '.json').write_text(json.dumps(config), encoding='utf-8')

    def test_discovers_named_and_unnamed_speakers_in_id_order(self):
        self.config()
        self.assertEqual([x.id for x in speaker_list(self.model)], [0, 1, 2, 3])
        self.assertEqual([x.label for x in speaker_list(self.model)],
                         ['Speaker 0 — zero', 'Speaker 1', 'Speaker 2 — Alice', 'Speaker 3 — Bob'])
        self.assertEqual(speaker_label(2, self.model), 'Speaker 2 — Alice')
        self.assertEqual(speaker_id_from_label('Speaker 3 — Bob'), 3)
        self.assertEqual(speaker_id_from_label('2'), 2)
        with self.assertRaises(ValueError):
            speaker_id_from_label('Alice')

    def test_installed_name_and_manual_model_path(self):
        self.config()
        with patch('openvoice.piper_models.search_directories', return_value=[self.root]):
            self.assertEqual(speaker_list('en_US-multi'), speaker_list(self.model))

    def test_single_speaker_default_and_empty_map(self):
        self.config(num_speakers=1, speaker_id_map={})
        self.assertEqual([x.label for x in speaker_list(self.model)], ['Speaker 0'])
        self.assertEqual([x.label for x in speaker_list()], ['Speaker 0'])

    def test_invalid_and_missing_metadata_is_reported(self):
        for data in ({'num_speakers': 0}, {'num_speakers': '4'},
                     {'num_speakers': 3, 'speaker_id_map': []}):
            Path(str(self.model) + '.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                speaker_list(self.model)
        Path(str(self.model) + '.json').unlink()
        with self.assertRaisesRegex(ValueError, 'speaker metadata'):
            speaker_list(self.model)

    def test_cli_can_list_every_speaker_without_loading_onnx(self):
        from openvoice.cli import main, make_parser
        self.config()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(['voices', '--speakers', '--model', str(self.model), '--json']), 0)
        found = json.loads(output.getvalue())
        self.assertEqual([sp['id'] for sp in found[str(self.model)]], [0, 1, 2, 3])
        self.assertEqual(found[str(self.model)][2]['name'], 'Alice')
        parsed = make_parser().parse_args(['render', '--engine', 'piper', '--model', str(self.model),
                                           '--speaker-id', '3', '-t', 'Hello', '-w', 'out.wav'])
        self.assertEqual(parsed.speaker_id, 3)

    def test_piper_cli_receives_selected_speaker(self):
        self.config()
        commands = []
        def mocked_invoke(args, **kwargs):
            commands.append(list(args))
            return b''
        with patch('openvoice.engines.builtin.piper_binary', return_value='/fake/piper'), \
             patch('openvoice.engines.builtin.invoke', side_effect=mocked_invoke):
            Piper().render_wav('Hello', self.root / 'output.wav',
                               SpeechSettings(model=str(self.model), speaker_id=3))
            self.assertEqual(commands[-1][commands[-1].index('--speaker') + 1], '3')
            with self.assertRaisesRegex(EngineError, 'unavailable'):
                Piper().render_wav('Hello', self.root / 'output.wav',
                                   SpeechSettings(model=str(self.model), speaker_id=4))
            with self.assertRaisesRegex(EngineError, 'unavailable'):
                Piper().render_wav('Hello', self.root / 'output.wav',
                                   SpeechSettings(model=str(self.model), speaker_id=-1))

    def test_python_backend_receives_speaker_id(self):
        self.config()
        calls = []
        with patch('openvoice.engines.builtin.piper_binary', return_value=None), \
             patch('openvoice.engines.builtin.python_piper_available', return_value=True), \
             patch('openvoice.engines.builtin.render_python_piper', side_effect=lambda *a: calls.append(a)):
            Piper().render_wav('Hello', self.root / 'output.wav',
                               SpeechSettings(model=str(self.model), speaker_id=2))
        self.assertEqual(calls[0][-1], 2)

    def test_char_project_and_portable_project_preserve_speaker(self):
        self.config()
        profiles = VoiceProject([CharacterProfile('Narrator', voice=str(self.model), speaker_id=3),
                                 CharacterProfile('Alice', voice=str(self.model), speaker_id=2)])
        self.assertEqual(profiles.profiles[1].speaker_id, 2)
        voice_path = self.root / 'voices.json'
        profiles.save(voice_path)
        self.assertEqual(VoiceProject.load(voice_path).profiles[0].speaker_id, 3)
        portable = self.root / 'archive.oamproj'
        save_project(portable, ProjectData(text='Hello',
                     settings={'engine': 'piper', 'model': str(self.model), 'speaker_id': 2},
                     voice_project=profiles))
        restored = load_project(portable, self.root / 'restored')
        self.assertEqual([p.speaker_id for p in restored.voice_project.profiles], [3, 2])
        self.assertEqual(restored.settings['speaker_id'], 2)

    def test_backward_compatible_character_profiles(self):
        self.assertEqual(CharacterProfile('Old Character').speaker_id, 0)
        for invalid in (-1, True, 3.8, 'two'):
            with self.assertRaises(ValueError):
                CharacterProfile('Bad', speaker_id=invalid)


if __name__ == '__main__':
    unittest.main()
