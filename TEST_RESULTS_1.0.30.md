# Openmukti v1.0.30 test record

- Command: `python -m unittest discover -s tests -p 'test_*.py' -q`
- Environment: Linux, Python 3.13, headless session.
- Result: **246 tests run, OK** (after fixing optional OpenCV import fallback).
- New tests: voice library persistence, pack checksums/round trip/overwrite protection,
  model duplicate detection, Unicode/script reporting, publication audit,
  segment manifest verification, searchable PDF with Tesseract,
  FFmpeg de-essing/EQ/pan/silence trimming, audio tagging/cover,
  and opt-in CPU/GPU settings.
- Existing tests: all run from the uploaded v1.0.29 test suite.
- Not tested: Windows/macOS graphical operation, portable EXE builds,
  third-party neural model downloads or synthesis, physical GPU hardware,
  cross-platform package installers, production-scale OCR and publication compliance.
- Existing `releases/` files are v1.0.28 artifacts; this ZIP is **updated source**, not newly built installers.
