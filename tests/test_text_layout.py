"""Real BASIC fonts reproduce the no-libraqm runtime seen in Windows packages."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
import warnings
import wave
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw, ImageFont
from openvoice import text_layout
from openvoice.animated_video import (
    MODES, PagePainter, ScriptFont, _font_candidates, _measure,
    estimate_timing, paginate, pick_font,
)


class TextLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        font=pick_font('Hello world',24)
        cls.font_path=Path(font.primary.path if isinstance(font,ScriptFont) else font.path)

    def basic(self):
        return ImageFont.truetype(str(self.font_path),24,layout_engine=ImageFont.Layout.BASIC)

    def test_reproduces_original_error_and_measures_real_basic_font(self):
        font=self.basic()
        with self.assertRaisesRegex((KeyError,ValueError),'libraqm'):
            font.getlength('Hello',direction='ltr')
        self.assertGreater(text_layout.text_length(font,'Hello'),0)
        self.assertEqual(_measure(font,'Hello','ltr'),font.getlength('Hello'))
        self.assertEqual(text_layout.layout_options(font,'rtl',language='ar',features=['kern']),{})

    def test_basic_measurement_matches_drawn_glyphs(self):
        font=self.basic()
        expected=Image.new('RGB',(280,90),'black')
        actual=expected.copy()
        ImageDraw.Draw(expected).text((12,12),'Hello world',font=font,fill='white')
        text_layout.draw_text(ImageDraw.Draw(actual),(12,12),'Hello world',font,'white','ltr')
        self.assertIsNone(ImageChops.difference(expected,actual).getbbox())
        self.assertIsNotNone(actual.getbbox())

    def test_font_selection_requests_basic_without_raqm_or_warnings(self):
        with patch('openvoice.text_layout.raqm_available',return_value=False):
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                font=pick_font('Hello world',24,str(self.font_path))
            primary=font.primary if isinstance(font,ScriptFont) else font
            self.assertEqual(primary.layout_engine,ImageFont.Layout.BASIC)
            self.assertGreater(_measure(font,'Hello world','ltr'),0)

    def test_every_animation_paints_with_real_basic_font(self):
        font=self.basic()
        pages=paginate(estimate_timing('Hello world. The next line.',2),font,240,3,2)
        for mode in MODES:
            with self.subTest(mode=mode):
                painter=PagePainter(pages,(320,240),font,mode=mode,color='FFFFFF',panel_opacity=160)
                frame=painter.render(Image.new('RGB',(320,240),'black'),1.2)
                self.assertEqual(frame.size,(320,240))
                self.assertIsNotNone(frame.getbbox())

    def test_basic_font_can_render_unicode_without_unsupported_keywords(self):
        # Glyph shaping quality is deliberately not claimed without RAQM.
        font=self.basic()
        for text in ('שלום עולם','مرحبا بالعالم','नमस्ते दुनिया','こんにちは世界'):
            with self.subTest(text=text):
                pages=paginate(estimate_timing(text+' Hello',2),font,250,3,2)
                painter=PagePainter(pages,(320,240),font,mode='static',color='FFFFFF',panel_opacity=160)
                self.assertIsNotNone(painter.render(Image.new('RGB',(320,240),'black'),1).getbbox())

    def test_script_fallback_fonts_are_safe_and_loaded_only_once(self):
        primary=self.basic()
        candidates=[p for p in _font_candidates() if p.resolve()!=self.font_path.resolve()]
        if not candidates:self.skipTest('Second font required')
        secondary=candidates[0]
        script=ScriptFont(primary,(secondary,),24)
        def coverage(path):
            return frozenset(map(ord,'Hello')) if Path(path)==self.font_path else frozenset(map(ord,'HelloΩ'))
        with patch('openvoice.animated_video._coverage',side_effect=coverage),patch('openvoice.text_layout.raqm_available',return_value=False):
            with patch('openvoice.animated_video.load_font',wraps=text_layout.load_font) as loaded:
                for _ in range(5):
                    self.assertGreater(script.getlength('Hello Ω'),0)
                    image=Image.new('RGB',(320,80),'black')
                    script.draw_text(ImageDraw.Draw(image),(5,5),'Hello Ω','white')
                self.assertEqual(loaded.call_count,1)
                self.assertTrue(all(f.layout_engine==ImageFont.Layout.BASIC for f in script._font_cache.values()))

    @unittest.skipUnless(text_layout.raqm_available(),'RAQM required')
    def test_raqm_direction_is_preserved_when_available(self):
        font=text_layout.load_font(self.font_path,24)
        self.assertEqual(text_layout.layout_options(font,'rtl'),{'direction':'rtl'})
        text='שלום 123'
        self.assertEqual(text_layout.text_length(font,text,'rtl'),font.getlength(text,direction='rtl'))
        expected=Image.new('RGB',(320,90),'black');actual=expected.copy()
        ImageDraw.Draw(expected).text((5,5),text,font=font,fill='white',direction='rtl')
        text_layout.draw_text(ImageDraw.Draw(actual),(5,5),text,font,'white','rtl')
        self.assertIsNone(ImageChops.difference(expected,actual).getbbox())

    def test_partial_runtime_retries_only_the_specific_libraqm_error(self):
        class Font:
            layout_engine=ImageFont.Layout.RAQM
            def getlength(self,text,**options):
                if options:raise KeyError('setting text direction, language or font features is not supported without libraqm')
                return 42
        class Drawer:
            def __init__(self):self.calls=[]
            def text(self,*args,**options):
                self.calls.append(options)
                if 'direction' in options:raise ValueError('setting text direction, language or font features is not supported without libraqm')
        with patch('openvoice.text_layout.raqm_available',return_value=True):
            self.assertEqual(text_layout.text_length(Font(),'Hello'),42)
            drawer=Drawer()
            text_layout.draw_text(drawer,(0,0),'Hello',Font(),'white')
            self.assertEqual(len(drawer.calls),2)
            self.assertNotIn('direction',drawer.calls[-1])
            with patch.object(Font,'getlength',side_effect=ValueError('Invalid font data')):
                with self.assertRaisesRegex(ValueError,'Invalid font data'):
                    text_layout.text_length(Font(),'Hello')

    def test_portable_check_exercises_native_and_basic_rendering(self):
        from openvoice.portable import _check_text_rendering
        with patch('openvoice.text_layout.raqm_available',return_value=False):
            result=_check_text_rendering()
        self.assertFalse(result['raqm'])
        self.assertFalse(result['complex_script_shaping'])
        self.assertTrue(result['native_text_rendered'])
        self.assertTrue(result['basic_fallback_rendered'])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_actual_video_export_without_raqm_with_and_without_artwork(self):
        from openvoice.video import render_video,VideoOptions
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with wave.open(str(root/'voice.wav'),'wb') as wav:
                wav.setparams((1,2,8000,0,'NONE','not compressed'))
                wav.writeframes(b'\0\0'*8000)
            Image.new('RGB',(160,120),(20,50,90)).save(root/'cover.png')
            with patch('openvoice.text_layout.raqm_available',return_value=False):
                for mode,images in [('typewriter',[root/'cover.png']),('handwriting',[])]:
                    with self.subTest(mode=mode):
                        output=root/(mode+'.mp4')
                        render_video(images,output,audio=root/'voice.wav',text='Hello world.',video_options=VideoOptions(animation=mode,dimensions='160x120',fps=24,font_path=str(self.font_path)))
                        self.assertGreater(output.stat().st_size,1000)


class PillowBundlingTests(unittest.TestCase):
    def bundle_helper(self):
        source=Path(__file__).resolve().parents[1]/'packaging'/'pillow_bundle.py'
        spec=importlib.util.spec_from_file_location('openmukti_pillow_bundle',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_sibling_native_libraries_and_load_order_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pil=root/'PIL';pil.mkdir()
            libs=root/'pillow.libs';libs.mkdir()
            binary=libs/'fribidi.dll';binary.write_bytes(b'DLL fixture')
            load_order=libs/'.load-order-pillow';load_order.write_text('fribidi.dll')
            options=self.bundle_helper().pillow_options(pil)
            self.assertIn('--add-binary',options)
            self.assertIn('--add-data',options)
            self.assertIn(str(binary)+os.pathsep+'pillow.libs',options)
            self.assertIn(str(load_order)+os.pathsep+'pillow.libs',options)

    def test_no_sibling_libraries_is_supported(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.bundle_helper().pillow_options(Path(d)/'PIL'),[])


if __name__=='__main__':unittest.main()
