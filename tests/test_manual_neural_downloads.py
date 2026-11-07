"""Regression coverage: neural downloads only on explicit GUI action."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice.neural_models import (MODEL_OPTIONS, VOICE_OPTIONS, model_environment,
                                     effective_model, is_downloaded, mark_downloaded,
                                     pocket_voice_state_path, require_downloaded)
from openvoice.neural_runtime import NEURAL_ENGINES
from openvoice.engines.base import SpeechSettings, EngineError


class ManualDownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.home = patch.dict(os.environ, {'OPENMUKTI_NEURAL_HOME':self.directory.name})
        self.home.start()
        self.addCleanup(self.home.stop)

    def test_visible_catalog_has_four_engines_and_curated_variants(self):
        self.assertEqual(set(MODEL_OPTIONS), set(NEURAL_ENGINES))
        self.assertEqual(set(VOICE_OPTIONS), set(NEURAL_ENGINES))
        self.assertEqual(len(VOICE_OPTIONS['kokoro']), 54)
        self.assertEqual(len(VOICE_OPTIONS['kitten']), 8)
        self.assertTrue('english_2m_2026-10' in MODEL_OPTIONS['pocket'])

    def test_different_kokoro_voices_need_individual_download(self):
        with self.assertRaisesRegex(RuntimeError, 'voice manager'):
            require_downloaded('kokoro', voice='af_heart')
        mark_downloaded('kokoro', voice='af_heart')
        self.assertTrue(is_downloaded('kokoro', voice='af_heart'))
        self.assertFalse(is_downloaded('kokoro', voice='jf_alpha'))
        self.assertFalse(is_downloaded('kokoro', model='another/model', voice='af_heart'))

    def test_kitten_and_coqui_all_speakers_share_one_model_asset(self):
        mark_downloaded('kitten', 'KittenML/kitten-tts-nano-0.8', 'Bella')
        self.assertTrue(is_downloaded('kitten', 'KittenML/kitten-tts-nano-0.8', 'Leo'))
        self.assertFalse(is_downloaded('kitten', 'KittenML/kitten-tts-mini-0.8', 'Bella'))
        mark_downloaded('coqui', 'tts_models/en/vctk/vits')
        self.assertTrue(is_downloaded('coqui', 'tts_models/en/vctk/vits', 'p225'))
        self.assertFalse(is_downloaded('coqui', 'tts_models/en/ljspeech/tacotron2-DDC'))

    def test_pocket_requires_prepared_local_voice_state(self):
        path = pocket_voice_state_path('english', 'alba')
        mark_downloaded('pocket', 'english', 'alba')
        self.assertFalse(is_downloaded('pocket', 'english', 'alba'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'pretend-safe-tensors')
        self.assertTrue(is_downloaded('pocket', 'english', 'alba'))
        self.assertFalse(is_downloaded('pocket', 'english', 'lola'))
        self.assertEqual(effective_model('pocket', voice='giovanni'), 'italian')

    def test_markers_are_not_network_downloads(self):
        env = model_environment(allow_network=False)
        self.assertEqual(env['HF_HUB_OFFLINE'], '1')
        self.assertEqual(env['TRANSFORMERS_OFFLINE'], '1')
        self.assertEqual(env['OPENMUKTI_NEURAL_DOWNLOAD'], '0')
        self.assertTrue(env['HF_HOME'].startswith(self.directory.name))
        explicit = model_environment(allow_network=True)
        self.assertNotIn('HF_HUB_OFFLINE', explicit)
        self.assertEqual(explicit['OPENMUKTI_NEURAL_DOWNLOAD'], '1')
        self.assertEqual(env['HF_HOME'], explicit['HF_HOME'])

    def test_render_and_voice_discovery_fail_before_starting_or_installing_any_worker(self):
        from openvoice.engines.neural import Kokoro82M, CoquiCPU
        with patch('openvoice.engines.neural._get_worker') as worker:
            with self.assertRaisesRegex(EngineError, 'voice manager'):
                Kokoro82M().render_wav('Hello', Path(self.directory.name)/'speech.wav',
                                      SpeechSettings(voice='af_heart'))
            with self.assertRaisesRegex(RuntimeError, 'voice manager'):
                CoquiCPU().voices_for_model('tts_models/en/vctk/vits')
            worker.assert_not_called()

    def test_gui_installer_and_download_are_separate_actions(self):
        from openvoice import gui
        source = Path(gui.__file__).read_text(encoding='utf-8')
        self.assertIn('def neural_voice_downloader(self)', source)
        self.assertNotIn("messagebox.askyesno('Confirm neural voice downloads'", source)
        self.assertIn('Download Kokoro / Kitten / Pocket / Coqui voices', source)
        self.assertIn('Download Selected', source)
        self.assertIn('require_downloaded(self.key, settings.model',
                      Path(sys.modules['openvoice.engines.neural'].__file__).read_text())

    def test_worker_disallows_background_download_requests(self):
        from openvoice import neural_worker as nw
        with patch.dict(os.environ, {'OPENMUKTI_NEURAL_DOWNLOAD':'0'}):
            with self.assertRaises(PermissionError):
                nw.process({'action':'download','engine':'kokoro','voice':'af_heart'})
        with patch.dict(os.environ, {'OPENMUKTI_NEURAL_DOWNLOAD':'1'}):
            with self.assertRaises(PermissionError):
                nw.process({'action':'voices','engine':'coqui'})

    def test_offline_guard_blocks_socket_connection(self):
        import socket
        from openvoice.neural_worker import forbid_network
        original_connect = socket.socket.connect
        original_create = socket.create_connection
        original_connect_ex = socket.socket.connect_ex
        try:
            forbid_network()
            with self.assertRaisesRegex(OSError,'disabled'):
                socket.create_connection(('example.com',443))
            with socket.socket() as test_socket:
                with self.assertRaisesRegex(OSError,'disabled'):
                    test_socket.connect(('127.0.0.1',1234))
        finally:
            socket.socket.connect = original_connect
            socket.create_connection = original_create
            socket.socket.connect_ex = original_connect_ex

    def test_pocket_explicit_worker_exports_voice_to_local_file(self):
        from openvoice import neural_worker as nw
        target = pocket_voice_state_path('english', 'alba')
        class Model:
            @classmethod
            def load_model(cls, **kwargs):
                return cls()
            def get_state_for_audio_prompt(self, voice):
                return {'voice':voice}
        def export_state(state, output):
            Path(output).write_bytes(json.dumps(state).encode())
        mock = types.SimpleNamespace(TTSModel=Model, export_model_state=export_state)
        with patch.dict(os.environ, {'OPENMUKTI_NEURAL_DOWNLOAD':'1'}), \
             patch.dict(sys.modules, {'pocket_tts':mock}):
            result = nw.process({'action':'download','engine':'pocket',
                                 'model':'english','voice':'alba','voice_state_path':str(target)})
        self.assertTrue(target.is_file())
        self.assertEqual(result['engine'], 'pocket')

    def test_download_failure_never_marks_model_installed(self):
        from openvoice.engines import neural
        with patch('openvoice.engines.neural.is_installed', return_value=True), \
             patch('openvoice.engines.neural._worker_script', return_value=Path('/neural_worker.py')), \
             patch('openvoice.engines.neural._Worker') as worker:
            worker.return_value.request.side_effect = RuntimeError('download failed')
            with self.assertRaisesRegex(RuntimeError,'failed'):
                neural.download_neural_voice('kitten', 'KittenML/kitten-tts-mini-0.8','Bella')
        self.assertFalse(is_downloaded('kitten', 'KittenML/kitten-tts-mini-0.8','Bella'))


if __name__ == '__main__':
    unittest.main()
