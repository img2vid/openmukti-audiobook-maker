"""Regression tests for unified BAT-free, single-file public build entry point."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build as launcher
from scripts import build_windows_py315 as worker


class SingleBuildLauncherTests(unittest.TestCase):
    def test_windows_repair_and_runtime_verification_reach_internal_builder(self):
        with patch.object(launcher, 'system', return_value='windows'), \
             patch.object(worker, 'entrypoint', return_value=0) as entry:
            self.assertEqual(launcher.main(['--repair', '--verify-runtime']), 0)
            entry.assert_called_once_with(['--repair', '--verify-runtime'])

    def test_windows_resume_alias(self):
        with patch.object(launcher, 'system', return_value='windows'), \
             patch.object(worker, 'entrypoint', return_value=0) as entry:
            self.assertEqual(launcher.main(['--resume']), 0)
            entry.assert_called_once_with(['--repair'])

    def test_windows_package_existing_is_not_a_new_build(self):
        with patch.object(launcher, 'system', return_value='windows'), \
             patch.object(worker, 'entrypoint', return_value=0) as entry:
            self.assertEqual(launcher.main(['--package-existing']), 0)
            entry.assert_called_once_with(['--package-existing'])

    def test_windows_incompatible_options_are_rejected(self):
        with patch.object(launcher, 'system', return_value='windows'):
            with self.assertRaises(SystemExit):
                launcher.main(['--verify-existing','--verify-runtime'])

    def test_non_windows_rejects_windows_repair(self):
        with patch.object(launcher, 'system', return_value='linux'):
            with self.assertRaises(SystemExit):
                launcher.main(['--repair'])

    def test_last_step_status_survives_failed_child(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(worker, 'STATUS', Path(temp) / 'status.json'):
            with self.assertRaises(Exception):
                worker.run('this-command-does-not-exist-anywhere-9ffe52', cwd=Path(temp))
            entry = json.loads((Path(temp) / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(entry['phase'], 'could not launch command')
            self.assertIn('this-command-does-not-exist', entry['last_command'][0])


if __name__ == '__main__':
    unittest.main()
