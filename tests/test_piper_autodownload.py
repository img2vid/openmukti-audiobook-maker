"""Piper catalog entries remain selectable before download and install once on use."""
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice import voice_catalog as vc
from openvoice.engines.builtin import Piper
from openvoice.engines.base import SpeechSettings
from openvoice.engines import get_engine


class PiperOnDemandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.voices = self.base / 'voices'
        self.voices.mkdir()
        self.cache = self.base / 'catalog.json'
        self.key = 'en_US-test-medium'
        self.model = b'pretend-onnx'
        self.config = json.dumps({'num_speakers': 2,
                                  'speaker_id_map': {'Reader': 0, 'Guest': 1},
                                  'phoneme_id_map': {}, 'phoneme_map': {}}).encode()
        self.cache.write_text(json.dumps({self.key: {
            'language': {'code': 'en_US', 'name_english': 'English', 'country_english': 'United States'},
            'quality': 'medium', 'num_speakers': 2,
            'files': {
                'en/test.onnx': {'size_bytes': len(self.model), 'md5_digest': hashlib.md5(self.model).hexdigest()},
                'en/test.onnx.json': {'size_bytes': len(self.config), 'md5_digest': hashlib.md5(self.config).hexdigest()},
            }
        }}), encoding='utf-8')
        self.patches = [patch('openvoice.voice_catalog.catalog_cache', return_value=self.cache),
                        patch('openvoice.voice_catalog.voice_directory', return_value=self.voices),
                        patch('openvoice.piper_models.search_directories', return_value=[self.voices])]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def install_fake_model(self, v):
        destination = self.voices / (v.key + '.onnx')
        destination.write_bytes(self.model)
        Path(str(destination) + '.json').write_bytes(self.config)
        return destination

    def test_catalog_voice_visible_before_installation_without_network(self):
        self.assertFalse(list(self.voices.glob('*.onnx')))
        with patch('openvoice.voice_catalog.fetch_catalog', side_effect=AssertionError('Unexpected network')):
            self.assertEqual(vc.catalog_voice(self.key).key, self.key)
            self.assertIn(self.key, Piper().voices())
        self.assertFalse(list(self.voices.glob('*.onnx')))

    def test_downloads_on_demand_only_once_and_reads_all_speakers(self):
        calls = []
        def download(v):
            calls.append(v.key)
            return self.install_fake_model(v)
        with patch.object(vc, 'download_voice', side_effect=download):
            path = vc.ensure_piper_voice(self.key)
            self.assertEqual(path, vc.ensure_piper_voice(self.key))
        self.assertEqual(calls, [self.key])
        from openvoice.piper_models import speaker_list
        self.assertEqual([x.label for x in speaker_list(self.key)],
                         ['Speaker 0 — Reader', 'Speaker 1 — Guest'])

    def test_concurrent_requests_download_once(self):
        requests = []
        downloaded = []
        def download(v):
            downloaded.append(v.key)
            return self.install_fake_model(v)
        with patch.object(vc, 'download_voice', side_effect=download):
            threads = [threading.Thread(target=lambda: requests.append(vc.ensure_piper_voice(self.key))) for _ in range(8)]
            for t in threads: t.start()
            for t in threads: t.join()
        self.assertEqual(downloaded, [self.key])
        self.assertEqual(requests, [self.voices / (self.key + '.onnx')] * 8)

    def test_render_requests_missing_catalog_model(self):
        selection = self.voices / (self.key + '.onnx')
        with patch('openvoice.engines.builtin.ensure_piper_voice', return_value=selection) as ensure, \
             patch('openvoice.engines.builtin.piper_binary', return_value='/tmp/piper'), \
             patch('openvoice.engines.builtin.invoke', return_value=b''):
            self.install_fake_model(vc.catalog_voice(self.key))
            Piper().render_wav('Hello', self.base / 'out.wav', SpeechSettings(voice=self.key, speaker_id=1))
            ensure.assert_called_once_with(self.key, control=None)

    def test_external_onnx_is_not_downloaded_and_invalid_unknown_rejected(self):
        path = self.voices / 'external.onnx'
        path.write_bytes(b'manually installed')
        Path(str(path) + '.json').write_bytes(self.config)
        with patch('openvoice.voice_catalog.fetch_catalog', side_effect=RuntimeError('offline')) as fetch:
            self.assertEqual(vc.ensure_piper_voice(str(path)), path)
            fetch.assert_not_called()
        with self.assertRaises(ValueError):
            vc.ensure_piper_voice('unknown_voice_not_in_catalog')

    def test_auto_engine_honors_selected_catalog_voice(self):
        with patch('openvoice.engines.builtin.Piper.available', return_value=True):
            self.assertEqual(get_engine('auto', voice=self.key).key, 'piper')

    def test_selected_piper_missing_runtime_does_not_silently_fallback(self):
        from openvoice.engines.base import EngineError
        with patch('openvoice.engines.builtin.Piper.available', return_value=False):
            with self.assertRaisesRegex(EngineError, 'Piper speech runtime'):
                get_engine('auto', voice=self.key)

    def test_gui_downloads_without_modal_notices(self):
        from openvoice import gui
        source = Path(gui.__file__).read_text(encoding='utf-8')
        self.assertIn('def _on_piper_voice_selected', source)
        self.assertIn('def character_voice_chosen', source)
        self.assertIn('ensure_piper_voice(item.key, progress=report)', source)
        self.assertIn('def _confirm_piper_downloads', source)
        self.assertIn('messagebox.askyesno(', source)
        self.assertNotIn("messagebox.askyesno('Confirm voice downloads'", source)
        self.assertNotIn("messagebox.showinfo('Download complete'", source)
        self.assertNotIn("messagebox.showerror('Voice download failed'", source)


if __name__ == '__main__':
    unittest.main()
