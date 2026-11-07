"""Dependency bootstrap tests are deliberately offline and never install OS packages."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build as entry
import build_detect_os
from scripts import auto_dependencies as deps


class DependencyBootstrapTests(unittest.TestCase):
    def test_debian_native_packages_are_planned_not_installed(self):
        with patch.object(deps, 'system', return_value='linux'), \
             patch.object(deps, 'linux_manager', return_value=('apt', 'apt-get')), \
             patch.object(deps, 'installed', return_value=False), \
             patch.object(deps, 'run_install', return_value=(True, 'planned')) as run:
            result = deps.ensure_dependencies(['deb', 'rpm', 'flatpak'], 'frozen', dry_run=True)
        names = set(result['tools'])
        self.assertTrue({'tesseract', 'tesseract-eng', 'tesseract-osd', 'ffmpeg',
                         'dpkg-deb', 'rpmbuild', 'flatpak-builder', 'python-venv'} <= names)
        self.assertTrue(all(item['status'] == 'planned' for item in result['tools'].values()))
        self.assertTrue(any('apt-get' in call.args[0] for call in run.call_args_list))

    def test_missing_unsupported_tool_is_reported_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(deps, 'system', return_value='linux'), \
             patch.object(deps, 'linux_manager', return_value=('apt', 'apt-get')), \
             patch.object(deps, 'installed', side_effect=lambda tool, **kw: tool != 'abuild'), \
             patch.object(deps, 'run_install') as installer:
            report = deps.ensure_dependencies(['apk'], 'frozen', report_path=Path(tmp) / 'deps.json')
            saved = json.loads((Path(tmp) / 'deps.json').read_text())
        self.assertEqual(report['tools']['abuild']['status'], 'unavailable')
        self.assertEqual(saved['tools']['abuild']['status'], 'unavailable')
        installer.assert_not_called()

    def test_preexisting_packages_are_not_reinstalled(self):
        with patch.object(deps, 'system', return_value='linux'), \
             patch.object(deps, 'linux_manager', return_value=('apt', 'apt-get')), \
             patch.object(deps, 'installed', return_value=True), \
             patch.object(deps, 'run_install') as installer:
            deps.ensure_dependencies(['deb'], 'frozen', dry_run=True)
        installer.assert_not_called()

    def test_cli_only_does_not_install_multimedia(self):
        with patch.object(deps, 'system', return_value='linux'), \
             patch.object(deps, 'linux_manager', return_value=('apt', 'apt-get')), \
             patch.object(deps, 'installed', return_value=True):
            result = deps.ensure_dependencies([], 'system', dry_run=True,
                                              cli_only=True, cli_tools=('git', 'gh'))
        self.assertEqual(set(result['tools']), {'git', 'gh'})

    def test_no_shell_commands_for_package_installs(self):
        command = deps.install_command('winget', 'winget', 'GitHub.cli')
        self.assertEqual(command[0], 'winget')
        self.assertNotIn('powershell', command)
        self.assertNotIn('curl', command)

    def test_cli_deps_plan_makes_no_changes(self):
        with patch.object(entry, 'system', return_value='linux'), \
             patch.object(deps, 'ensure_dependencies', return_value={'dry_run': True}) as prepare, \
             contextlib.redirect_stdout(io.StringIO()):
            result = entry.main(['--formats', 'tar,deb', '--deps-plan'])
        self.assertEqual(result, 0)
        self.assertTrue(prepare.call_args.kwargs['dry_run'])

    def test_detect_os_installs_before_filtering_absent_formats(self):
        call_sequence = []
        def setup(*args, **kwargs):
            call_sequence.append('install')
            return {'tools': {}}
        def select(*args, **kwargs):
            call_sequence.append('filter')
            return ['tar'], []
        with patch.object(build_detect_os, 'system', return_value='linux'), \
             patch.object(build_detect_os, 'selected_profile', return_value='system'), \
             patch.object(build_detect_os, 'automatic_formats', side_effect=select), \
             patch.object(deps, 'ensure_dependencies', side_effect=setup), \
             patch.object(build_detect_os.build, 'main', return_value=0), \
             contextlib.redirect_stdout(io.StringIO()):
            code = build_detect_os.main([])
        self.assertEqual(code, 0)
        self.assertEqual(call_sequence, ['install', 'filter'])


if __name__ == '__main__':
    unittest.main()
