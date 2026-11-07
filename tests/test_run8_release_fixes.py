"""Regressions for native release jobs that failed in GitHub Actions run #8."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import build_unix, ci_native, macos_tesseract


class NativeReleaseFixTests(unittest.TestCase):
    def test_real_ips_fmris_are_selected_from_installed_packages(self):
        inventory = ('pkg://omnios/runtime/python-311@3.11.15 i--\n'
                     'pkg:/image/tesseract@5.5 i--\n')
        self.assertEqual(
            ci_native.installed_ips_fmris(
                inventory, ['runtime/python-311', 'image/tesseract', 'video/ffmpeg']),
            ['pkg://omnios/runtime/python-311@3.11.15',
             'pkg:/image/tesseract@5.5'])
        self.assertEqual(ci_native.installed_ips_fmris('not installed',
                                                       ['runtime/python-311']), [])

    def test_ips_python_packages_match_active_omnios_runtime(self):
        packages = ci_native.ips_packages_for_python(3, 13)
        self.assertIn('runtime/python-313', packages)
        self.assertIn('library/python/tkinter-313', packages)
        self.assertNotIn('runtime/python-311', packages)

        inventory = (
            'pkg://omnios/runtime/python-313@3.13.6-151054 i--\\n'
            'pkg://omnios/runtime/python-311@3.11.12-151054 i--\\n'
            'pkg:/image/tesseract@5.5 i--\\n'
        ).replace('\\n', '\n')
        self.assertEqual(
            ci_native.installed_ips_fmris(inventory, packages),
            ['pkg://omnios/runtime/python-313@3.13.6-151054',
             'pkg:/image/tesseract@5.5'])

    def test_dragonfly_chooses_xz_not_unsupported_zstd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            work, dist, stage = [root / name for name in ('work','dist','stage')]
            for p in (work, dist, stage):
                p.mkdir()
            (stage / 'fixture.txt').write_text('test')
            def fake_run(*args, **kwargs):
                if args[:3] == ('pkg','config','ABI'):
                    return SimpleNamespace(stdout='DragonFly:6:amd64\n')
                if args[:2] == ('pkg','create'):
                    out = Path(args[args.index('-o') + 1])
                    out.mkdir(parents=True, exist_ok=True)
                    (out / 'openmukti-1.2.0.pkg').write_bytes(b'package fixture')
            with patch.multiple(build_unix, WORK=work, DIST=dist), \
                 patch.object(build_unix,'system',return_value='dragonfly'), \
                 patch.object(build_unix,'version',return_value='1.2.0'), \
                 patch.object(build_unix,'install_tree',return_value=stage), \
                 patch.object(build_unix,'run',side_effect=fake_run) as runner, \
                 patch.object(build_unix,'require'), \
                 patch.dict('os.environ', {
                     'OPENMUKTI_PKG_DEPENDENCIES':
                       '{"python311":{"origin":"lang/python311","version":"3.11"}}'
                 }):
                self.assertTrue(build_unix.bsd_package(stage,'system').is_file())
            create = next(call.args for call in runner.call_args_list
                          if call.args[:2] == ('pkg','create'))
            self.assertEqual(create[2:4], ('-f','txz'))

    def test_embedded_macos_tesseract_has_separate_dylib_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            # macOS /var -> /private/var and Windows short names -> long
            # names. Canonicalize the fixture before the production helper
            # (which deliberately calls resolve()) sees any path.
            root=Path(folder).resolve()
            original=root/'brew/bin/tesseract'; original.parent.mkdir(parents=True)
            original.write_bytes(b'original')
            lib=root/'brew/lib';lib.mkdir(parents=True)
            tesseract=lib/'libtesseract.5.dylib';tesseract.write_bytes(b'proper-ABI')
            leptonica=lib/'liblept.6.dylib';leptonica.write_bytes(b'lept')
            staged=root/'bundle/_internal/tesseract/tesseract'
            staged.parent.mkdir(parents=True);staged.write_bytes(b'rewritten')
            deps={original.resolve():[str(tesseract.resolve())],
                  tesseract.resolve():[str(leptonica.resolve()),
                   '/usr/lib/libSystem.B.dylib'], leptonica.resolve():[]}
            with patch.object(macos_tesseract,'_linked_libraries',
                              side_effect=lambda p: deps[Path(p).resolve()]), \
                 patch.object(macos_tesseract.subprocess,'run') as runner:
                self.assertEqual(
                    macos_tesseract.isolate_tesseract(root/'bundle',original),staged)
            self.assertEqual(staged.read_bytes(),b'original')
            self.assertEqual((staged.parent/'lib'/tesseract.name).read_bytes(),b'proper-ABI')
            changes=[call.args[0] for call in runner.call_args_list]
            self.assertIn(['install_name_tool','-change',str(tesseract.resolve()),
                           '@loader_path/lib/'+tesseract.name,str(staged)], changes)
            self.assertEqual(sum(c[0]=='codesign' for c in changes),3)


if __name__=='__main__':
    unittest.main()
