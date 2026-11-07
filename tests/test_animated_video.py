from __future__ import annotations
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from openvoice.animated_video import (
    _direction, estimate_timing, graphemes, load_cues, paginate, pick_font,
    timed_text, visible_book_text,
)
from openvoice.video import video_size, VideoOptions, render_video


class AnimatedVideoTests(unittest.TestCase):
    def test_custom_aspects_and_exact_dimensions(self):
        self.assertEqual(video_size('16:9','720p'),(1280,720))
        self.assertEqual(video_size('9:16','720p'),(404,720))
        self.assertEqual(video_size('11:8','360p'),(496,360))
        self.assertEqual(video_size('17:11','720p','1440x1080'),(1440,1080))
        for invalid in ('garbage','0:4','4:0','99999:1'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                video_size(invalid,'360p')
        for invalid in ('199x1080','1920x0','25000x1080','1920-1080'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                video_size('16:9','360p',invalid)

    def test_unicode_graphemes_and_book_tags(self):
        self.assertEqual(graphemes('e\u0301'),['e\u0301'])
        self.assertEqual(graphemes('क्ष'),['क्ष'])
        self.assertIn('Alice', visible_book_text('[Narrator] Alice said [Alice] “Hello.”'))
        self.assertNotIn('[Narrator]', visible_book_text('[Narrator] Alice said [Alice] “Hello.”'))
        self.assertIn('Hello',visible_book_text('[Narrator] Alice said [Alice] “Hello.”'))

    def test_script_directions(self):
        self.assertEqual(_direction('مرحبا'), 'rtl')
        self.assertEqual(_direction('שלום'), 'rtl')
        self.assertEqual(_direction('हिन्दी'), 'ltr')
        self.assertEqual(_direction('日本語'), 'ltr')

    def test_estimated_token_timing_is_monotonic(self):
        tokens=estimate_timing('Hello, world! नमस्ते दुनिया 你好世界 مرحبا',8)
        self.assertTrue(len(tokens)>=5)
        self.assertEqual(tokens[0].start,0)
        self.assertAlmostEqual(tokens[-1].end,8)
        for a,b in zip(tokens,tokens[1:]):
            self.assertAlmostEqual(a.end,b.start)

    def test_alignment_json_srt_vtt_and_preserves_real_word_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'aligned.json').write_text(json.dumps({'words':[{'start':.3,'end':1,'text':'Hello'},{'start':1.5,'end':2.5,'text':'world'}]}))
            tokens=timed_text('completely different',4,str(root/'aligned.json'))
            self.assertEqual([x.text for x in tokens],['Hello','world'])
            self.assertAlmostEqual(tokens[0].start,.3)
            self.assertAlmostEqual(tokens[1].start,1.5)
            (root/'aligned.srt').write_text('1\n00:00:00,300 --> 00:00:01,000\nनमस्ते\n\n2\n00:00:01,500 --> 00:00:02,500\n世界\n',encoding='utf-8')
            cues=load_cues(root/'aligned.srt',4)
            self.assertEqual(len(cues),2)
            self.assertEqual(cues[1].text,'世界')
            (root/'aligned.vtt').write_text('WEBVTT\n\n00:00:00.300 --> 00:00:01.000\nمرحبا\n', encoding='utf-8')
            self.assertEqual(load_cues(root/'aligned.vtt',4)[0].text,'مرحبا')

    def test_rejects_out_of_audio_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'invalid.json'
            file.write_text(json.dumps([{'start':3,'end':5,'text':'later'}]))
            with self.assertRaises(ValueError):load_cues(file,4)

    def test_multiscript_pages_keep_token_timestamps(self):
        example='Bonjour हिन्दी العربية 日本語 中文'
        f=pick_font(example,25)
        pages=paginate(estimate_timing(example,6),f,250,3,6)
        self.assertTrue(pages)
        self.assertTrue(all(len(page.lines)==len(page.word_steps) for page in pages))
        self.assertEqual(pages[-1].ending,6)
        self.assertTrue(all(page.word_steps for page in pages))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg and FFprobe required')
    def test_real_encoded_modes_with_cover_and_without_cover(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            with wave.open(str(d/'speech.wav'),'wb') as f:
                f.setparams((1,2,8000,0,'NONE','not compressed'))
                f.writeframes(b'\0\0'*9600)
            cover=d/'cover.png'
            Image.new('RGB',(170,220),(40,70,110)).save(cover)
            timed=d/'aligned.json'
            timed.write_text(json.dumps([{'start':0,'end':.5,'text':'Hello'},{'start':.5,'end':1.2,'text':'world'}]))
            for mode,images in [('typewriter',[cover]),('handwriting',[cover]),('scroll-up',[]),('karaoke',[cover]),('none',[cover])]:
                with self.subTest(mode=mode):
                    path=d/(mode+'.mp4')
                    result=render_video(images,path,audio=d/'speech.wav',text='Hello world',video_options=VideoOptions(animation=mode,dimensions='160x120',fps=24,timing_file=str(timed) if mode!='none' else ''))
                    self.assertTrue(result.exists())
                    self.assertGreater(result.stat().st_size,1000)
                    self.assertEqual(video_size('16:9','720p','160x120'),(160,120))

    def test_coverless_classic_video_remains_disallowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'image'):
                render_video([],Path(tmp)/'unused.mp4',audio=Path(tmp)/'no.wav')


if __name__=='__main__':
    unittest.main()

class AnimatedProjectArchiveTests(unittest.TestCase):
    def test_font_and_alignment_survive_project_export_import(self):
        from openvoice.project_archive import ProjectData,save_project,load_project
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            font=directory/'user-handwriting.ttf'
            font.write_bytes(b'dummy-font-to-test-resource-preservation')
            timeline=directory/'words.srt'
            timeline.write_text('1\n00:00:00,000 --> 00:00:01,000\nHello\n')
            picture=directory/'cover.png'
            picture.write_bytes(b'fake-image-bytes-for-project-packaging')
            project=ProjectData(text='Hello',video_images=[picture],video_settings={
                'animation':'handwriting','dimensions':'1440x1080',
                'font_path':str(font),'timing_file':str(timeline)})
            saved=save_project(directory/'book.oamproj',project)
            restored=load_project(saved,directory/'extract')
            self.assertEqual(restored.video_settings['animation'],'handwriting')
            self.assertEqual(restored.video_settings['dimensions'],'1440x1080')
            self.assertEqual(Path(restored.video_settings['font_path']).read_bytes(),font.read_bytes())
            self.assertEqual(Path(restored.video_settings['timing_file']).read_text(),timeline.read_text())
            self.assertEqual(restored.video_images[0].read_bytes(),picture.read_bytes())
