import io
import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from openvoice.engines import SpeechSettings, RunControl
from openvoice.engines.base import Cancelled
from openvoice.service import render_text, JobOptions
from openvoice.progress import ConsoleProgress, Progress, emit, subprogress, run_ffmpeg
from openvoice.audiobooks import Book, Chapter, BookExportOptions, export_books


class Voice:
    key = 'test'
    def render_wav(self, text, output, settings, control):
        with wave.open(str(output), 'wb') as audio:
            audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\0\0' * 160)


class ProgressTests(unittest.TestCase):
    def test_audio_is_complete_only_after_file_is_saved(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'narration.wav'
            def receive(event):
                if event.fraction == 1:
                    self.assertTrue(target.is_file())
                    with wave.open(str(target)) as audio: self.assertGreater(audio.getnframes(), 0)
                events.append(event)
            render_text('A sentence. Another sentence. ' * 6,target,Voice(),SpeechSettings(),JobOptions(chunk_size=40),status=receive)
        self.assertEqual(events[-1].fraction, 1)
        self.assertEqual(sorted(e.fraction for e in events), [e.fraction for e in events])
        self.assertTrue(any('Merging' in e.label for e in events))
        self.assertTrue(any(e.stage_fraction is None for e in events))

    def test_cancelled_render_never_reports_completion(self):
        events = []
        control = RunControl(); control.stop()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'cancelled.wav'
            with self.assertRaises(Cancelled):
                render_text('Hello world.',target,Voice(),SpeechSettings(),control=control,status=events.append)
            self.assertFalse(target.exists())
        self.assertFalse(any(e.fraction == 1 for e in events))

    def test_book_merge_and_report_are_part_of_overall_progress(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            book = Book('Test book', [Chapter('One',[],text='First chapter.'),Chapter('Two',[],text='Second chapter.')])
            def receive(event):
                if event.fraction == 1:
                    self.assertTrue((root / 'openvoice-batch-report.json').exists())
                events.append(event)
            with patch('openvoice.audiobooks.find_binary', return_value=''):
                result = export_books([book],root,engine=Voice(),settings=SpeechSettings(),
                                      options=BookExportOptions(mode='both',output_type='audio',audio_format='wav'),status=receive)
            self.assertFalse(result['failures'])
            self.assertTrue(Path(result['books'][0]['combined']).is_file())
        self.assertEqual(events[-1].fraction, 1)
        self.assertEqual(sorted(e.fraction for e in events), [e.fraction for e in events])
        self.assertTrue(any('Combining chapters' in e.label for e in events))

    def test_failed_chapter_does_not_show_success(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            result = export_books([Book('Missing',[Chapter('No text',[])])],temp,engine=Voice(),settings=SpeechSettings(),
                                  options=BookExportOptions(output_type='audio'),status=events.append)
        self.assertTrue(result['failures'])
        self.assertLess(events[-1].fraction, 1)

    def test_nested_progress_and_cli_stream(self):
        events = []
        emit(subprogress(events.append,.3,.6,'Book one'),.5,'Encoding',.2)
        self.assertAlmostEqual(events[0].fraction,.45)
        self.assertEqual(events[0].stage_fraction,.2)
        stream=io.StringIO()
        ConsoleProgress(stream)(Progress(1,'Saved',1))
        self.assertIn('100%',stream.getvalue())

    @unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
    def test_ffmpeg_reports_real_encoded_time_and_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            target=Path(temp)/'encoded.wav'
            command=[shutil.which('ffmpeg'),'-hide_banner','-loglevel','error','-y','-re','-f','lavfi',
                     '-i','anullsrc=r=8000:cl=mono','-t','1.3',str(target)]
            values=[]
            run_ffmpeg(command,progress=values.append,duration=1.3)
            self.assertTrue(any(0 < v < 1 for v in values))
            self.assertEqual(values[-1],1)
            control=RunControl()
            values=[]
            def cancel(value):
                values.append(value)
                if value > 0: control.stop()
            with self.assertRaises(Cancelled):
                run_ffmpeg(command,control=control,progress=cancel,duration=1.3)
            self.assertFalse(any(v==1 for v in values))


if __name__ == '__main__':
    unittest.main()
