# Openmukti Audiobook Maker

## Version 1.1.2

Run `python -m openvoice gui` and open **Studio** for project tabs, cover design, a waveform editor, a sound timeline, subtitle timing, synchronized reading, OCR review and production tools. The bundled [production guide](openvoice/resources/PRODUCTION_STUDIO.txt) includes the desktop workflows, command examples, optional dependencies and backend requirements.

```sh
python -m openvoice studio --help
python -m openvoice studio score examples/performance-score.json chapter.wav --cache-dir cache
python -m openvoice studio design cover.json --title "The Window" --byline "Mira Sen"
python -m openvoice video --audio chapter.wav --storyboard cover.json --dimensions 1280x720 -w chapter.mp4
python -m openvoice hardware-check
```

Compatible installed devices are tried automatically. Speech, video encoding, selected OCR image filters, pixel composition, eligible PCM effects and signal analysis have acceleration paths. Some older graphics drivers can composite layers using OpenGL ES 2.0. Software paths remain available on machines without compatible devices. The Studio guide explains runtime selection and the CPU override.

[Feature-by-feature status](FEATURES_STATUS_CURRENT.md) · [Recorded checks](VERIFICATION_1.1.md). The material below describes earlier releases.

## Version 1.0.30 — Source upgrade (2026-11-04)

This release is **not a completion of all 500 requested features**. The complete
item-by-item status audit is [`FEATURES_STATUS_1.0.30.md`](FEATURES_STATUS_1.0.30.md):
259 implemented, 86 partially implemented and 155 remaining, according to the
previous source audit plus this patch's conservative changes. The original
500-item request is included in `REQUESTED_FEATURES_500.txt`.

### New desktop menus

- **File → Import clipboard as document / Insert clipboard text** (local text clipboard).
- **Tools → Create searchable PDF from scanned pages** (Tesseract OCR text layer;
  rasterizes any source PDF, so keep originals).
- **Tools → Edit audio metadata / embed cover**, **Check multilingual scripts / Unicode**,
  **Check export/publishing readiness**, and **Hardware / GPU compatibility diagnostics**.
- **Voices → Voice Library — favorites / packs / tags**: manage Piper favorites,
  tags and named voice collections, detect duplicate ONNX files, and export/import
  checksum-verified portable Piper voice packs without automatic downloads.
- **Voices → CPU performance (thread) profile**: low (1 thread), balanced (2),
  fast (up to 8 logical CPUs). Automatic acceleration is enabled. Compatible local runtimes try a GPU and retry on CPU when needed.
- **Tools → Audio processor**: adds `deess`, `equalize`, `pan`, `trim-silence`.

### New CLI examples

```bash
python -m openvoice voice-library list
python -m openvoice voice-library favorite en_US-amy-medium
python -m openvoice voice-library tags en_US-amy-medium --tags calm,clear
python -m openvoice voice-library collection educational en_US-amy-medium en_US-lessac-medium
python -m openvoice voice-library export-pack en_US-amy-medium -w voices.zip
python -m openvoice voice-library import-pack voices.zip
python -m openvoice ocr scan.png --searchable-pdf searchable.pdf
python -m openvoice script-check -f manuscript.txt -w script-report.json
python -m openvoice publication-check ./finished-book --title "Book" --author "Author" --language en
python -m openvoice segment-audit render-manifest.json ./generated-audio
python -m openvoice audio deess raw.wav -w cleaned.wav
python -m openvoice audio equalize raw.wav -w equalized.wav --eq-frequency 2600 --eq-gain -3
python -m openvoice audio pan stereo.wav -w left.wav --pan -0.6
python -m openvoice audio trim-silence raw.wav -w trimmed.wav --silence-db -45
python -m openvoice tag-audio input.mp3 -w tagged.mp3 --tag title="Chapter 1" --cover cover.jpg
python -m openvoice hardware-check --profile low
python -m openvoice render -f chapter.txt -w chapter.wav --performance-profile low
```

OpenCV is optional at runtime for basic image/OCR processing when the installed wheel fails, but unavailable advanced preprocessing may reduce OCR accuracy.

A 500-feature product needs further engineering, integration testing and
engine-specific support. Current source functionality and previous Linux
1.0.28 binaries are different: old binaries in `releases/` **do not include**
these 1.0.30 changes. No Windows/macOS build or physical GPU test was performed
by this source upgrade. Model downloads still require user approval.

## Version 1.0.29

### New in 1.0.29 — project library, structure, editorial and publishing tools

* **Project library** (`library` command). Index projects with categories,
  tags, favorites, notes and bookmarks; search across names, metadata and
  `.oamproj` manuscript text; batch-rename projects (plain text or regex,
  with `--dry-run`); detect duplicate projects by content hash; analyze
  storage by audio/video/models/images/fonts/text/cache; and run health
  checks that verify `.oamproj` manifests, bundled assets and ZIP integrity.
* **Book structure** (`chapters` command). Heuristic chapter detection
  (Markdown, `Chapter 12`, `Part IV`, numbered and ALL-CAPS headings) with
  custom regex rules; Markdown/plain/JSON table of contents; scene-break,
  repeated header/footer detection; per-chapter duration estimates; and a
  drafted → reviewed → completed status file with summaries.
* **Editorial reports** (`proofread` command). Proper-name consistency
  clustering (transposition-aware, e.g. `Elias`/`Elais`), dialogue
  punctuation checks, OCR punctuation artifact reports, Flesch readability
  statistics, cross-chapter terminology consistency, and a pronunciation
  audit listing difficult words and those already covered by IPA overrides.
* **Speech preparation** (new text tools, also in the GUI text tools):
  `expand-abbreviations`, `speak-numbers`, `speak-numbers-plain`,
  `speak-dates-times` and `pauses-to-tags` (ellipses/dashes become timing
  tags such as `[p:0.7s]`). A **Tools → Speech preparation** menu item
  applies the full chain to the open document.
* **Publishing** — ASS subtitle export via `captions out.ass` (styled,
  numpad-aligned, centisecond timing); `name-files` naming patterns with
  `{title} {author} {chapter} {number:03} {language} {date}` tokens;
  `sample` promotional excerpts with fades; `release-notes` and
  `attribution` document generators; and `transcript` export to clean HTML,
  TXT, or a dependency-free text PDF.
* **Production** (`production` command). Chapter workflow stages
  (imported → corrected → narrated → mastered → exported), quality-control
  checkpoints, chapter approval with failing-checkpoint protection, a
  progress dashboard, render-time estimates from measured realtime factors,
  storage forecasts per audio format, and an append-only JSONL production
  log with field redaction.
* **GUI**: Tools menu gains chapter overview, editorial reports, speech
  preparation and transcript export. All new features run offline on CPU
  and are covered by the regression suite (`tests/test_new_features_v129.py`,
  `tests/test_cli_new_commands.py`).

## Version 1.0.28

### Build and run

The `releases/` directory in the download contains Linux x86-64 system-runtime
DEB and tar.xz packages. The archive includes a launcher named `openmukti` and
a desktop launcher named `openmukti-gui`. These packages use installed Python
3.10+ and native media, OCR and speech providers. FFmpeg with the Flite filter
can synthesize English on CPU without a model download.

From the source folder use `python openvoice_gui.py` or
`python openvoice_cli.py --help`. Use `py -3 build_detect_os.py` on Windows
and `python3 build_detect_os.py` on Unix. To choose formats interactively, use
`build_select.py`. For explicit per-OS entry points, use
`python3 scripts/native/build_freebsd.py`, for example. Each checks its native
host before building. Run `python build.py --list-targets` to inspect the format
catalog. Other Unix hosts can attempt the generic system-runtime tar build where
Python, a POSIX shell and the required providers work. Building the multi-OS
matrix from Windows or Ubuntu uses `build_all_platforms.py` and configured native
CI runners.

### Use the new production tools

* **File menu**. Save a named snapshot or set automatic backups for this session.
  Pick a folder with space for complete project archives, including linked models.
  Each changed snapshot creates a separate file. Open a snapshot with **Open
  entire project** to recover. Use **Compare two project versions** to review
  text and settings, or **Inspect saved project resources** to see stored sizes,
  potential duplicates and missing assets. Project notes, category and tags
  travel inside the project.
* **Import**. Open ODT, FB2 or FB2.ZIP documents. A ZIP with supported documents
  reads them in archive order. An image-only ZIP opens the OCR importer. For a
  mixed archive use the explicit scan importer to select the OCR route.
* **Edit → Find / Replace**. Enable regular expressions to match patterns and use
  Python replacement backreferences. Replace all opens a preview before applying.
  Document statistics list groups of duplicate paragraph numbers.
* **Voices menu**. Use available GPU controls automatic acceleration for this session.
* **Tools menu**. Export timed JSON, SRT or VTT as SRT or WebVTT. Package a
  finished book folder as a ZIP with a SHA-256 manifest.
* **Command line**. Run the examples below from the source folder.

```sh
python openvoice_cli.py audio-quality chapter.wav
python openvoice_cli.py captions timing.json chapter.vtt
python openvoice_cli.py publish-book book.json book.m4b
python openvoice_cli.py publish-book book.json feed.xml
python openvoice_cli.py release-archive finished-book finished-book.zip
python openvoice_cli.py environment-sbom
```

For publishing, list local audio files relative to the manifest in playback
order. RSS also requires the public feed site and episode URLs. No audio is
uploaded. M4B encoding uses temporary disk space for lossless chapter audio.
Example book.json:

```json
{
  "title": "The Window Seat",
  "artist": "Aishik Dutta",
  "language": "en",
  "link": "https://example.org/books/window-seat",
  "chapters": [
    {"title": "Chapter One", "file": "01.wav", "url": "https://example.org/audio/01.wav"},
    {"title": "Chapter Two", "file": "02.wav", "url": "https://example.org/audio/02.wav"}
  ]
}
```

### Scope and verification

The Linux x86-64 packaged CLI was exercised with real speech and chaptered
M4B output. Native builds for other OS/architecture pairs, the desktop display,
CUDA hardware and downloaded neural models require separate testing.
The environment inventory covers installed Python distributions and their
declared licenses. It excludes system components and manual legal review.

This release implements part of the 500-item list. Examples of remaining
work include multi-project tabs, advanced table and formula OCR, streaming
synthesis recovery, a multitrack audio editor, DAISY export, encrypted
project backups and permission-isolated plugins. Universal GPU execution
depends on individual engine, driver and OS support.


Offline audiobook creation with GUI and CLI, Piper and system voices, character
profiles, IPA pronunciation, audio/video export, chapters, complete-project
archives, scanned PDF/image/ZIP/CBZ OCR, contrast/black-and-white preprocessing,
and clickable English spelling corrections. Application source: MIT.

Text remains fully editable: click to position the cursor, double-click to select
a word, and drag to select text. For spelling suggestions, right-click or
Ctrl-click an underlined word, or put the cursor in it and press Shift+F10 or
Ctrl+period. Choosing or closing a correction returns focus to the editor.

Creation shows overall and current-stage progress for speech chunks, character
voice processing, chapters, merging, audio conversion and video encoding. FFmpeg
progress uses encoded timestamps. An animated stage bar indicates work whose
percentage is unknown; 100% appears after the final output is saved. CLI bars go
to stderr; JSON and streamed audio remain on stdout.

## Built-in optional neural speech engines (CPU, 2026-11-02)

The normal **Speech engine** dropdown and character-voice studio include four
more backends. No GPU or CUDA is necessary for the adapters; they request CPU
inference. Each upstream engine runs in a **separate Python environment** so
its model-specific requirements cannot replace the app's Piper libraries:

| Engine | Default | Voices and language | Notes |
| --- | --- | --- | --- |
| `kokoro` — Kokoro-82M | `af_heart` | 54 named voices across English (US/UK), Spanish, French, Hindi, Italian, Brazilian Portuguese, Japanese, and Mandarin | Language derives from the voice prefix (such as `hf_alpha` or `jf_alpha`); the official `KPipeline` is used in CPU mode. |
| `kitten` — KittenTTS 0.8 ONNX | `Bella` / nano-0.8 | 8 named voices; English | Choose nano, micro, or mini model; ONNX-based inference without GPU. |
| `pocket` — Kyutai Pocket TTS | `alba` / English | Built-in voice names plus several multilingual model variants | Models `english_18m_2026-10`, `english_7m_2026-10`, and `english_2m_2026-10` can be entered in **Model** for smaller CPU variants. Choose `italian`, `spanish`, `french`, `german`, `portuguese`, or `dutch` models as applicable. |
| `coqui` — Coqui TTS (maintained `coqui-tts` fork) | `tts_models/en/ljspeech/tacotron2-DDC` | Voice/speaker and language availability depend on the selected model | Select a model ID, e.g. `tts_models/en/vctk/vits`; click **Discover Coqui speakers** to populate the speaker list. The engine uses `.to('cpu')`. |

**GUI (manual Kokoro / Kitten / Pocket / Coqui model downloads):** Open **Voices → Download Kokoro /
Kitten / Pocket / Coqui voices**, or use the button in the main **VOICE
SETTINGS** panel. Select an engine, model variant and one or more voices. The
window shows whether each selection is downloaded. Click **Download Selected**
(or **Download All Shown**) to begin downloading without any confirmation or completion popup. The app installs
missing engine dependencies during this explicit GUI operation, then
downloads the selected model/voice assets. An indeterminate progress bar and
status text show that the download is active. All voices in a Kitten model
share model assets; all Coqui speakers are included with the chosen model.
Kokoro and Pocket have individually downloadable voice assets. For Pocket,
the downloader also exports a reusable local voice state so inference does not
fetch sample audio later.

**Kokoro, Kitten, Pocket and Coqui do not download model assets in speech operations:**
Preview, Speak, Audio/Video Export, and Coqui speaker discovery use only manually installed model assets. If the selected model or voice
has not been downloaded, the app reports the missing asset and directs you
to the GUI downloader. The ordinary neural worker explicitly disables network
connections; only a separately launched user-approved download worker may
fetch model files. Engine-package installation (including Python and CPU
libraries) also requires an explicit **Install / repair** or manually started GUI
Download action, not an ordinary preview. You can use **Edit all character
voices** to assign any installed engine, model, voice and language to each
character. These choices remain in portable project archives, but large neural
model weights are installed once into the local app cache and are *not*
embedded into project files. Existing Piper multi-speaker selection is unchanged.

**From source or a packaged executable:** The build scripts bundle the `uv`
installer in supported frozen builds. When explicitly requested in the GUI,
`uv` can download a managed Python 3.12 runtime and CPU dependencies into the
user's application cache. Model weights and voice presets download **only**
after the user approves a specific GUI download action; internet access and
adequate storage are required for that initial download. Subsequent synthesis
uses the local cache with all model-related network access disabled. The engine
installer alone downloads Python packages, **not** neural voice weights.
These engines remain optional: Piper and system voices can work without them.

```sh
python -m openvoice engine-install kokoro
python -m openvoice engine-install kitten
python -m openvoice engine-install pocket
python -m openvoice engine-install coqui
python -m openvoice engine-install all

# First download the selected model and voice through the GUI.
# Running the following commands before downloading will give a clear error.
python -m openvoice voices --engine kokoro
python -m openvoice render --engine kokoro --voice hf_alpha -t "नमस्ते" -w hindi.wav
python -m openvoice render --engine kitten --voice Jasper -t "Hello" -w kitten.wav
python -m openvoice render --engine pocket --voice alba --model english_7m_2026-10 -t "Hello" -w pocket.wav
python -m openvoice render --engine coqui --model tts_models/en/ljspeech/tacotron2-DDC -t "Hello" -w coqui.wav
```

**If a neural engine fails to install:** Open the neural-voice manager and click
**View / copy neural dependency installation log**. The log is also stored in
`<user neural cache>/<engine>/dependency-install.log`; it records the exact
failed dependency stage, uv/pip output, and exit code. The installer retains
an incomplete environment for **Install / repair** or a subsequent confirmed
voice download to retry; it never marks a failed install as ready. Temporary
network failures are retried automatically. Kokoro uses prebuilt
`pyopenjtalk-plus` and `unidic-lite` packages for Japanese G2P, avoiding a
native compiler requirement and a separate UniDic dictionary fetch.
Installing engine packages is distinct from downloading the actual voice
models; voice-model downloads still require an explicit click in the GUI downloader, but do not display confirmation popups.

**If a voice download says “Invalid response from ... worker”:** Version 1.0.24
keeps the worker's JSON control channel separate from native-library,
subprocess, and package logs. The downloader also tolerates bounded noise
from older workers and records it in `<user neural cache>/<engine>/worker.log`.
In the neural-voice manager, choose the engine and use **View / copy neural
worker log** to inspect the actual traceback and installation messages. If a
package or model fails, the dialog includes the relevant log tail and the
voice is not marked as downloaded. Rebuild the application with the updated
source; repairing dependencies alone will not update the application's
worker-protocol code. On Linux, Kokoro's log defaults to:
`~/.local/share/OpenmuktiAudiobookMaker/neural-engines/kokoro/worker.log`.

**Compatibility:** The application adapters are cross-platform Python code;
actual installs require suitable upstream PyTorch/ONNX/native wheels on the
target architecture and sufficient RAM. Common Windows, Linux and macOS CPU
configurations are the primary targets. BSD, Solaris and uncommon processor
architectures are **not guaranteed** to have compatible neural-engine wheels.
The GitHub download services, voice/model license terms and package mirrors
are controlled by third parties. There is no bundled paid cloud API. Real
end-to-end waveform generation requires downloading the upstream model and
was not exercised in the local mock-based integration tests; test each model
on the target device before publishing a build as verified.

## Drawing-oriented handwriting and calligraphy (1.0.23)

**New: Stroke Studio** (Animated Audiobook Video → **Open Stroke Studio**).
Instead of applying distortions to printed fonts, the final ink layer is
constructed exclusively from simulated pen/brush imprints following recorded
vector stroke trajectories. Each pen-down / pen-up gesture and pressure sample
is stored in a Unicode JSON library. Draw Bengali clusters, Arabic joining
forms, Japanese characters, English cursive words, or any other Unicode string
and save it as a **stroke pack**. Whole-word templates are preferred over
single-letter templates, allowing continuous cursive joins. Stroke packs can
be exported and imported as ordinary JSON files, and are also bundled with
complete `.oamproj` project exports. An example is in
`examples/illustrative_handdrawn_strokes.json`. It is deliberately a small
illustration, not a complete multilingual calligraphy collection.

Handwriting and calligraphy each operate with multiple physical pen presets:
`pencil`, `ballpoint`, `fountain`, `brush`, `broad-nib` and automatic selection.
Controls include pen thickness, nib inclination, dry-brush pigment, paper grain
and editable pressure while drawing trajectories. The painting system includes
nib-angle and pressure modulation, deterministic ink texture, slight pigment
feathering, supersampled brush silhouettes and visible pen movement. It runs
on CPU and needs no GPU.

**Strict drawn-only mode** refuses to render a missing character or word
trajectory, rather than invent authentic script strokes. **Normal mode**
falls back to font-guided *path reconstruction* when no hand-drawn sample
exists; the final rendered pixels still come from virtual pen marks, but the
trajectory and letterform are derived from a printed shape guide and therefore
are **not equivalent to hyper-realistic handwriting**. Neither mode can infer
all culturally accurate strokes or stylistic letterforms for every script in
existence. You must supply genuine stroke templates to obtain them, and a
working shaping font/RAQM runtime is still needed for line layout. The app
bundles many modern Unicode fonts but not every script or writing tradition.

For CLI exports, supply options such as:

```sh
openvoice video -t "Hello" --audio narration.wav --animation calligraphy \
  --stroke-library examples/illustrative_handdrawn_strokes.json \
  --strict-strokes --pen-tool broad-nib --pen-width 7 --nib-angle -35 \
  --paper-grain 18 --brush-dryness 22 -w result.mp4
```

The engine syncs stroke drawing to the same per-word or per-phrase timestamps
as the video's audio. Use aligned JSON/SRT/WebVTT to synchronize to known spoken
word times. Timing estimated only from total narration length cannot guarantee
exact synchronization to individual spoken words.

## Windows build repair: RAQM/FriBiDi (version 2, 2026-11-01)

**Version 2** now builds Bengali/Indic/RTL text rendering with the native
FriBiDi library that Pillow's official Windows wheel requires but does not
install automatically. The original `windows-build.log` showed Pillow 13.0.0
installed successfully under Python 3.15.2 and failed at
`features.check_feature("raqm")` before packaging. The repaired builder:

1. Downloads only a pinned FriBiDi 1.0.17-1 **MSYS2** Windows package for the
   host architecture (x64 or ARM64), on the first connected build.
2. Checks the archive's official SHA-256 and the extracted DLL's PE machine
   code, and extracts its LGPL license. Never runs the downloaded executable.
3. Preloads the verified DLL before Pillow's text engine is initialized.
4. Includes the DLL and its license in *each* independent onefile GUI/CLI EXE.
5. Keeps the strict Bengali/Indic layout checks, instead of silently falling
   back to incorrect basic-font shaping. `--verify-runtime` checks the fully
   isolated EXEs after compilation.

Run on Windows from the **extracted updated version 2** folder:

```powershell
py -3 build.py --repair --verify-runtime --keep-open
```

A first-time build requires internet access for FriBiDi and other native
runtime dependencies. Subsequent repair runs reuse the pinned archive from
`.build-assets/text-layout/<architecture>/`. Logs go to
`build-logs/windows-build.log` and `windows-build-status.json`.

If your computer's Windows application-control policy prevents running a
new unsigned EXE, you can compile without `--verify-runtime` and inspect the
produced UNVERIFIED ZIP; compilation cannot override Windows policy.

Only `build.py` is a public build launcher. No BAT file is included. Internal
scripts in `scripts/` and `packaging/` are still required and are not duplicate
user-facing build files. All Stroke Studio, drawing-oriented handwriting,
calligraphy, Unicode fonts, ebook, PDF/OCR, Piper, GUI, CLI and video features
remain present.

### Redistributing the FriBiDi dependency

FriBiDi is LGPL-2.1-or-later, not MIT. The builder embeds its license in the
standalone EXE (`text_layout/FRIBIDI-LICENSE.txt`) and records the upstream
MSYS2 package URL and SHA-256 in `.build-assets/text-layout/*/source.json`.
For application developers, `OPENMUKTI_FRIBIDI_DLL` supports substituting an
alternative ABI-compatible DLL without modifying the application source.
Comply with the corresponding LGPL terms when redistributing compiled EXEs.

## Multilingual video text and pen rendering upgrade (1.0.22)

Bengali (বাংলা) and other Indic/RTL scripts must use the **RAQM/HarfBuzz**
text-shaping runtime. The Windows portable build script now **checks RAQM
before building**. A generated one-file EXE additionally renders a Bengali
sample in all three text modes during runtime verification and rejects a
release that lost its libraries. Rebuild the EXEs from this source; it is not
possible to repair an old one-file EXE simply by installing a font beside it.

This source now bundles 21 OFL-licensed Noto Unicode script fonts, including
Bengali, Devanagari, Tamil, Telugu, Arabic, Myanmar, and others. The exact
list and the redistributable Noto font license are in
`openvoice/resources/fonts/`. System and user-selected fonts remain available
for other scripts and custom handwriting faces. Unicode layout coverage still depends on suitable font glyphs.
Fonts for **every possible Unicode script** are not bundled. The new drawing
engine can read genuine, manually authored trajectories in any script.

Typewriter, handwriting, and calligraphy now use different render paths:
**typewriter** reveals shaped grapheme sections at fixed times;
**handwriting** traces their paths with a variable-pressure round pen; and
**calligraphy** adds an angled broad-edge nib with different pigment coverage.
With an imported Stroke Studio library, the stroke paths ARE genuine user-drawn
pen movements; when templates are absent the renderer reconstructs trajectories
from shaped text instead. Rendering remains CPU-only, with no GPU requirement.

For genuine Bengali or Hindi handwriting, use Stroke Studio to record handwritten
character or word paths, or import a licensed collection of such paths. A
handwriting font can still improve the **fallback** tracing appearance, but is
not necessary for the finished ink shape if all drawing templates are supplied.

For a verified Windows release, run `py -3 build.py --verify-runtime`
from the extracted source on Windows, or use the included GitHub Actions Windows
workflow. Native Windows EXEs cannot be cross-compiled here on Linux.

## Text rendering hotfix (1.0.21)

Fixes **"setting text direction, language or font features is not supported
without libraqm"** during animated video creation. Both text measurement and
drawing now check the actual font layout engine. Fonts loaded without RAQM use
compatible basic calls, including fonts selected for mixed-script fallback.
Available RAQM shaping is retained. A specific stale-runtime dependency error
is retried without the unsupported options; unrelated font errors still surface.

Windows and native Unix frozen builders now explicitly collect Pillow's
available sibling `.libs` files, including dynamically loaded text-layout
libraries and load-order metadata. This preserves libraries provided by the
installed wheel; it does not invent or download missing RAQM dependencies.
Portable verification exercises native text rendering and a real basic-layout
font, and reports whether complex-script shaping is available.

The basic fallback prevents the crash. Correct Arabic/Indic shaping and complex
bidirectional layout still need a RAQM-enabled Pillow runtime and suitable fonts.
No GPU is required. Existing EXEs must be rebuilt for this source fix to apply.
From the extracted source folder on Windows, run:

```powershell
py -3 build.py --repair
```

This reuses compatible build environments/helpers where present and recompiles
the main EXEs with the updated renderer. Packaging existing EXEs alone does not
apply code changes. The source archive retains the full character upgrade and
all existing features.

## Intelligent character profiles and quote attribution (1.0.20)

Open **Character Voices → Find Characters**. The offline recognizer combines
speech-tag syntax, name hints, scene boundaries, descriptive identities,
explicit identity revelations, unique full-name forms, pronoun antecedents,
action beats, named direct address, and constrained conversation turns. It
handles interrupted speech, nested quotes, multi-paragraph speeches, straight
single/double quotes, curly quotes, guillemets, Japanese quotation marks,
dash dialogue and screenplay labels. English has the richest rules; several
European, Cyrillic, Arabic, Bengali, Hindi, Japanese and Chinese speech markers
are included. Unicode name support does not mean equally complete grammar
recognition in every language.

Unnamed speakers receive stable descriptive identities: repeated **the old man**
and **the elderly gentleman** can share one profile; **the talking dog** remains
consistent. Explicit revelations such as **The old man was named Elias**,
**The dog's name was Rex**, and an attributed **My name is Elias** merge earlier
quotes and profiles into the named identity. Different unnamed people and
ambiguous shared surnames are kept separate. Descriptions are scoped to scenes
unless evidence links their identities. Source words and punctuation are
retained; control tags are editable.

The bundled lexicon contains over **54,000 multilingual names**. Context also
recognizes invented names and names absent from the lexicon. **Import Name
List** accepts UTF-8 text (one name per line), CSV (first column), a JSON array
of strings, or GZip versions. Extra hints are loaded for the current studio
session; imported lists are limited to 32 million characters per file. Character
labels and aliases support up to 160 characters, including non-Latin scripts.

Find Characters can populate **every profile control**:

| Control | Evidence and behavior |
|---|---|
| Character | Canonical identity, aliases, explicit name revelations |
| Language | Character dialogue first; document language when speech is too short |
| Piper model | Matching installed language/locale; quality, reuse, and explicit local voice metadata |
| Speech rate | Described delivery, such as quickly, slowly and drawled |
| Volume | Quiet/whispered/loud delivery; Piper and other engines without native volume now apply it after synthesis |
| Pitch correction | Explicit high/deep/squeaky voice descriptions |
| Voice presentation | Author descriptions, titles and resolved pronouns; never guessed from name spelling |
| Age | Numeric/word ages, age phrases and descriptive identities |
| Personality | Weighted combinations of supported styles from descriptions and delivery |
| Transformation strength | Scaled to available character-specific evidence; neutral when there is none |

**Save / Add Profile** protects fields you changed manually. Later scans refresh
automatic fields while retaining those edits. Older projects retain non-default
custom settings. To infer all fields again, select a character and use **Allow
automatic updates for this profile**, then **Find Characters**. To explicitly
link identities yourself, add the former name in the named profile's **Aliases**
field (separate multiple aliases with semicolons), save, and scan again.

**Review Characters / Quotes** shows proposed settings, evidence, heuristic
confidence, manual settings, quote line numbers and ambiguous candidates.
Confidence is a heuristic ranking, not a calibrated probability. Uncertain
quotes stay with Narrator. Speaker tags remain authoritative except when a
verified alias is canonicalized. No inference system can reliably resolve every
literary ambiguity or reconstruct a voice the author never describes.

Profiles, aliases, inference evidence and manual settings survive voice JSON
and complete `.oamproj` exports. Speak, Audio, Video, Batch and audiobook exports
use saved profiles and aliases; untagged dialogue can be attributed to configured
speakers. The algorithms run on CPU without GPU, online APIs or model downloads.
FFmpeg is needed for voice effects and media output. Bundled Windows builds
include it; local source installations must provide it.

Optional local model metadata can be added under an `openmukti` object in an
installed model's `.onnx.json` (retain all its existing Piper configuration):

```json
"openmukti": {"gender": "Female", "age": "Adult", "styles": ["calm", "warm"]}
```

Missing voice demographics are not invented from the model's name. Models not
installed are never assigned as if available. **Detect Language + Recommend**
continues to offer installed and downloadable recommendations; the catalog
requires internet or cache. `pip install .[languages]` adds optional offline
language detection; it is not needed for the basic CPU-only workflow.

CLI example (use `--names` repeatedly for additional lists):

```sh
openvoice character-profiles -f book.txt -w voices.json --report analysis.json
openvoice character-profiles -f edited-book.txt -w updated.json \
  --update-project voices.json --names extra-names.txt --report review.json
openvoice multivoice --project updated.json --auto-tag -w book.wav
```

Run `python -m unittest discover -s tests -v` for the regression suite, including
real FFmpeg waveform checks for volume, mute, pitch and rate/profile routing.
With a desktop display, `PYTHONPATH=. python tests/gui_character_smoke.py`
checks the live studio workflow. Windows binaries must be built and tested on
Windows using the included build scripts; this source release does not contain
newly compiled EXEs.

## Animated audiobook videos / handwriting and calligraphy

**Animated Audiobook Video** overlays readable, synchronized book text **on top
of your selected cover images**. Original image-only slideshows are retained as
`none` (classic slideshow) mode. Animated modes do not require a cover: a solid
background is used if no image is selected. Add or reorder multiple covers;
they change during playback while the text remains overlaid.

Available motion effects: `typewriter`, `handwriting`, `calligraphy`,
`scroll-up`, `scroll-down`, `scroll-left`, `scroll-right`, `slide-up`,
`slide-down`, `slide-left`, `slide-right`, `fade`, `zoom`, `karaoke`, `static`.
Handwriting and calligraphy now draw actual pen and nib stamps from ordered
trajectories. Authentic stroke order requires a user-authored library; otherwise
the automatic font-guided tracer remains an imperfect fallback. Font shaping delegates to Pillow RAQM and
script-specific Unicode fonts, with fallback runs for mixed scripts. Install
Noto fonts for broad coverage, or select an appropriate licensed OTF/TTF font
in the GUI; exact visual coverage of every script depends on available fonts.

Choose preset aspect ratios (16:9, 9:16, 1:1, 4:3, 3:4, 3:2, 2:3, 21:9,
9:21, 5:4, 4:5), type **any positive W:H ratio** (e.g. `17:10`), or set
**exact custom even-pixel dimensions** (e.g. `1080x1920`). Output sizes must
be 16–7680 pixels per side. Choose a frame rate (24/25/30/60), text color,
font size and text-panel transparency. Your image cover remains visible.

**Sync details:** A video frame is rendered at its exact assigned timeline
time, using existing audio duration. By default, word/cluster timings are
estimated using narration length. For accurate synchronization, supply a
word- or phrase-aligned transcript in `.json`, `.srt` or `.vtt`, containing
real timings for that narration; the renderer respects these timestamps to
frame precision. It does **not** automatically perform phonetic forced
alignment; therefore audio-perfect word alignment cannot be guaranteed without
validated timing data. JSON accepts either an array of objects or a
`{"words": [{"start": 0.0, "end": 0.5, "text": "Hello"}]}` object.
Times are seconds relative to the supplied audio. A project archive bundles
its selected video font, stroke pack and timing file so it can be restored later.

Example (existing spoken audio, cover art and animated text):

```sh
openvoice video -t "Hello, world. This is my narrated book." \
  --audio book.wav --images cover.png --animation handwriting \
  --aspect 9:16 --resolution 720p --font-file /path/to/font.ttf \
  --timing-file aligned_words.json -w narrated-book.mp4
```

To produce an animated video without artwork, omit `--images`. For optional
rendering dependencies: `pip install .[video]`; FFmpeg and FFprobe are also
required for exports. Video frame rendering is CPU-based and can take a long
time for full-length books, particularly at high resolution and frame rates.

## Automatic builds on GitHub

Upload this folder's contents, including `.github`, to your repository. **Actions
→ Build portable releases → Run workflow** builds every configured platform.
Builds also run on pushes to `main`/`master`, `v*` tags and pull requests. Download
the outputs from each job's artifacts; successful formats remain downloadable if
another format fails. These workflows build artifacts without publishing a release.

| Native host | Architectures in the workflow | Outputs |
|---|---|---|
| Windows | x64, ARM64 | Independent GUI/CLI `.exe` files in a ZIP |
| Linux | x86_64, ARM64 | `.deb`, `.rpm`, `.AppImage`, `.flatpak`, Arch `.pkg.tar.zst`, portable `.tar.xz` |
| Linux in QEMU/Debian | i686, ARMv7, POWER/ppc64le, s390x, RISC-V | System-runtime `.deb`, `.tar.xz` |
| macOS | Intel, Apple Silicon | Application `.dmg`, portable CLI/GUI runtime `.tar.xz` |
| FreeBSD | x86_64, ARM64 | Native `.pkg`, system-runtime `.tar.xz` |
| OpenBSD, NetBSD | x86_64, ARM64 | Native package `.tgz`, system-runtime `.tar.xz` |
| DragonFly BSD | x86_64 | Native `.pkg`, system-runtime `.tar.xz` |
| Solaris, illumos/OmniOS | x86_64 | IPS `.p5p`, SVR4 `.pkg`, system-runtime `.tar.xz` |

Windows/Linux/macOS bundles embed Python, Tesseract with English/orientation data,
imaging libraries, Piper and media tools. End users do not install Tesseract or
Python. Windows ARM64 uses native ARM64 main EXEs and FFmpeg; its bundled x64
speech/imaging/Tesseract helpers require Windows 11 x64 emulation. Voice models
are downloaded or selected separately. Linux bundles use an Ubuntu 22.04 glibc
baseline and require a desktop/X11 environment for the GUI. Flatpak uses the
Freedesktop 25.08 runtime, installed by Flatpak.

Additional Linux architecture and BSD/Solaris jobs create **system-runtime packages**, not self-contained frozen
executables. They retain every feature's code, vendor the pure-Python document
importers, and record installed native package dependencies. Python 3.10+, Tk,
Pillow, NumPy, OpenCV, Tesseract, media tools and a voice engine must be available
on the target. Poppler supports scanned PDFs where PDFium is unavailable. Piper
and other providers are not available on every OS/CPU; `runtime-check.json` and
`provider-installation.json` show missing components. SVR4/portable source payloads
require these providers to be installed separately. `build-report.json` separates
packaging success from full bundled-runtime verification.

There is no compiler that produces a working desktop application for every OS
and CPU. These jobs build on the target OS, using native or emulated VM runners.
The workflows have to complete successfully on those runners before their
outputs can be considered verified.

## Build locally

### Start the multi-platform build from Windows or Ubuntu

To start the configured native build matrix from one Windows or Ubuntu
computer, first commit and push this project version to GitHub. The launcher
attempts to install missing GitHub CLI or Git through the host package manager
and starts an interactive GitHub login if needed. You must authorize that login
yourself. Then run:

```text
py -3 build_all_platforms.py --plan       # Windows
py -3 build_all_platforms.py --ref main   # Windows; replace main with your branch
python3 build_all_platforms.py --ref main # Ubuntu
```

The launcher starts `.github/workflows/build.yml`, waits for the native runner
jobs, and downloads their artifacts under `dist/all-platforms-<run-id>`. The
local computer coordinates the build; GitHub's Windows, Linux, macOS, BSD, and
Solaris/illumos runners create their own native packages. This is how one
Windows or Ubuntu workstation can collect cross-platform releases without
pretending its local toolchain can create another OS's native executable.

The workflow builds the targets for which the repository has native runners.
The Linux job skips optional formats when their required builders or metadata
are absent. Alpine APK and Void XBPS can be added through the configurable
native-runner matrix; AIX, Haiku, GNU Hurd, MINIX, and other rare targets also
need matching runners and compatible Python, Tk, OCR, and multimedia providers.
Formats listed only as recipes, store submissions, or OS images are not
application packages this project builds.

Choose either of the two launcher files:

```text
python build_select.py      # prompts for one or more formats supported on this host
python build_detect_os.py   # detects this OS and builds its implemented native formats
```

On Windows, use `py -3` in place of `python`. The selector only offers formats
implemented for the detected host. The automatic launcher uses the frozen
runtime where this project has native bundles configured, and the system-runtime
profile on other Unix hosts. Neither launcher cross-compiles other operating
systems. **Both launchers automatically install missing build dependencies**
from the configured native package repositories where available; they also
install the Python wheel dependencies into disposable virtual environments.
Linux package managers supported by the bootstrap include apt, dnf, pacman,
zypper, Alpine apk, and Void xbps. macOS uses Homebrew (if installed), and
BSD/Solaris use native package tools. Windows installers automatically fetch
Python modules, Windows OCR/media binaries, Unicode shaping DLLs and the
managed Piper runtime. Administrator or sudo authorization may still be needed;
no script bypasses system security policy. On macOS a missing Homebrew installation,
on Windows a missing initial Python interpreter, and unsupported or offline
system repositories can still require initial setup. Tool download failures and
unavailable optional platform formats are reported instead of claimed as built.
Native package signing keys and some distro-specific dependency metadata are
not downloadable software and may still require configured keys/metadata.
Per-format results are written to `dist/build-report.json`.
The native dependency receipt is `.build-native/dependency-setup.json`.

Preview the automatic dependency commands **without changing the computer**:

```sh
python3 build_detect_os.py --deps-plan
python3 build_select.py --formats deb,rpm --deps-plan
```

To disable native dependency installation for managed/offline environments,
pass `--no-auto-deps` to either launcher or directly to `build.py`.


Portable `.zip`, `.tar.gz`, and `.tar.zst` archives and Python `wheel`/`sdist`
outputs are available alongside the existing native packages. A Python wheel or
source distribution is not a desktop installer. The Windows `exe` selection
creates both standalone executables and the portable ZIP archive.

Alpine APK builds require `abuild`, a configured signing key, and
`OPENMUKTI_APK_DEPENDENCIES` set to the exact space-separated runtime package
names for that Alpine release. Void XBPS builds require `xbps-create` and
`OPENMUKTI_XBPS_DEPENDENCIES`. The automatic launcher skips these when the tool
or dependency metadata is missing; the interactive selector still lets you
choose them and the build report records any configuration error.

Windows build PC: 64-bit CPython 3.10–3.15; Python 3.12 recommended:

```powershell
py -3 build.py
```

The first build downloads its dependencies. Each EXE embeds its own runtime; no
neighboring `_internal` folder or signing certificate is needed. Runtime launch
tests are optional locally: `py -3 build.py --verify-existing`. Other
options: `--repair`, `--package-existing`, `--diagnose-policy`, `--verify-runtime`.
Windows execution policy still decides whether an unsigned EXE can run.

Linux/macOS: start with Python 3.10 or newer (3.12 recommended).
The builder downloads missing Tk, venv, Tesseract/data, FFmpeg/FFprobe and
package tools where the system package manager supplies them. macOS uses an
existing Homebrew installation. Then run:

```sh
python3 build.py --list-targets
python3 build.py --formats tar,deb,rpm,appimage,flatpak,arch --verify-runtime
# macOS: python3 build.py --formats tar,dmg --verify-runtime
# Native BSD/Solaris: python3 build.py --profile system
```

`--verify-gui` also exercises Tk spelling suggestions and undo and needs a display
(CI uses Xvfb on Linux). Build outputs and hashes are in `dist`. Full Linux builds
use `dpkg-deb`, `rpmbuild`/`rpm`, `zstd`, `flatpak-builder` and a user Flathub
remote; the bootstrap attempts to install/configure them automatically.
AppImage tooling is downloaded with a verified upstream SHA-256.
An AppImage opens the GUI by default; use `./Openmukti-*.AppImage --cli --help`
for its CLI. Flatpak also exposes the CLI with `flatpak run --command=openmukti
io.github.img2vid.Openmukti --help`.

## Additional native architectures

Configure self-hosted runners with Python and the required native providers and
package tools, then set repository variable `OPENMUKTI_NATIVE_RUNNERS` to a JSON
array. For example:

```json
[{"id":"Linux-riscv64","labels":["self-hosted","linux","riscv64"],"profile":"system","formats":"tar,deb","python":"python3"}]
```

For an Alpine runner, use `"formats":"apk"` and set `apk_dependencies` to the
space-separated Alpine runtime package names; configure its `abuild` signing
key on that runner. For Void, use `"formats":"xbps"` and set
`xbps_dependencies`. The workflow passes those values to the package builders.

The optional job runs on pushes/manual runs, and uses the actual host and binary
architecture. LoongArch, SPARC and other targets need a compatible runner
installation and available dependencies. Other Unix hosts (including AIX or Haiku)
can create a Python system-runtime tar archive; their GUI depends on a working
Tk port. This fallback does not claim to compile or bundle unavailable native
libraries. Mobile, embedded and other systems without desktop Python/Tk need
separate application ports.

The Help menu contains the application manual and OCR/spelling, Piper and IPA
guides. Keep [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and the runtime
licenses with redistributed packages.

## Historical note: earlier automatic ink tracer (1.0.22)

The **Typewriter**, **Handwriting**, and **Calligraphy** settings now run three
separate animation algorithms. Typewriter switches on complete Unicode grapheme
clusters, never a partly visible Bengali vowel sign or half an emoji sequence.
The earlier release automatically traced shaped glyphs. The new 1.0.23 release
accepts original, stroke-authored geometry and paints from scratch. Calligraphy
uses a broad, angled pen nib.
Neither writing mode depends on OpenCV/NumPy or a GPU. Letter shapes are shaped
**before** tracing, so the final forms retain OpenType script shaping and font
fallback. Alignment JSON/SRT/WebVTT supplies precise time ranges; otherwise
word/cluster intervals are approximate, distributed across narration duration.

* In **Animated Audiobook Video**, choose **Text motion / handwriting**, then
  choose `handwriting`, `calligraphy`, or `typewriter`.
* Optionally choose an **OTF/TTF/TTC font suitable for the language/script**.
  A real handwriting font can improve automatic tracing where a genuine
  hand-drawn stroke sample has not been supplied. Examples of separately available
  open-source font families are Atma (Bengali/Latin), Kalam (Devanagari/Latin),
  and Caveat (Latin/Cyrillic). Font files are not included.
* Configure **Pen thickness** (0=automatic) and **Calligraphy nib tilt**
  (-80..80 degrees). Both settings are saved in exported projects.
* All aspect ratios, optional cover images, and conventional slideshow/video
  formats continue to work. On the CLI add `--pen-width 0 --nib-angle -32`.

For **Bengali, Arabic, Devanagari, Tamil and other complex scripts**, use a
Pillow build with **libraqm/HarfBuzz** and install a font with sufficient glyph
coverage. Missing shaping support now gives an actionable error rather than
silently rendering disconnected glyphs. This is not a promise of universal
preinstalled font coverage, handwriting font availability, or historically
accurate pen order for the thousands of world writing systems. No runtime
network access is required.

## Windows builds that close part-way through

**There is only one user-facing build script, `build.py`.** The historical
`build_windows.py` launcher and all `.bat` launchers have been removed. The
Python modules under `scripts/` and `packaging/` are internal build code and
must remain in the source tree.

Open **PowerShell or Command Prompt** in the extracted source directory and run:

```powershell
py -3 build.py --repair --keep-open
```

`--repair` reuses compatible build environments and a previously completed
Piper worker after an interrupted build. `--keep-open` keeps an interactive
console open when the command finishes. If double-clicked directly, the builder
also tries to retain its newly created console window automatically. Existing
Python 3.12 x64/ARM64 installations are recommended for best compatibility;
Python 3.10-3.15 is accepted by the launcher but third-party wheels may not
support every version.

**Logs and diagnosis:** `build-logs/windows-build.log` records the commands and
failure traceback. `build-logs/windows-build-status.json` records the last
command *before* launching it, useful if antivirus software, a memory shortage,
or an unexpected Windows restart ends Python without a traceback. Older build
logs are copied to `windows-build.previous.log` before a new run begins.

After a failed build, share the end of `windows-build.log` and the
`windows-build-status.json` file to identify the actual reason. An abrupt
process termination cannot always be caught by Python; this update diagnoses
rather than guarantees prevention of Windows-level termination.

Once compiled, use `py -3 build.py --verify-existing` to verify existing
executables, or `py -3 build.py --package-existing` to archive already compiled
executables without launching them. Use `py -3 build.py --verify-runtime` on a
new build to run extra checks if local application policy allows it.

### Selecting multiple Piper speakers from a single model

Some Piper `.onnx` files provide multiple speaker voices. Once the matching
`.onnx.json` configuration is installed, the **Piper speaker** dropdown on the
main window lists all speaker IDs and their names where available. The **Character
Voices** dialog has a speaker selector for each character, so two characters may
share the same model while using different speakers. Selected IDs are retained
in presets and portable `.oamproj` projects, including video/audio exports.

The CLI accepts `--speaker-id 0`, `--speaker-id 1`, and so forth with
`--engine piper --model model.onnx`; use
`python -m openvoice voices --speakers --model model.onnx` to list every speaker.
Out-of-range IDs are rejected rather than silently playing Speaker 0.


### Piper voices — catalog selection and on-demand installation

The main Voice dropdown and Character Voices list catalog Piper voices even before downloading. Each voice picker has an **Installed voices only** checkbox to limit the displayed choices to downloaded models. Selecting a voice alone does **not** start downloading it.

When a missing voice is needed for **Speak, character Preview, Audio/Video Export, Batch Processing or Audiobook Creator**, a GUI confirmation lists the missing Piper voices and their permanent user-voice directory. Select **Yes** to download and reuse them for future sessions, or **No** to cancel the speech job before it begins. Downloads use checksum verification and persist as `.onnx` and `.onnx.json` files in the user data directory. Multi-speaker models offer every catalog-advertised speaker ID even before downloading, with named speakers becoming available once the model/config files are installed.

**Download Piper voices by language** remains a no-popup manual downloader. It now includes a **Status** column (`Not downloaded`, `Downloading N%`, `Downloaded`, or `Failed`), a cumulative percentage progress bar, an **Installed voices only** checkbox and a manual **Refresh download status** button. Voice-file weights are never fetched simply because the downloader or a picker opens. The catalog metadata may refresh online and is cached locally. Other neural engines retain their manual model manager, which also has an installed-only filter.

## Version 1.0.27: Timed multi-character audio scenes

The main **Installed voices only** checkbox filters downloadable neural voices
(Kokoro, Kitten, Pocket and Coqui) as well as Piper. System-installed voices
remain selectable. Character Voice Studio and the manual downloader have their
own installed-only filters.

Import WAV/MP3/FLAC/OGG/etc. sound effects with **Voice Settings → Import /
manage project sound effects**. Sound files are bundled into full `.oamproj`
project exports and restored after re-import. See the in-app **Help → Complete
User Manual** or `openvoice/resources/TIMING_SOUND_TAGS.txt` for the complete
bracket grammar with variants, combined examples, safety limits, and caveats.

Examples (these are functional timed-audio directives, not spoken text):

```text
[Mary][pause: 2s]Hi!
[John][p:0.9s]Hello.
[Alice, 3.19s]Please come to my party.
[Alice, 520ms, sfx:abc.mp3(200ms-510ms), 3.19s, sfx:def.mp3(2s-3s)]Please come.
[background:street.mp3][Alice]Can you hear the traffic?
[John, overlap:0.5s]Yes, I can.
[Alice, interrupt after 1s]Please let me finish!
```

FFmpeg mixes independent voices/sounds, supports speaker interruption and
overlap, and time-stretches lines to their requested lengths with audio-speed
limits. This is a deterministic timing grammar, **not** open-ended English
understanding; not every natural-language phrasing is supported.
