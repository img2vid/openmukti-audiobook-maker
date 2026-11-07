import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('pypdf') and importlib.util.find_spec('cv2')
                     and shutil.which('pdftoppm'), 'Optional native PDF/OCR providers absent')
class PopplerTests(unittest.TestCase):
    def test_image_pdf_renders_without_pdfium_and_honors_page_range(self):
        from pypdf import PdfWriter
        from openvoice.ocr import _pdf_pages, OCRSettings, MAX_WORK_PIXELS
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'scan.pdf'
            writer=PdfWriter()
            writer.add_blank_page(width=800,height=1200)
            writer.add_blank_page(width=800,height=1200)
            writer.write(path)
            with patch.dict('sys.modules',{'pypdfium2':None}):
                pages=list(_pdf_pages(path,OCRSettings(first_page=2,last_page=2,dpi=300),None))
            self.assertEqual([p[0] for p in pages],[2])
            image=pages[0][2]
            self.assertLessEqual(image.width*image.height,MAX_WORK_PIXELS)
            self.assertGreater(image.width,500)
            image.close()


if __name__ == '__main__':
    unittest.main()
