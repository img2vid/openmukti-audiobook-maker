"""Cross-platform release failures reproduced from GitHub Actions run #6."""
from __future__ import annotations
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import build_unix
from openvoice import cli


class ReleaseRegressions(unittest.TestCase):
    def test_tesseract_data_supports_ubuntu_4_00_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / 'tesseract-ocr'
            data = package / '4.00' / 'tessdata'
            data.mkdir(parents=True)
            for lang in ('eng', 'osd'):
                (data / (lang + '.traineddata')).touch()
            binary = root / 'bin' / 'tesseract'
            binary.parent.mkdir()
            binary.touch()
            with patch.dict('os.environ', {'TESSDATA_PREFIX': str(package / '4.00')}, clear=False):
                self.assertEqual(build_unix.tesseract_data(binary), data)

    def test_python_distribution_runs_pypa_build_outside_source_root(self):
        from scripts import auto_dependencies
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / '.build-native'
            dist = Path(tmp) / 'dist'
            dist.mkdir()
            interpreter = work / 'python-build-tools' / 'bin' / 'python'
            interpreter.parent.mkdir(parents=True)
            interpreter.touch()
            def fake_run(*arguments, **kwargs):
                if '-m' in arguments and 'build' in arguments:
                    output = work / 'python-dist-wheel'
                    output.mkdir(exist_ok=True)
                    (output / 'example.whl').write_bytes(b'test wheel')
            with patch.object(build_unix, 'WORK', work), patch.object(build_unix, 'DIST', dist), \
                 patch.object(auto_dependencies, 'ensure_pip'), \
                 patch.object(build_unix, 'run', side_effect=fake_run) as run, \
                 patch.object(build_unix.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as process:
                output = build_unix.python_distribution('wheel')
            self.assertEqual(output.read_bytes(), b'test wheel')
            self.assertEqual(run.call_args.kwargs['cwd'], work)
            self.assertEqual(process.call_args.kwargs['cwd'], work)

    def test_windows_redirected_help_stream_uses_utf8(self):
        output = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
        try:
            with patch.object(cli, 'os', SimpleNamespace(name='nt')), patch.object(cli.sys, 'stdout', output):
                cli._configure_windows_text_streams()
                self.assertEqual(output.encoding, 'utf-8')
                output.write('বাংলা')
                output.flush()
        finally:
            output.close()


if __name__ == '__main__':
    unittest.main()
