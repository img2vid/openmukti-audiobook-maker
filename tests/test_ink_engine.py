"""Regression tests for original OpenMukti multilingual pen engine."""
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from openvoice.animated_video import (PagePainter, estimate_timing, paginate,
                                      pick_font, graphemes)
from openvoice.ink_engine import prepare_step, draw_step
from openvoice.video import VideoOptions


class InkEngineTests(unittest.TestCase):
    def test_traces_without_opencv_numpy_or_any_language_dictionary(self):
        shaped=Image.new('RGBA',(100,45),(0,0,0,0))
        canvas=ImageDraw.Draw(shaped)
        canvas.line((12,25,33,7,51,27,80,6),fill=(255,255,255,255),width=5)
        # The core implementation has no cv2/numpy dependencies.
        with patch.dict('sys.modules',{'cv2':None,'numpy':None}):
            step=prepare_step(shaped,0,90,0,40,0,1,'ltr')
        self.assertIsNotNone(step)
        self.assertGreater(step.total_length,5)
        self.assertGreater(len(step.strokes),0)
        self.assertTrue(any(len(path.points)>2 for path in step.strokes))
        self.assertIsNone(draw_step(step,0,calligraphy=False,font_size=35)[0])
        partial,tip=draw_step(step,.25,calligraphy=False,font_size=35)
        self.assertIsNotNone(partial)
        self.assertIsNotNone(tip)
        full,_=draw_step(step,1,calligraphy=False,font_size=35)
        self.assertLess(sum(partial.getchannel('A').tobytes()),sum(full.getchannel('A').tobytes()))

    def test_distinct_effects_for_bengali_and_latin_shaped_text(self):
        text='নমস্কার বন্ধু Hello'
        font=pick_font(text,40,handwriting=True)
        pages=paginate(estimate_timing(text,3),font,650,3,3)
        self.assertTrue(pages)
        self.assertGreater(len(pages[0].word_steps[0]),4)
        background=Image.new('RGB',(800,250),(30,30,30))
        images={}
        for mode in ('typewriter','handwriting','calligraphy'):
            painter=PagePainter(pages,background.size,font,mode=mode,
                                color='FFFFFF',panel_opacity=150)
            images[mode]=painter.render(background,.13)
        self.assertIsNotNone(ImageChops.difference(images['typewriter'],images['handwriting']).getbbox())
        self.assertIsNotNone(ImageChops.difference(images['handwriting'],images['calligraphy']).getbbox())
        self.assertEqual(graphemes('ক্ষ'),['ক্ষ'])
        self.assertEqual(graphemes('e\u0301'),['e\u0301'])
        # Completed text must be fully drawn by every writing engine.
        finished={mode:PagePainter(pages,background.size,font,mode=mode,color='FFFFFF',
                                   panel_opacity=150).render(background,3)
                  for mode in ('typewriter','handwriting','calligraphy')}
        self.assertIsNotNone(ImageChops.difference(finished['handwriting'],finished['calligraphy']).getbbox())

    def test_rtl_arabic_and_multiple_scripts_are_accepted(self):
        text='مرحبا بالعالم • বাংলা • हिंदी • עברית • ภาษาไทย'
        font=pick_font(text,34,handwriting=True)
        pages=paginate(estimate_timing(text,5),font,720,4,5)
        p=PagePainter(pages,(850,330),font,mode='calligraphy',color='FFFFFF',panel_opacity=0)
        mid=p.render(Image.new('RGB',(850,330),'black'),2.5)
        end=p.render(Image.new('RGB',(850,330),'black'),5)
        self.assertIsNotNone(ImageChops.difference(mid,end).getbbox())

    def test_pen_parameters_persist_in_video_options(self):
        from dataclasses import asdict
        src=VideoOptions(animation='calligraphy',pen_width=7,nib_angle=55)
        restored=VideoOptions(**asdict(src))
        self.assertEqual(restored.pen_width,7)
        self.assertEqual(restored.nib_angle,55)

if __name__=='__main__':
    unittest.main()
