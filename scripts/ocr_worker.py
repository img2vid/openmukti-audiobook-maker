"""Build as a single-file Python 3.12 imaging helper for the Windows GUI/CLI."""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--health', action='store_true')
    parser.add_argument('--request', type=Path)
    args = parser.parse_args()
    from openvoice.ocr import OCRSettings, import_ocr, _image_modules
    if args.health:
        import pypdfium2
        _image_modules()
        print(json.dumps({'ok': True, 'python': sys.version.split()[0], 'features': ['PDFium', 'Pillow', 'OpenCV', 'Tesseract transport']}))
        return 0
    if not args.request:
        parser.error('--request is required')
    data = json.loads(args.request.read_text(encoding='utf-8'))
    if data.get('tesseract'):
        os.environ['OPENMUKTI_TESSERACT'] = data['tesseract']
    class Cancellation:
        def is_set(self):
            return Path(data['cancel']).exists()
    def progress(*values):
        print(json.dumps({'progress': values}, ensure_ascii=True), flush=True)
    try:
        result = import_ocr(data['source'], OCRSettings(**data['settings']), progress=progress, cancel=Cancellation(), _local=True)
        Path(data['result']).write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding='utf-8')
        return 0
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=True), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
