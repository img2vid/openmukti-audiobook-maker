#!/usr/bin/env python3
"""Fail early when a GitHub checkout omitted bundled source assets.

These assets are required by tests and portable release builds. The complete
set is defined by the original Openmukti Audiobook Maker 1.2.0 source archive.
"""
from __future__ import annotations

from pathlib import Path
import gzip
import sys

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ['openvoice/engines/__init__.py', 'openvoice/engines/base.py', 'openvoice/engines/builtin.py', 'openvoice/engines/neural.py', 'openvoice/resources/ENGLISH_DICTIONARY_LICENSE.txt', 'openvoice/resources/FAKER_LICENSE.txt', 'openvoice/resources/FILE_NAMING.txt', 'openvoice/resources/GUI_GUIDE.txt', 'openvoice/resources/IPA_GUIDE.txt', 'openvoice/resources/OCR_AND_SPELLING.txt', 'openvoice/resources/PIPER_SETUP.txt', 'openvoice/resources/PRODUCTION_STUDIO.txt', 'openvoice/resources/PROOFLOOM_DICTIONARY_LICENSE.txt', 'openvoice/resources/PROOFLOOM_LICENSE.txt', 'openvoice/resources/TESSERACT_LICENSE.txt', 'openvoice/resources/TIMING_SOUND_TAGS.txt', 'openvoice/resources/USER_MANUAL.txt', 'openvoice/resources/english_frequency.json.gz', 'openvoice/resources/english_variants.txt', 'openvoice/resources/fonts/NOTO-COPYRIGHT-AND-LICENSE.txt', 'openvoice/resources/fonts/NotoSansArabic-Regular.ttf', 'openvoice/resources/fonts/NotoSansArmenian-Regular.ttf', 'openvoice/resources/fonts/NotoSansBengali-Regular.ttf', 'openvoice/resources/fonts/NotoSansDevanagari-Regular.ttf', 'openvoice/resources/fonts/NotoSansEthiopic-Regular.ttf', 'openvoice/resources/fonts/NotoSansGeorgian-Regular.ttf', 'openvoice/resources/fonts/NotoSansGujarati-Regular.ttf', 'openvoice/resources/fonts/NotoSansGurmukhi-Regular.ttf', 'openvoice/resources/fonts/NotoSansHebrew-Regular.ttf', 'openvoice/resources/fonts/NotoSansKannada-Regular.ttf', 'openvoice/resources/fonts/NotoSansKhmer-Regular.ttf', 'openvoice/resources/fonts/NotoSansLao-Regular.ttf', 'openvoice/resources/fonts/NotoSansMalayalam-Regular.ttf', 'openvoice/resources/fonts/NotoSansMyanmar-Regular.ttf', 'openvoice/resources/fonts/NotoSansOriya-Regular.ttf', 'openvoice/resources/fonts/NotoSansSinhala-Regular.ttf', 'openvoice/resources/fonts/NotoSansTamil-Regular.ttf', 'openvoice/resources/fonts/NotoSansTelugu-Regular.ttf', 'openvoice/resources/fonts/NotoSansThai-Regular.ttf', 'openvoice/resources/fonts/NotoSerifBengali-Regular.ttf', 'openvoice/resources/fonts/NotoSerifDevanagari-Regular.ttf', 'openvoice/resources/human_names.txt.gz', 'openvoice/resources/interface-bn.json', 'openvoice/resources/interface-es.json', 'openvoice/resources/interface-patterns-bn.json', 'openvoice/resources/interface-patterns-es.json', 'openvoice/resources/neural_worker.txt', 'openvoice/resources/openmukti-icon.png', 'openvoice/resources/play_wav.ps1', 'openvoice/resources/portable-ocr-check.png', 'openvoice/resources/proofloom_english.json.gz', 'openvoice/resources/sapi.ps1']


def main() -> int:
    missing = [name for name in REQUIRED if not (ROOT / name).is_file()]
    empty = [name for name in REQUIRED if (ROOT / name).is_file() and (ROOT / name).stat().st_size == 0]
    broken = []
    for name in REQUIRED:
        if name.endswith('.gz') and name not in missing and name not in empty:
            try:
                with gzip.open(ROOT / name, 'rb') as stream:
                    stream.read(1)
            except (OSError, EOFError) as exc:
                broken.append(f'{name}: {exc}')
    if missing or empty or broken:
        print('ERROR: Incomplete Openmukti checkout. Missing or invalid tracked source files:')
        for path in missing:
            print('  MISSING:', path)
        for path in empty:
            print('  EMPTY:', path)
        for path in broken:
            print('  INVALID:', path)
        print('\nRestore openvoice/engines/ and openvoice/resources/ from the original project ZIP.')
        print('Use: python scripts/restore_missing_assets_from_archive.py PATH_TO_ORIGINAL_ZIP')
        print('Then git add both directories, commit, and push.')
        return 1
    print(f'Openmukti release assets verified: {len(REQUIRED)} files present and non-empty.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
