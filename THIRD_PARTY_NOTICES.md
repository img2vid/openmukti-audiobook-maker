# Third-party notices

The original Openmukti application source is licensed under [MIT](LICENSE).
Third-party code, dictionaries, voice models and native tools retain their own
licenses. Keep the license files and notices supplied with generated packages.

## Proofloom and spelling data

- [Proofloom](https://github.com/img2vid/proofloom), MIT: OCR correction,
  candidate-generation, ranking and edit-application ideas adapted from commit
  `2fa2d34a2a50fd1a62f9c08c0d9a071265449518`. The full notice is
  `openvoice/resources/PROOFLOOM_LICENSE.txt`.
- The English dictionary used by Proofloom (`dictionary-en@4.0.0`) is sourced
  from [SCOWL through wooorm/dictionaries](https://github.com/wooorm/dictionaries/tree/main/dictionaries/en).
  The compressed `proofloom_english.json.gz` is a modified expansion into 121,147
  normalized English forms, NOSUGGEST exclusions and 90 REP replacement pairs.
  Original affix/dictionary/license blob hashes are respectively
  `9e7cb1e2f1c2cc3faff5a7ae2d5c041091017bdb`,
  `b41fd203e6daf76934db99dec6572a230516368a`, and
  `6b5b49088c4ae6f871bdb1c741b15fd837868572`. Proofloom dependency reference:
  `ae4f1ae9162d89049613144f7437efd6ef3e8c6d`. Full SCOWL/Ispell and source notices
  are in `openvoice/resources/PROOFLOOM_DICTIONARY_LICENSE.txt`.
- The existing English frequency dictionary retains its attribution and license
  in `openvoice/resources/ENGLISH_DICTIONARY_LICENSE.txt`. British/American
  variants were adapted from Proofloom's MIT-licensed dialect data.

## Tesseract and native dependencies

Tesseract and its English/orientation models are bundled by the Windows,
Linux and macOS frozen-runtime builders. See `openvoice/resources/TESSERACT_LICENSE.txt`. Exact downloaded
package provenance and available dependency licenses are retained in the staged
runtime and generated ZIP. Piper, ONNX Runtime, Python, imaging libraries and
voice models have separate upstream licenses; downloaded voice models retain
their model-card terms.

Unix system-runtime packages include pypdf 5.9.0 and striprtf 0.0.29, downloaded
as pure-Python wheels with PyPI SHA-256 verification. Their wheel metadata and
license files are retained inside `openmukti.pyz`. Other native dependencies on
BSD/Solaris remain the target package manager's responsibility. macOS bundles
use the build host's Homebrew Tesseract and FFmpeg libraries; Linux bundles use
the build host's Tesseract plus the verified FFmpeg release below. Preserve their
corresponding licenses and source obligations when distributing binaries.

## FFmpeg and FFprobe distribution

FFmpeg and FFprobe are external programs. The Openmukti MIT license does not
replace their licenses.

The builder stages an architecture-compatible GPL-enabled FFmpeg release from
https://github.com/BtbN/FFmpeg-Builds/releases/tag/latest, verifies its SHA-256
against GitHub release asset metadata, and embeds both executables. Upstream:
https://ffmpeg.org/. Licensing: https://ffmpeg.org/legal.html.

Public redistribution of these builds requires GPL compliance, including the
complete corresponding source for the exact binary build and GPL components
linked into it, applicable build/configuration information, license texts and
notices. Downloaded builds may include additional compatible licenses. Checksums
and upstream notices are retained in `vendor/ffmpeg/<platform>-<arch>` and the
generated ZIP. This application source package does not include FFmpeg's source;
publishers must obtain or build and provide the matching corresponding sources
before distributing compiled packages.

## Human name lexicon

`openvoice/resources/human_names.txt.gz` contains 54,104 distinct normalized
first names and surnames extracted from Faker 40.1.2's multilingual person
provider data (https://github.com/joke2k/faker). Faker's MIT license is
preserved in `openvoice/resources/FAKER_LICENSE.txt`. Fictional names need not
appear in this dataset: context-based matching also recognizes unknown names.
The lexicon is advisory; neither a name's spelling nor the dataset is used to
assert a real person's age or gender.


## Bundled Noto Unicode fonts (SIL Open Font License 1.1)

The package includes unmodified regular-weight Noto Sans and selected Noto
Serif fonts for offline Unicode text rendering. Copyright Google Inc./Google
LLC and Noto font contributors. The complete OFL 1.1 license and copyright
notices, distributed with the font files, appear in
`openvoice/resources/fonts/NOTO-COPYRIGHT-AND-LICENSE.txt`.

Noto fonts are separate font software under OFL 1.1; this does not change
the license of Openmukti's application source or of rendered videos.

## OpenMukti Stroke Studio and trajectory engine

The stroke-path JSON format, editable canvas, pressure-aware pen simulation,
and illustrative example path pack are authored for this release and are covered
by the application's MIT license. Neither the demo trajectories nor the
reconstructed fallback should be represented as documented traditional
Bengali/Arabic/etc. handwriting stroke order.

## FriBiDi — Windows complex-script shaping (LGPL-2.1-or-later)

The Windows build automatically downloads the original binary for FriBiDi
1.0.17-1 from the official MSYS2 repository (x64 or ARM64), verifies the
MSYS2-published SHA-256, and bundles `libfribidi-0.dll` beside Pillow's
internal RAQM runtime. The original LGPL license is extracted from the same
archive and embedded as `text_layout/FRIBIDI-LICENSE.txt` in each standalone
EXE. FriBiDi is part of the external text-shaping runtime, not the MIT-licensed
Openmukti application source.

Sources: https://github.com/fribidi/fribidi and
https://packages.msys2.org/packages/mingw-w64-x86_64-fribidi and
https://packages.msys2.org/packages/mingw-w64-clang-aarch64-fribidi .
FriBiDi is licensed under LGPL-2.1-or-later; downstream redistributors must
honor the license, including rights to substitute a modified compatible DLL.
`OPENMUKTI_FRIBIDI_DLL` provides a runtime replacement mechanism.


## Optional CPU neural TTS engines (not redistributed as installed Python packages)

The desktop application can download the following independent third-party
libraries and voice model weights into isolated per-user caches on first use:

- **Kokoro-82M** (`hexgrad/Kokoro-82M`), project
  https://github.com/hexgrad/kokoro, model card
  https://huggingface.co/hexgrad/Kokoro-82M. Verify the specific upstream
  model weights and voice files' license before redistribution.
- **KittenTTS 0.8** (official release wheel), project
  https://github.com/KittenML/KittenTTS; model weights at
  https://huggingface.co/KittenML. Check the chosen repository's license.
- **Kyutai Pocket TTS**, project
  https://github.com/kyutai-labs/pocket-tts. Model weights and pretrained
  voices have their own terms on https://huggingface.co/kyutai.
- **Coqui TTS**, maintained fork package `coqui-tts`, project
  https://github.com/idiap/coqui-ai-TTS, source license MPL-2.0. A model's
  separate license and any required license acceptance still apply; the
  software does not automatically accept restricted model license terms.
- **uv**, project https://github.com/astral-sh/uv, is bundled with packaged
  launchers as a dependency/Python bootstrap executable where supported.
  Its license and source obligations must be honored when redistributing.

Model downloads are not part of the application's MIT license. Package and
model sources are controlled by upstream maintainers; availability and license
terms can change. Check bundled binary notices and redistributable rights
before publishing a compiled build or copying models to another computer.
