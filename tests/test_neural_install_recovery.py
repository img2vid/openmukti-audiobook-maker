"""Installer regression tests: actionable error output and compiler-free Japanese G2P."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice import neural_runtime as rt


class NeuralInstallRecoveryTests(unittest.TestCase):
    def test_failing_uv_command_includes_real_error_and_saves_log(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'install.log'
            result = subprocess.CompletedProcess(['uv'], 1, 'Resolved 8 packages\nerror: failed to build wheel for package X\n')
            with patch.object(rt.subprocess, 'run', return_value=result):
                with self.assertRaisesRegex(RuntimeError, 'failed to build wheel') as raised:
                    rt._run(['uv', 'pip', 'install', 'package'], log_path=log,
                            label='Testing installer')
            self.assertIn(str(log), str(raised.exception))
            self.assertIn('exit 1', str(raised.exception))
            self.assertIn('failed to build wheel', log.read_text(encoding='utf-8'))

    def test_repair_failure_leaves_ready_flag_absent_and_diagnostic_file(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'OPENMUKTI_NEURAL_HOME':directory}), \
             patch.object(rt, 'bundled_uv', return_value='/path/to/uv'):
            python = rt.python_path('kokoro')
            python.parent.mkdir(parents=True)
            python.write_text('fake python')
            def fail_on_package(command, **kwargs):
                if command[1:3] == ['pip', 'install']:
                    raise RuntimeError('failed: package not found')
            with patch.object(rt, '_run', side_effect=fail_on_package):
                with self.assertRaisesRegex(RuntimeError, 'package not found'):
                    rt.ensure_installed('kokoro')
            self.assertFalse(rt.is_installed('kokoro'))
            self.assertTrue(rt.installation_log('kokoro').exists())

    def test_kokoro_plan_avoids_compilers_and_unneeded_audio_torch(self):
        plan = rt.install_plan('kokoro')
        words = [item for step in plan for item in step]
        self.assertNotIn('misaki[ja,zh]', words)
        self.assertNotIn('misaki[ja]', words)
        self.assertIn('misaki[zh]', words)
        self.assertIn('pyopenjtalk-plus>=0.4.1.post8', words)
        self.assertIn('unidic-lite', words)
        self.assertNotIn('torchaudio', words)

    def test_gui_contains_diagnostic_view(self):
        from openvoice import gui
        text = Path(gui.__file__).read_text(encoding='utf-8')
        self.assertIn('def show_neural_install_log', text)
        self.assertIn('Copy diagnostics', text)
        self.assertIn('View / copy neural dependency installation log', text)


if __name__ == '__main__':
    unittest.main()
