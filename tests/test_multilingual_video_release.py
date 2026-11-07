"""Regressions for the Bengali/Indic Windows release and pen animation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops, ImageFont

from openvoice.animated_video import PagePainter, ScriptFont, estimate_timing, paginate, pick_font
from openvoice.text_layout import raqm_available


class MultilingualVideoReleaseTests(unittest.TestCase):
    def test_bundled_bengali_font_works_with_empty_system_font_inventory(self):
        folder = Path(__file__).resolve().parents[1] / 'openvoice/resources/fonts'
        for script in ('Bengali', 'Devanagari', 'Tamil', 'Arabic'):
            self.assertTrue((folder / f'NotoSans{script}-Regular.ttf').is_file())
        self.assertTrue((folder / 'NOTO-COPYRIGHT-AND-LICENSE.txt').is_file())
        candidates = tuple(folder.glob('*.ttf'))
        with patch('openvoice.animated_video._font_candidates', return_value=candidates):
            for script in ('বাংলা ভাষা', 'हिंदी भाषा', 'தமிழ் மொழி'):
                for kind in ('typewriter', 'handwriting', 'calligraphy'):
                    with self.subTest(text=script, kind=kind):
                        f = pick_font(script, 28, handwriting=kind=='handwriting',
                                      calligraphy=kind=='calligraphy')
                        face = f.primary if isinstance(f, ScriptFont) else f
                        self.assertTrue(Path(face.path).is_file())
                        self.assertIn(str(folder), str(face.path))

    @unittest.skipUnless(raqm_available(), 'RAQM required')
    def test_bengali_handwriting_calligraphy_and_typewriter_render_differently(self):
        text = 'বাংলা ভাষা • हिंदी • English'
        face=pick_font(text,35,handwriting=True)
        self.assertEqual((face.primary if isinstance(face,ScriptFont) else face).layout_engine,
                         ImageFont.Layout.RAQM)
        page=paginate(estimate_timing(text,4),face,600,2,4)
        background=Image.new('RGB',(700,200),'#1f2635')
        frames=[]
        for mode in ('typewriter','handwriting','calligraphy'):
            painter=PagePainter(page,background.size,face,mode=mode,
                                color='FFFFFF',panel_opacity=120)
            frames.append(painter.render(background,.9))
        self.assertIsNotNone(ImageChops.difference(frames[0],frames[1]).getbbox())
        self.assertIsNotNone(ImageChops.difference(frames[1],frames[2]).getbbox())


if __name__ == '__main__':
    unittest.main()
