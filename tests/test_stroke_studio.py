"""True pen paths must supersede any font-derived printed glyph pixels."""
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw

from openvoice.stroke_library import StrokeLibrary, load_stroke_library
from openvoice.ink_engine import prepare_step, draw_step, stylize_step
from openvoice.animated_video import PagePainter, pick_font, paginate, estimate_timing


class StrokeStudioTests(unittest.TestCase):
    def test_unicode_paths_round_trip_and_validate(self):
        trajectories=[[(.10,.18,.2),(.23,.45,.8),(.84,.72,.55)],[(.15,.8,.9),(.9,.08,.4)]]
        library=StrokeLibrary({}).with_glyph('ক্ষ',trajectories).with_glyph('あ',trajectories)
        with tempfile.TemporaryDirectory() as root:
            output=Path(root)/'stroke.json'
            library.save(output)
            loaded=load_stroke_library(output)
            self.assertEqual(loaded.lookup('ক্ষ')[1].points[0],(.15,.8,.9))
            self.assertTrue(loaded.lookup('あ'))
            self.assertIsNone(loaded.lookup('missing'))
            bad=output.read_text().replace('0.8','99999')
            output.write_text(bad)
            with self.assertRaises(ValueError):load_stroke_library(output)

    def test_font_pixels_are_not_in_final_stroke_output(self):
        img=Image.new('RGBA',(85,65),(0,0,0,0))
        d=ImageDraw.Draw(img)
        d.rectangle((8,10,78,60),fill=(255,255,255,255))
        paths=StrokeLibrary({}).with_glyph('ক', [[(.12,.2,.95),(.85,.20,.65)],[(.14,.78,.7),(.87,.77,.9)]]).lookup('ক')
        step=prepare_step(img,0,85,0,65,0,1,'ltr',trajectories=paths)
        stylize_step(step,calligraphy=True,font_size=45,color=(18,38,80),pen_width=3)
        alpha=step.source.getchannel('A')
        self.assertLess(sum(v>200 for v in alpha.getdata()),.36*img.width*img.height)
        partial,tip=draw_step(step,.42,calligraphy=True,font_size=45,pen_width=3)
        self.assertIsNotNone(tip)
        self.assertLess(sum(partial.getchannel('A').tobytes()),sum(alpha.tobytes()))
        self.assertEqual(step.source.getpixel((0,0))[:3],(18,38,80))

    def test_genuine_strict_mode_requires_every_cluster(self):
        font=pick_font('কখ',38)
        pages=paginate(estimate_timing('কখ',2),font,320,1,2)
        library=StrokeLibrary({}).with_glyph('ক',[[(.1,.2,.8),(.8,.8,.8)]])
        painter=PagePainter(pages,(450,150),font,mode='handwriting',color='FFFFFF',panel_opacity=120,
                            stroke_library=library,strict_strokes=True)
        with self.assertRaisesRegex(ValueError,'Missing hand-drawn'):
            painter.render(Image.new('RGB',(450,150),'black'),.7)

    def test_indic_painted_traces_produce_different_brush_and_pen_textures(self):
        font=pick_font('বাংলা',35)
        pages=paginate(estimate_timing('বাংলা',3),font,450,1,3)
        source=Image.new('RGB',(470,180),'#3a2b22')
        handwriting=PagePainter(pages,source.size,font,mode='handwriting',color='E2A75F',panel_opacity=160)
        calligraphy=PagePainter(pages,source.size,font,mode='calligraphy',color='E2A75F',panel_opacity=160)
        self.assertIsNotNone(ImageChops.difference(handwriting.render(source,2.9),calligraphy.render(source,2.9)).getbbox())

if __name__ == '__main__':unittest.main()
