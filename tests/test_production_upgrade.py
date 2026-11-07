import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from openvoice.documents import read_document, use_scan_dialog
from openvoice.project_archive import ProjectData, save_project, load_project
from openvoice.project_review import compare_projects, resource_report
from openvoice.release_tools import caption_export, release_archive
from openvoice.acceleration import load_voice


class ProductionUpgrade(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_imports(self):
        path = self.root / 'a.odt'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('content.xml', '<doc xmlns:o="urn:oasis:names:tc:opendocument:xmlns:office:1.0"><o:text><h>Title</h><p>A<s/>B</p></o:text></doc>')
        self.assertEqual(read_document(path), 'Title\n\nA B')
        path = self.root / 'b.fb2.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('nested/b.fb2', '<FictionBook><body><section><p>বাংলা</p></section></body></FictionBook>')
            z.writestr('second.txt', 'Café'.encode('cp1252'))
        self.assertFalse(use_scan_dialog(path))
        self.assertEqual(read_document(path), 'বাংলা\n\nCafé')
        self.assertFalse((self.root / 'b.fb2').exists())

    def test_review_and_release(self):
        book = self.root / 'book'
        book.mkdir()
        one, two = [book / f'{i}.oamproj' for i in (1, 2)]
        save_project(one, ProjectData(text='First'))
        save_project(two, ProjectData(text='Second', settings={'production': {'notes':'review'}}))
        self.assertIn('+Second', compare_projects(one, two))
        self.assertIn('No bundled assets', resource_report(one))
        self.assertEqual(load_project(two,self.root/'unpacked').settings['production']['notes'], 'review')
        output = self.root / 'release.zip'
        release_archive(book, output)
        with zipfile.ZipFile(output) as z:
            self.assertEqual(json.loads(z.read('sha256.json'))[one.name], hashlib.sha256(z.read(one.name)).hexdigest())

    def test_captions(self):
        cues = self.root/'time.json'
        cues.write_text('[{"start":59.9996,"end":61.25,"text":"A & B"}]')
        for ext, stamp in [('vtt','00:01:00.000'),('srt','00:01:00,000')]:
            out = self.root/('output.' + ext)
            caption_export(cues,out)
            self.assertIn(stamp,out.read_text())
            self.assertIn('A &amp; B',out.read_text())

    def test_gpu_fallback(self):
        from unittest.mock import Mock
        runtime = Mock()
        runtime.get_available_providers.return_value = ['CUDAExecutionProvider']
        voice = Mock()
        voice.load.side_effect = [RuntimeError('driver unavailable'), 'cpu']
        with patch.dict('os.environ', OPENMUKTI_PIPER_GPU='1'), patch.dict('sys.modules', onnxruntime=runtime), self.assertWarns(UserWarning):
            self.assertEqual(load_voice(voice,'model','cfg'),'cpu')
        self.assertEqual([call.kwargs['use_cuda'] for call in voice.load.call_args_list], [True, False])
