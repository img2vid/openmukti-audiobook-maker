"""v1.0.26 regressions: permanent Piper downloads, progress and consent flow."""
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice import voice_catalog as vc
from openvoice.piper_models import PiperSpeaker


class DownloadFeedbackTests(unittest.TestCase):
    def test_byte_progress_is_monotonic_across_model_and_config_files(self):
        model = b'piper-demo-onnx-data' * 400
        config = json.dumps({'num_speakers': 3}).encode()
        voice = vc.CatalogVoice(
            key='en_US-test-three', language='en-US', language_name='English',
            region='US', quality='medium', speakers=3,
            model_path='en/test.onnx', config_path='en/test.onnx.json',
            model_bytes=len(model), model_md5=hashlib.md5(model).hexdigest(),
            config_bytes=len(config), config_md5=hashlib.md5(config).hexdigest())
        recorded=[]
        def opener(request, timeout):
            return io.BytesIO(config if request.full_url.endswith('.json') else model)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = vc.download_voice(voice, destination=folder, opener=opener,
                                       progress=lambda done, total: recorded.append((done, total)))
            self.assertEqual(result.read_bytes(), model)
            self.assertEqual(Path(str(result) + '.json').read_bytes(), config)
        self.assertGreaterEqual(len(recorded), 2)
        self.assertEqual(recorded[-1], (len(model) + len(config), len(model) + len(config)))
        self.assertEqual([done for done, _ in recorded], sorted(done for done, _ in recorded))
        self.assertEqual(set(total for _, total in recorded), {len(model) + len(config)})

    def test_catalog_multispeaker_ids_are_available_without_model_download(self):
        from openvoice import gui
        source = Path(gui.__file__).read_text(encoding='utf8')
        self.assertIn('range(model.speakers)', source)
        self.assertIn('PiperSpeaker(index)', source)
        self.assertIn('def _confirm_piper_downloads', source)
        self.assertIn("messagebox.askyesno(", source)

    def test_no_automatic_installation_on_selection_and_installed_filters_every_picker(self):
        from openvoice import gui
        source = Path(gui.__file__).read_text(encoding='utf8')
        self.assertNotIn('_queue_piper_download(', source)
        self.assertGreaterEqual(source.count("text='Installed voices only'"), 4)
        self.assertIn('def character_voice_choices()', source)
        self.assertIn("'Not downloaded'", source)
        self.assertIn("'Downloading {percent}%'", source)
        self.assertIn("tree.set(iid, 'status', 'Downloaded')", source)
        self.assertIn('ensure_piper_voice(item.key, progress=report)', source)

    def test_renderer_still_uses_persistent_piper_catalog_directory(self):
        from openvoice.engines.builtin import Piper
        from openvoice.engines.base import SpeechSettings
        from openvoice.piper_models import voice_directory
        import inspect
        source = inspect.getsource(Piper.render_wav)
        self.assertIn('ensure_piper_voice(settings.voice, control=control)', source)
        self.assertIn('ensure_piper_voice(settings.model, control=control)', source)
        self.assertIn('voice_directory()', inspect.getsource(vc.download_voice))

if __name__ == '__main__':
    unittest.main()
