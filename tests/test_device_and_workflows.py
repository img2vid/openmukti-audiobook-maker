import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

from openvoice.acceleration import load_voice
from openvoice.ocr import OCRSettings, OCRError
from openvoice.project_archive import ProjectData, project_template, save_project, load_project
from openvoice.release_tools import compare_recordings, package_subtitles


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_directml_and_cpu_retry(self):
        ort, voice = Mock(), Mock()
        ort.get_available_providers.return_value = ['DmlExecutionProvider', 'CPUExecutionProvider']
        session = ort.InferenceSession.return_value
        session.get_providers.return_value = ort.get_available_providers.return_value
        session.run.side_effect = RuntimeError('unavailable operator')
        loaded, fallback = Mock(), Mock()
        voice.load.side_effect = (loaded, fallback)
        fallback.session.run.return_value = [17]
        with patch.dict(os.environ, {}, clear=True), patch.dict(sys.modules, onnxruntime=ort):
            self.assertIs(load_voice(voice, 'voice', 'config'), loaded)
            self.assertFalse(ort.SessionOptions.return_value.enable_mem_pattern)
            with self.assertWarns(UserWarning):
                self.assertEqual(loaded.session.run(None, {}), [17])
            self.assertEqual(loaded.session.run(None, {}), [17])
        self.assertEqual(session.run.call_count, 1)

    def test_forced_cpu(self):
        ort, voice = Mock(), Mock()
        with patch.dict(os.environ, OPENMUKTI_GPU_MODE='cpu'), patch.dict(sys.modules, onnxruntime=ort):
            load_voice(voice, 'voice', 'config')
        ort.get_available_providers.assert_not_called()
        voice.load.assert_called_once_with('voice', config_path='config', use_cuda=False)

    def test_template_excludes_manuscript(self):
        original = ProjectData(text='private', settings={'rate': 2, 'production': {'notes': 'private'}},
                               video_settings={'fps': 24}, book_settings={'format': 'mp3'})
        original.voice_project.script = 'private'
        file = save_project(self.root / 'template.oamtemplate', project_template(original))
        restored = load_project(file, self.root / 'resources')
        self.assertEqual(('', '', {'rate': 2}, {'fps': 24}, {'format': 'mp3'}),
                         (restored.text, restored.voice_project.script, restored.settings,
                          restored.video_settings, restored.book_settings))
        self.assertEqual(original.voice_project.script, 'private')

    def test_multilingual_subtitles(self):
        source = self.root / 'sub.srt'
        source.write_text('1\n00:00:00,000 --> 00:00:00,500\nবই', encoding='utf-8')
        target = self.root / 'tracks.zip'
        package_subtitles(target, ['bn=' + str(source), 'en-IN=' + str(source)])
        with ZipFile(target) as archive:
            self.assertEqual(archive.read('captions.bn.srt'), source.read_bytes())
            self.assertIn('captions.en-in.srt', archive.namelist())
        before = target.read_bytes()
        with self.assertRaises(ValueError):
            package_subtitles(target, ['en=' + str(source), 'EN=' + str(source)])
        self.assertEqual(before, target.read_bytes())

    def test_wav_regression(self):
        def wav(name, values):
            path = self.root / name
            with wave.open(str(path), 'wb') as f:
                f.setparams((1, 1, 8000, 0, 'NONE', ''))
                f.writeframes(bytes(values))
            return path
        a, b = wav('reference.wav', [128, 127]), wav('render.wav', [129, 127])
        self.assertTrue(compare_recordings(a, a, 0)['passed'])
        self.assertFalse(compare_recordings(a, b, 0)['passed'])
        self.assertTrue(compare_recordings(a, b, .01)['passed'])

    def test_region_conflicts(self):
        with self.assertRaises(OCRError):
            OCRSettings(region=(0,0,2,2), split_spreads=True).validate()
