import importlib.util
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import build_unix as builder
from scripts.platform_support import architecture, elf_arch, macho_arch, pe_arch


def pe(path, machine):
    header = bytearray(128)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 60, 64)
    header[64:68] = b'PE\0\0'
    struct.pack_into('<H', header, 68, machine)
    path.write_bytes(header)


class BuildTests(unittest.TestCase):
    def test_binary_architecture_comes_from_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'program.exe'
            for machine, arch in ((0x8664, 'x86_64'), (0xaa64, 'aarch64')):
                pe(path, machine)
                self.assertEqual(pe_arch(path), arch)
            path.write_bytes(b'MZ not a valid executable')
            with self.assertRaises(ValueError): pe_arch(path)
            path.write_bytes(b'\x7fELF\x02\x01' + bytes(12) + b'\xb7\x00')
            self.assertEqual(elf_arch(path), 'aarch64')
            path.write_bytes(b'\xcf\xfa\xed\xfe' + struct.pack('<I',0x100000c))
            self.assertEqual(macho_arch(path),'aarch64')

    def test_architecture_aliases(self):
        for value, expected in [('AMD64','x86_64'), ('arm64','aarch64'), ('ppc64el','ppc64le'), ('sun4v','sparc64')]:
            self.assertEqual(architecture(value), expected)

    def test_windows_repair_reuses_only_matching_native_python(self):
        from scripts import build_windows_py315 as windows
        with tempfile.TemporaryDirectory() as temp:
            venv=Path(temp)/'main'
            binary=venv/'Scripts/python.exe'
            binary.parent.mkdir(parents=True)
            pe(binary,0xaa64)
            self.assertTrue(windows.matching_binary(binary,'aarch64'))
            self.assertFalse(windows.matching_binary(binary,'x86_64'))
            with patch.object(windows,'VENV',venv), patch.object(windows,'ASSETS',Path(temp)/'assets'), \
                 patch.object(windows,'windows_arch',return_value='aarch64'), \
                 patch.object(windows,'run') as run, patch.object(windows,'clean_environment') as clean, \
                 patch('scripts.auto_dependencies.ensure_pip'):
                # A mocked child process must simulate the binary that the
                # real pinned-archive installer would have placed on disk.
                directory=Path(temp)/'assets/text-layout/aarch64'
                directory.mkdir(parents=True)
                pe(directory/'libfribidi-0.dll',0xaa64)
                self.assertEqual(windows.build_main_environment(reuse=True),binary)
                clean.assert_not_called()
                self.assertFalse(any('venv' in call.args for call in run.call_args_list))

    def test_windows_repair_reuses_the_x64_worker_on_arm64(self):
        from scripts import build_windows_py315 as windows
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            main=root/'main'; native=root/'native'; workers=root/'workers'
            for directory in (main/'Scripts',native/'Scripts',workers): directory.mkdir(parents=True)
            (main/'Scripts/uv.exe').write_bytes(b'build tool fixture')
            pe(native/'Scripts/python.exe',0x8664)
            worker=workers/'OpenmuktiPiperWorker.exe';pe(worker,0x8664)
            with patch.multiple(windows,VENV=main,PIPER_VENV=native,WORKERS=workers), \
                 patch.object(windows,'windows_arch',return_value='aarch64'), patch.object(windows,'run') as run:
                self.assertEqual(windows.build_worker(main/'Scripts/python.exe',reuse=True),worker)
                self.assertFalse(any('PyInstaller' in call.args for call in run.call_args_list))
                self.assertTrue(any(call.args==(worker,'--health') for call in run.call_args_list))

    def test_windows_archive_uses_binary_identity_and_rejects_mixed_exes(self):
        module_path = builder.ROOT / 'packaging/package_windows_exes.py'
        spec = importlib.util.spec_from_file_location('windows_archive', module_path)
        packager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packager)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in packager.PROGRAMS: pe(root / (name + '.exe'), 0xaa64)
            output = packager.build(root)
            self.assertIn('Windows-arm64-UNVERIFIED', output.name)
            with zipfile.ZipFile(output) as package:
                info = json.loads(package.read('BUILD_PROVENANCE.json'))
                self.assertEqual(info['main_binary_architecture'], 'aarch64')
                self.assertFalse(info['runtime_verified'])
                self.assertFalse(info['signature_required'])
                self.assertTrue(info['windows_x64_emulation_required'])
            pe(root / (packager.PROGRAMS[0] + '.exe'), 0x8664)
            with self.assertRaises(ValueError): packager.build(root)

    def test_failed_format_keeps_successful_outputs_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / 'payload'; payload.mkdir()
            (payload / 'openmukti').write_text('test payload')
            args = SimpleNamespace(profile='frozen', formats='tar,deb', python=None, verify_runtime=False, verify_gui=False)
            def unavailable(*args): raise RuntimeError('dpkg-deb unavailable for test')
            with patch.multiple(builder, WORK=root / 'work', DIST=root / 'dist'), \
                 patch.object(builder, 'system', return_value='linux'), \
                 patch.object(builder, 'freeze', return_value=payload), \
                 patch.dict(builder.PACKAGERS, {'deb': unavailable}):
                self.assertEqual(builder.build(args), 1)
                report = json.loads((root / 'dist/build-report.json').read_text())
                self.assertEqual(report['results']['tar']['status'], 'built')
                self.assertEqual(report['results']['deb']['status'], 'failed')
                self.assertFalse(report['runtime_verified'])
                self.assertTrue((root / 'dist' / report['results']['tar']['file']).is_file())

    def test_foreign_format_is_rejected(self):
        args = SimpleNamespace(profile='frozen', formats='dmg', python=None, verify_runtime=False, verify_gui=False)
        with tempfile.TemporaryDirectory() as temp, patch.object(builder, 'system', return_value='linux'), \
             patch.multiple(builder, WORK=Path(temp)/'work', DIST=Path(temp)/'dist'):
            self.assertEqual(builder.build(args), 2)


if __name__ == '__main__':
    unittest.main()
