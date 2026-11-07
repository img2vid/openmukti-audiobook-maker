"""Regression tests for opt-in voice collections, Unicode reports, audio effects and metadata."""
import json
import math
import shutil
import struct
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from openvoice.voice_library import (VoiceLibrary, duplicate_models,
                                    export_voice_pack, import_voice_pack)
from openvoice.manuscript_validation import (script_of, mixed_script_report,
                                             publication_preflight, audit_audio_segments)
from openvoice.media_metadata import tag_audio
from openvoice.audiofx import process_audio
from openvoice.cli import main as cli_main
from openvoice.piper_models import PiperVoice


class VoicePackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.models = self.root/'models'
        self.models.mkdir()
        self.model = self.models/'en_TEST-demo.onnx'
        self.config = self.models/'en_TEST-demo.onnx.json'
        self.model.write_bytes(b'fake ONNX for packaging tests')
        self.config.write_text('{"num_speakers": 2, "speaker_id_map": {"one": 0, "two": 1}}')
        self.voice = PiperVoice('en_TEST-demo', self.model, self.config)

    def test_metadata_persistence(self):
        library = VoiceLibrary(self.root/'library.json')
        library.set_favorite(self.voice.name, True)
        library.set_tags(self.voice.name, ['calm', 'Calm', ' soft '])
        library.set_collection('storybook', [self.voice.name])
        fresh = VoiceLibrary(self.root/'library.json')
        self.assertEqual(fresh.voices[self.voice.name]['tags'], ['calm', 'soft'])
        self.assertEqual(fresh.collections['storybook'], [self.voice.name])
        with patch('openvoice.voice_library.discover_voices', return_value=[self.voice]):
            self.assertEqual(len(fresh.list_voices(favorites_only=True, tag='CALM')), 1)
            self.assertEqual(fresh.list_voices(tag='missing'), [])

    def test_voice_pack_roundtrip_and_existing_file_protection(self):
        pack = self.root/'pack.zip'
        with patch('openvoice.voice_library.discover_voices', return_value=[self.voice]):
            export_voice_pack(pack, [self.voice.name])
        installed = import_voice_pack(pack, target=self.root/'installed')
        self.assertEqual(len(installed), 2)
        self.assertEqual((self.root/'installed'/self.config.name).read_bytes(), self.config.read_bytes())
        with self.assertRaises(FileExistsError):
            import_voice_pack(pack, target=self.root/'installed')
        self.assertEqual(len(import_voice_pack(pack, target=self.root/'installed', overwrite=True)), 2)

    def test_pack_checksum_mismatch_rejected_before_write(self):
        pack = self.root/'pack.zip'
        with patch('openvoice.voice_library.discover_voices', return_value=[self.voice]):
            export_voice_pack(pack, [self.voice.name])
        with zipfile.ZipFile(pack) as zipped:
            manifest = zipped.read('manifest.json')
            source = {n: zipped.read(n) for n in zipped.namelist() if n != 'manifest.json'}
        altered = self.root/'altered.zip'
        with zipfile.ZipFile(altered, 'w') as zipped:
            zipped.writestr('manifest.json', manifest)
            for name, content in source.items():
                zipped.writestr(name, b'tampered' if name.endswith('.onnx') else content)
        destination = self.root/'bad_import'
        with self.assertRaises(ValueError):
            import_voice_pack(altered, target=destination)
        self.assertEqual(list(destination.rglob('*.onnx')), [])

    def test_duplicate_hashes(self):
        other = self.root/'dupes'
        other.mkdir()
        (other/'copy.onnx').write_bytes(self.model.read_bytes())
        groups = duplicate_models([self.models, other])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 2)


class HardwareTests(unittest.TestCase):
    def test_opt_in_profiles_and_gpu_fallback_diagnostics(self):
        from openvoice.hardware import apply_cpu_profile, gpu_preference, hardware_status
        from unittest.mock import patch
        import os
        with patch.dict(os.environ, {}, clear=True):
            result = apply_cpu_profile('low')
            self.assertEqual(result['threads'], 1)
            self.assertEqual(os.environ['OMP_NUM_THREADS'], '1')
            gpu_preference(True)
            status = hardware_status('.')
            self.assertTrue(status['gpu_requested'])
            self.assertIn('disk_free_bytes', status)
            gpu_preference(False)
            self.assertEqual(os.environ['OPENMUKTI_PIPER_GPU'], '0')
        with self.assertRaises(ValueError):
            apply_cpu_profile('impossible')


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_unicode_script_detection(self):
        self.assertEqual(script_of('অ'), 'Bengali')
        self.assertEqual(script_of('Ж'), 'Cyrillic')
        report = mixed_script_report('বাংলা and English text.\n\n日本語だけ\n\nعربي')
        self.assertEqual(report['mixed_paragraph_count'], 2)
        self.assertEqual(report['scripts']['Bengali'], 5)
        self.assertTrue(report['warnings'])

    def test_combining_mark_report(self):
        report = mixed_script_report('\u0301abc')
        self.assertEqual(report['combining_mark_warnings'][0]['index'], 0)

    def test_publication_report_warns_and_detects_empty_file(self):
        (self.root/'blank.mp3').write_bytes(b'')
        report = publication_preflight(self.root)
        self.assertFalse(report['ready_for_manual_platform_review'])
        (self.root/'blank.mp3').write_bytes(b'not a real mp3')
        # Preflight is a basic size/metadata audit, not a codec certification.
        report = publication_preflight(self.root, title='Book', author='Author', language='en')
        self.assertTrue(report['ready_for_manual_platform_review'])

    def test_segment_missing_checksum_and_escape(self):
        (self.root/'a.wav').write_bytes(b'wave')
        manifest = self.root/'manifest.json'
        manifest.write_text(json.dumps({'segments':[{'id': 1,'file':'a.wav'},
                                                   {'id':2,'file':'b.wav'}]}))
        report = audit_audio_segments(manifest, self.root)
        self.assertEqual(report['missing_or_corrupt'], 1)
        manifest.write_text(json.dumps([{'file': '../parent.wav'}]))
        with self.assertRaises(ValueError):
            audit_audio_segments(manifest, self.root)

    def test_command_script_check(self):
        file = self.root/'text.txt'
        file.write_text('Hello, বাংলা!')
        report = self.root/'report.json'
        self.assertEqual(cli_main(['script-check', '-f', str(file), '-w', str(report)]), 0)
        self.assertTrue(json.loads(report.read_text())['mixed_paragraph_count'])

    def test_searchable_pdf_ocr_image(self):
        if not shutil.which('tesseract'):
            self.skipTest('Tesseract unavailable')
        try:
            from PIL import Image, ImageDraw
            from pypdf import PdfReader
        except ImportError:
            self.skipTest('Pillow and pypdf needed for image/PDF test')
        from openvoice.ocr import OCRSettings, create_searchable_pdf
        scan = self.root/'page.png'
        image = Image.new('RGB',(700,170),'white')
        ImageDraw.Draw(image).text((40,55),'Openmukti OCR Test 2026',fill='black')
        image.save(scan)
        target = self.root/'searchable.pdf'
        create_searchable_pdf(scan,target,OCRSettings(preprocessing='original'))
        text = PdfReader(str(target)).pages[0].extract_text()
        self.assertIn('Openmukti',text)

        file = self.root/'text.txt'
        file.write_text('Hello, বাংলা!')
        report = self.root/'report.json'
        self.assertEqual(cli_main(['script-check', '-f', str(file), '-w', str(report)]), 0)
        self.assertTrue(json.loads(report.read_text())['mixed_paragraph_count'])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required for functional effects tests')
class AudioEffectsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.wav = self.root/'tone.wav'
        with wave.open(str(self.wav), 'wb') as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(16000)
            frames = b''.join(struct.pack('<hh', round(8000*math.sin(2*math.pi*440*i/16000)),
                              round(8000*math.sin(2*math.pi*440*i/16000))) for i in range(16000))
            out.writeframes(frames)

    def test_new_audio_filters(self):
        for operation in ('deess','equalize','pan','trim-silence'):
            target = self.root/(operation+'.wav')
            result = process_audio([self.wav], target, operation=operation, eq_gain=3, pan=0.5)
            self.assertTrue(result.is_file(), operation)
            self.assertGreater(result.stat().st_size, 100)

    def test_embedded_cover_image(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow is unavailable')
        import subprocess
        source = self.root/'source.mp3'
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                        '-i',str(self.wav),str(source)],check=True)
        cover = self.root/'cover.jpg'
        Image.new('RGB',(128,128),(90,120,160)).save(cover)
        result = tag_audio(source,self.root/'with-cover.mp3',tags={'title':'Illustrated book'},cover=cover)
        self.assertTrue(result.is_file())
        metadata = subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,disposition',
                                   '-of','json',str(result)],capture_output=True,text=True,check=True)
        self.assertTrue(any(x.get('codec_type') == 'video' for x in json.loads(metadata.stdout)['streams']))

    def test_invalid_audio_controls(self):
        with self.assertRaises(ValueError):
            process_audio([self.wav], self.root/'bad.wav', operation='pan', pan=2)

    def test_metadata_stream_copy(self):
        import subprocess
        original = self.root/'source.mp3'
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(self.wav),str(original)],check=True)
        target = self.root/'tagged.mp3'
        self.assertEqual(tag_audio(original,target,tags={'title':'Story','artist':'Narrator'}), target)
        self.assertTrue(target.stat().st_size > 0)
        with self.assertRaises(ValueError):
            tag_audio(original, original, tags={'title':'Story'})
        with self.assertRaises(ValueError):
            tag_audio(original, self.root/'bad.mp3', tags={'invalid':'text'})


if __name__ == '__main__':
    unittest.main()
