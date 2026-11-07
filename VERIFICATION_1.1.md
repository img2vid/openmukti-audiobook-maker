# Verification for Openmukti Audiobook Maker 1.1.2

## Test results

| Check | Observed result |
|---|---|
| Source regression suite | 299 tests ran. 298 passed, 1 skipped and zero failed. The skipped native PDF/OCR test requires an optional provider. |
| Linux package builds | Both the x86-64 system-runtime TAR.XZ and DEB were built. The two dependency archives for PDF and RTF import were recovered from the supplied release, verified against wheel RECORD hashes and pinned for offline builds. |
| Extracted package execution | Both extracted launchers reported version 1.1.2 and synthesized an English WAV with the real FFmpeg Flite backend. Both packaged apps loaded their Bengali and Spanish interface resources and checked the language corpus. Each produced an MP4 with H.264 video at 200 × 144 and AAC audio. |
| Production work | A two-voice score rendered to WAV. The sound pipeline rendered a ducked mix, independent audio stems and a spectrogram. A SQLite queue processed a real chapter. |
| Manuscript and OCR | A DOCX fixture exercised footnotes and narrated tables. The bundled scanned page produced an aligned, editable HTML review using local Tesseract. A Bengali and English cover rendered with the packaged text tools. A separate margin fixture verified transcribed notes were excluded from the body. |
| Multilingual and local interfaces | Script-span routing, Bengali numbers, normalization and local ICU transliteration were checked. The loopback editor and incremental speech server returned valid WAV audio. A control-bridge test checked session-scoped actions and rejected a cross-origin request. Bundled Bengali and Spanish strings and parameterized statuses were exercised, including preservation of Unicode file paths. All 11,172 generated modern Hangul syllable paths passed trajectory validation. A subprocess test checked folder, process and network denials. |
| Publication | A real MP3 fixture generated DAISY navigation, SMIL links and a Dublin Core XML catalog. Codec checks distinguished MP3 from AAC. |
| Project reliability | Tests covered archive migration, model locks, missing-asset recovery, interrupted speech jobs and Piper transfers, corrupted caches, signed extensions and authenticated backup rejection after a bad passphrase. |
| GPU fallback | This host exposed no physical GPU. FFmpeg listed 6 candidate encoders, and zero passed the real hardware encode probe. Jobs fell back to software. Accelerator failure and cancellation paths were tested with injected failures. |
| Legacy graphics | An OpenGL ES 2.0 shader produced the expected blended pixel using Mesa llvmpipe in the explicit software test. Automatic mode rejected the software renderer as a GPU. |
| Desktop accessibility | Browser control labels, local audio and high-contrast palettes were checked. This host had no desktop display. The native Tk keyboard test and desktop interaction smoke test require a display such as the one configured in the Linux CI workflow. |

## Scope of the packages

The Linux packages contain application code and pure Python import libraries. They use the host Python, Tk, FFmpeg, OCR and optional inference providers. The package inventory found FFmpeg, FFprobe, local Tesseract, Pillow and NumPy here. OpenCV and Piper were absent. Real Flite synthesis and Tesseract recognition were exercised independently of those providers.

The archive includes source and native build scripts for the other target systems. Windows executables, macOS applications, BSD and other native packages were not built or exercised on this Linux host. Physical NVIDIA, AMD, Intel, Apple and embedded GPU execution, platform-specific assistive technology, optional speech models, live image services and external upload destinations still require testing in their respective environments. The full source feature inventory is in FEATURES_STATUS_CURRENT.md.

## Repeat the checks

    python -m unittest discover -s tests -v
    python -m openvoice studio test languages
    python -m openvoice studio test render
    python -m openvoice hardware-check
    python build.py --formats tar,deb --profile system --no-auto-deps

In a Linux desktop session, run python -m openvoice studio test accessibility and python tests/gui_production_studio_smoke.py. The native results in this report describe the local run. GitHub Actions jobs are provided for subsequent platform runs.
