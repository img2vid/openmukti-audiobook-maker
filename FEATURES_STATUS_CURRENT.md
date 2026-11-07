# Feature status for Openmukti Audiobook Maker 1.1.2

All 500 numbered items from the attached list are included. The uploaded source recorded 268 implemented, 84 partial and 148 missing. This release adds or extends workflows across those 232 open items. Implementation coverage and hardware verification are separate.

| Classification | Count | Meaning |
|---|---:|---|
| Carried forward | 268 | The uploaded audit marked these implemented. Their classifications were retained without individually recertifying every inherited feature. |
| Implemented in 1.1 | 219 | The indicated code path provides the described workflow. The verification report identifies checks executed on this host. |
| External runtime | 11 | An implemented integration depends on a separately installed service, tool, model or sensor. Availability varies by machine. |
| Partial | 2 | The scope column identifies the remaining limitation. |

The explicitly partial rows are 428, 429. Automatic acceleration requires a supported operation and driver. An individual GPU can accelerate some stages and use CPU fallback for others.

| # | Feature | Classification | Entry point | Scope |
|---:|---|---|---|---|
| 1 | Advanced Project Creation Wizard | Carried forward | Uploaded source audit | File menu wizard guides title, template, manuscript and destination. |
| 2 | Reusable Project Templates | Carried forward | Uploaded source audit | Portable casting and production settings templates, with manuscript and notes removed. |
| 3 | Automatic Project Saving | Carried forward | Uploaded source audit | Configurable in-place autosave for a saved project; detects external edits and stops when switching projects. |
| 4 | Project Recovery System | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 5 | Project Version History | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 6 | Project Snapshots | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 7 | Project Comparison Tool | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 8 | Portable Project Packages | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 9 | Project Dependency Viewer | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 10 | Project Health Analyzer | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 11 | Project Notes | Carried forward | Uploaded source audit | Notes stored in projects; library notes added in 1.0.29 |
| 12 | Global Project Search | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 13 | Batch Project Renaming | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 14 | Project Categories | Carried forward | Uploaded source audit | Category/tags fields ship in projects; library-wide category/tag management added in 1.0.29 |
| 15 | Project Tags | Carried forward | Uploaded source audit | Category/tags fields ship in projects; library-wide category/tag management added in 1.0.29 |
| 16 | Project Favorites | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 17 | Multiple Project Tabs | Implemented in 1.1 | Studio → Project tabs | Independent project tabs, protected read-only source files and Save copy. |
| 18 | Project Activity History | Implemented in 1.1 | Project tabs → Activity | Timestamped saved manuscript revisions with line-level changes. |
| 19 | Project Bookmarks | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 20 | Intelligent Missing-File Recovery | Implemented in 1.1 | studio recover | Search a selected folder by SHA-256 and restore the exact bytes of missing or damaged assets. |
| 21 | Project Duplicate Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 22 | Project Storage Analyzer | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 23 | Read-Only Project Mode | Implemented in 1.1 | Studio → Project tabs | Independent project tabs, protected read-only source files and Save copy. |
| 24 | Automatic Project Backups | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 25 | Project Archive Manager | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 26 | Advanced PDF Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 27 | DOCX Import Improvements | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 28 | ODT Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 29 | EPUB Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 30 | HTML Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 31 | Markdown Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 32 | RTF Import | Carried forward | Uploaded source audit | RTF listed among archive document formats |
| 33 | FictionBook Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 34 | DRM-Free MOBI/AZW Import | External runtime | Document import | Uses a local Calibre ebook-convert installation for supported DRM-free Kindle variants. |
| 35 | Comic Archive Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 36 | Scanned Book Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 37 | Clipboard Import | Carried forward | Uploaded source audit | New document / insert-text actions in File menu; local OS clipboard only. |
| 38 | Web Article Import | Implemented in 1.1 | Studio → Import web article | Explicit HTTP(S) article import, charset decoding, size limits and network preferences. |
| 39 | ZIP Document Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 40 | Multi-Document Book Assembly | Carried forward | Uploaded source audit | Repeated -f inputs and audiobook manifests assemble books |
| 41 | Automatic Folder Monitoring | Implemented in 1.1 | Studio → Watch document folder | Stable new or changed files appear in a selectable import inbox. |
| 42 | Advanced Drag-and-Drop Import | External runtime | Main manuscript editor | Drop several paths onto the editor with an installed tkinterdnd2/TkDND runtime. |
| 43 | Batch Import Presets | Implemented in 1.1 | studio import --preset | Saved import rules select formats, transformations and headings. DOCX footnotes can be inline, collected or skipped. Tables can be narrated by heading and row. |
| 44 | Character Encoding Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 45 | Encoding Conversion Engine | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 46 | Automatic Line-Unwrapping | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 47 | Formatting Preservation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 48 | Footnote Import | Implemented in 1.1 | studio import --preset | Saved import rules select formats, transformations and headings. DOCX footnotes can be inline, collected or skipped. Tables can be narrated by heading and row. |
| 49 | Table Interpretation | Implemented in 1.1 | studio import --preset | Saved import rules select formats, transformations and headings. DOCX footnotes can be inline, collected or skipped. Tables can be narrated by heading and row. |
| 50 | Image Description Import | Implemented in 1.1 | Document import | Existing HTML/EPUB alt text and DOCX drawing descriptions enter the manuscript. |
| 51 | Intelligent Image Preprocessing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 52 | Automatic Skew Correction | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 53 | Perspective Correction | Carried forward | Uploaded source audit | Four-corner perspective rectification in OCR and searchable PDF paths. |
| 54 | Advanced Image Denoising | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 55 | Blur Detection and Enhancement | Implemented in 1.1 | ocr --enhance-blur --historic-print | Text-bearing tiles guide sharpening. Historical print correction handles long-s and ligatures. Installed historical Tesseract language/script models can be selected. |
| 56 | Adaptive Contrast Enhancement | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 57 | Automatic Page Layout Analysis | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 58 | Multilingual OCR Script Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 59 | Selective Region OCR | Carried forward | Uploaded source audit | Coordinate-based rectangular region selection for page OCR. |
| 60 | Intelligent Reading-Order Detection | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 61 | Multi-Column OCR | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 62 | Table OCR | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 63 | Mathematical Formula Detection | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 64 | Searchable PDF Layer Creation | Carried forward | Uploaded source audit | Tesseract searchable text-layer PDF export for images and rasterized PDF pages. |
| 65 | OCR Confidence Visualization | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 66 | Interactive OCR Correction Workspace | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 67 | Dictionary-Assisted OCR Correction | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 68 | Cross-Page Hyphenation Repair | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 69 | Historical Typography Recognition | Implemented in 1.1 | ocr --enhance-blur --historic-print | Text-bearing tiles guide sharpening. Historical print correction handles long-s and ligatures. Installed historical Tesseract language/script models can be selected. |
| 70 | Batch OCR Processing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 71 | OCR Comparison Mode | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 72 | Image-to-Text Alignment | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 73 | Formatting-Aware OCR | Implemented in 1.1 | studio ocr-layout | Review word boxes on the processed page, compare segmentation modes and export columns, ruled cells, candidate formulas, layout regions and available hOCR style information. |
| 74 | Marginal Note Recognition | Implemented in 1.1 | studio ocr-layout | Identify marginal notes by geometry or supplied rectangles. A separate local handwriting or historical model can transcribe the selected margins. The review and JSON keep notes apart from the body. Accuracy depends on the page and selected model. |
| 75 | OCR Quality Scoring | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 76 | Advanced Grammar Correction | Implemented in 1.1 | Project tabs → Editorial rules / studio review | Project terms, configurable English checks, user style rules, optional local LanguageTool and learned OCR substitutions feed the review interface. |
| 77 | Nonintrusive Spelling Suggestions | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 78 | Keyboard-Based Correction Navigation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 79 | Custom Dictionary Manager | Carried forward | Uploaded source audit | Custom dictionaries via spelling settings and name-list import |
| 80 | Project Terminology Dictionaries | Implemented in 1.1 | Project tabs → Editorial rules / studio review | Project terms, configurable English checks, user style rules, optional local LanguageTool and learned OCR substitutions feed the review interface. |
| 81 | Proper-Name Consistency Checker | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 82 | Automatic Punctuation Cleanup | Carried forward | Uploaded source audit | Cleanup transforms existed; 1.0.29 adds the artifact report |
| 83 | OCR Error Pattern Learning | Implemented in 1.1 | Project tabs → Editorial rules / studio review | Project terms, configurable English checks, user style rules, optional local LanguageTool and learned OCR substitutions feed the review interface. |
| 84 | Quotation Mark Normalization | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 85 | Dialogue Punctuation Checker | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 86 | Custom Writing Style Guides | Implemented in 1.1 | Project tabs → Editorial rules / studio review | Project terms, configurable English checks, user style rules, optional local LanguageTool and learned OCR substitutions feed the review interface. |
| 87 | Contextual Language Issue Detection | Implemented in 1.1 | Project tabs → Editorial rules / studio review | Project terms, configurable English checks, user style rules, optional local LanguageTool and learned OCR substitutions feed the review interface. |
| 88 | Side-by-Side Text Comparison | Implemented in 1.1 | Project tabs | Compare saved/current text, highlight speaker marks, protect selected text and preview each transformation before applying it. |
| 89 | Track Changes | Implemented in 1.1 | Project tabs → Activity | Timestamped saved manuscript revisions with line-level changes. |
| 90 | Unlimited Editing History | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 91 | Regular Expression Search | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 92 | Batch Replacement Preview | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 93 | Character Tag Syntax Highlighting | Implemented in 1.1 | Project tabs | Compare saved/current text, highlight speaker marks, protect selected text and preview each transformation before applying it. |
| 94 | Protected Text Regions | Implemented in 1.1 | Project tabs | Compare saved/current text, highlight speaker marks, protect selected text and preview each transformation before applying it. |
| 95 | Pronunciation Override Editor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 96 | Non-Destructive Text Transformations | Implemented in 1.1 | Project tabs | Compare saved/current text, highlight speaker marks, protect selected text and preview each transformation before applying it. |
| 97 | Grammar and Readability Statistics | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 98 | Duplicate Paragraph Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 99 | Cross-Chapter Terminology Consistency | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 100 | Synchronized Read-Aloud Editing | Implemented in 1.1 | Studio → Read along / Preview chapter openings | Render and highlight successive passages or play chapter-opening excerpts through a local sound device. |
| 101 | Intelligent Chapter Detection | Carried forward | Uploaded source audit | v1.0.28 keyword splitter; 1.0.29 adds Markdown/numbered/ALL-CAPS/custom rules |
| 102 | Configurable Chapter Recognition Rules | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 103 | Drag-and-Drop Chapter Reordering | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 104 | Chapter Splitting and Merging | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 105 | Hierarchical Section Management | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 106 | Front-Matter Management | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 107 | Back-Matter Management | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 108 | Automatic Table of Contents Generation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 109 | Footnote Narration Rules | Implemented in 1.1 | studio import --preset | Saved import rules select formats, transformations and headings. DOCX footnotes can be inline, collected or skipped. Tables can be narrated by heading and row. |
| 110 | Nested Quotation Handling | Carried forward | Uploaded source audit | Nested quote attribution in the character engine |
| 111 | Scene Break Detection | Carried forward | Uploaded source audit | Scene boundaries in character engine; 1.0.29 adds standalone detection |
| 112 | Author's Note Recognition | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 113 | Automatic Page Number Removal | Carried forward | Uploaded source audit | Existing splitter; detection greatly extended in 1.0.29 |
| 114 | Header and Footer Detection | Carried forward | Uploaded source audit | Repeated-header stripping existed; 1.0.29 adds detection reports |
| 115 | Section Metadata Editor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 116 | Interactive Chapter Navigator | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 117 | Scene Timeline | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 118 | Batch Chapter Formatting | Implemented in 1.1 | Project tabs → Chapters | Recognize front and back matter and author notes. Navigate, inspect scene boundaries, reorder by dragging or keyboard and apply uniform headings. |
| 119 | Custom Chapter Title Pronunciation | Implemented in 1.1 | Audiobook chapter manifest / studio score | Independent settings, spoken titles, recorded or written intros/outros and per-chapter or per-scene narrators. |
| 120 | Chapter-Specific Narration Settings | Implemented in 1.1 | Audiobook chapter manifest / studio score | Independent settings, spoken titles, recorded or written intros/outros and per-chapter or per-scene narrators. |
| 121 | Independent Chapter Export | Carried forward | Uploaded source audit | Existing splitter; detection greatly extended in 1.0.29 |
| 122 | Chapter Duration Estimation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 123 | Chapter Completion Tracking | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 124 | Chapter-Specific Intro and Outro Templates | Implemented in 1.1 | Audiobook chapter manifest / studio score | Independent settings, spoken titles, recorded or written intros/outros and per-chapter or per-scene narrators. |
| 125 | Chapter Preview Queue | Implemented in 1.1 | Studio → Read along / Preview chapter openings | Render and highlight successive passages or play chapter-opening excerpts through a local sound device. |
| 126 | Multi-Algorithm Character Recognition | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 127 | Character Alias Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 128 | Pronoun-Based Speaker Identification | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 129 | Unnamed Character Tracking | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 130 | Character Identity Linking | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 131 | Character Relationship Graph | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 132 | Speaker Attribution Confidence Scores | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 133 | Uncertain Dialogue Review Queue | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 134 | Multi-Paragraph Dialogue Recognition | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 135 | Nested Dialogue Attribution | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 136 | Indirect Speech Recognition | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 137 | Cross-Chapter Character Continuity | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 138 | Narrator and Character Separation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 139 | Internal Monologue Recognition | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 140 | Thought-versus-Dialogue Classification | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 141 | Speech Verb Analysis | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 142 | Dialogue Attribution Timeline | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 143 | Interactive Speaker Correction | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 144 | Explainable Speaker Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 145 | Character Merge Tool | Implemented in 1.1 | studio cast | Search profiles, merge characters and reassign selected tagged passages to another identity. |
| 146 | Character Split Tool | Implemented in 1.1 | studio cast | Search profiles, merge characters and reassign selected tagged passages to another identity. |
| 147 | Dialogue Distribution Statistics | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 148 | Custom Speaker Recognition Rules | Implemented in 1.1 | Project tabs → Editorial rules / multivoice --auto-tag | Project-specific phrase-to-cast rules are saved in the portable project and applied during automatic speaker attribution. Explicit character tags take precedence. |
| 149 | Character Appearance and Mention Tracker | Implemented in 1.1 | studio cast-map | Display a character co-occurrence graph and timeline. Review dialogue word counts, mentions, reported speech and thought candidates. |
| 150 | Multilingual Quotation Recognition | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 151 | Universal TTS Plugin Architecture | Implemented in 1.1 | openvoice.engines entry points | Implement SpeechEngine and register a trusted plugin. Engine IDs also work in character profiles. Discovery can be disabled. |
| 152 | Automatic Engine Capability Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 153 | Engine Compatibility Analyzer | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 154 | Isolated Engine Environments | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 155 | CPU Performance Profiles | Carried forward | Uploaded source audit | Low, balanced and fast thread-limit profiles, GUI/CLI controls. |
| 156 | Optional GPU Acceleration | Implemented in 1.1 | hardware-check / Voices → Use available GPU | Compatible ONNX/PyTorch inference, hardware video encoding, OpenCL image filters, composition, selected PCM effects, signal analysis and optional EGL ES2 composition. CPU fallback is available. |
| 157 | Automatic Engine Fallback | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 158 | Paragraph-Level Engine Selection | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 159 | Strict Offline Synthesis Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 160 | Local TTS Server Mode | Implemented in 1.1 | studio serve / studio stream | Loopback WAV and incremental speech endpoints. Streaming playback overlaps preparation of the next chunk. |
| 161 | Engine Diagnostics Center | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 162 | TTS Engine Benchmarking | Implemented in 1.1 | studio benchmark --output | Measure synthesis times, real-time factor, signal peaks, clipping and architecture. Optional psutil measures process-tree memory. |
| 163 | Intelligent Synthesis Queue | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 164 | Engine-Specific Text Normalization | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 165 | Streaming Speech Generation | Implemented in 1.1 | studio serve / studio stream | Loopback WAV and incremental speech endpoints. Streaming playback overlaps preparation of the next chunk. |
| 166 | Adaptive Text Chunking | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 167 | Interrupted Synthesis Recovery | Implemented in 1.1 | render --cache-dir / studio passages | Content-addressed chunk cache, checksum validation, atomic commits and reuse after interruption or local text edits. |
| 168 | Reproducible Synthesis Settings | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 169 | Automatic Sample-Rate Compatibility | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 170 | Engine Feature Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 171 | Speech Engine Process Isolation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 172 | CPU and Memory Resource Governor | External runtime | studio queue work | Limit thread counts and process-tree memory. Thermal/battery and memory controls can suspend active work when supported sensors are available. Requires psutil for native readings. |
| 173 | Speech Engine Watchdog | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 174 | Engine Version Pinning | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 175 | On-Demand Engine Loading | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 176 | Unified Voice Library | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 177 | Automatic Multi-Speaker Enumeration | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 178 | Individual Voice Preview Samples | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 179 | Side-by-Side Voice Comparison | Implemented in 1.1 | studio audition | Render identical text with multiple profiles. Compare offline samples with controls, durations and signal diagnostics. |
| 180 | Explicit Voice Download Approval | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 181 | Detailed Download Progress | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 182 | Model Integrity Verification | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 183 | Voice Licensing Information | Implemented in 1.1 | studio voice-index | Cross-engine voice records with editable rights, permitted uses, accent, favorites, tags and collections. Unknown rights remain identified as unknown. |
| 184 | Model Storage Information | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 185 | Accent-Based Voice Filtering | Implemented in 1.1 | studio voice-index | Cross-engine voice records with editable rights, permitted uses, accent, favorites, tags and collections. Unknown rights remain identified as unknown. |
| 186 | Language-Based Voice Filtering | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 187 | Voice Favorites | Implemented in 1.1 | studio voice-index | Cross-engine voice records with editable rights, permitted uses, accent, favorites, tags and collections. Unknown rights remain identified as unknown. |
| 188 | Voice Tags | Implemented in 1.1 | studio voice-index | Cross-engine voice records with editable rights, permitted uses, accent, favorites, tags and collections. Unknown rights remain identified as unknown. |
| 189 | Offline Voice Preview Library | Implemented in 1.1 | studio audition | Render identical text with multiple profiles. Compare offline samples with controls, durations and signal diagnostics. |
| 190 | Installed Voice Manager | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 191 | Duplicate Voice File Detection | Implemented in 1.1 | studio models | Compare model hashes, transfer checksum-protected assets, enforce pinned versions and repair damaged weights from a matching approved backup. |
| 192 | Custom Voice Model Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 193 | Voice Format Conversion | External runtime | studio models convert | Convert supported ONNX graphs to ORT format and reopen the result. Requires compatible ONNX Runtime. |
| 194 | Voice Cache Repair | Implemented in 1.1 | studio models | Compare model hashes, transfer checksum-protected assets, enforce pinned versions and repair damaged weights from a matching approved backup. |
| 195 | Voice Pack Import and Export | Implemented in 1.1 | studio models | Compare model hashes, transfer checksum-protected assets, enforce pinned versions and repair damaged weights from a matching approved backup. |
| 196 | Voice Model Version Locking | Implemented in 1.1 | studio models | Compare model hashes, transfer checksum-protected assets, enforce pinned versions and repair damaged weights from a matching approved backup. |
| 197 | Voice Quality Evaluation | Implemented in 1.1 | studio audition | Render identical text with multiple profiles. Compare offline samples with controls, durations and signal diagnostics. |
| 198 | Queued Manual Downloads | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 199 | Resumable Model Downloads | Implemented in 1.1 | voice-download / Voices downloader | Preserve partial Piper transfers, resume with verified ranges and verify final checksums before installation. |
| 200 | Voice Collection Presets | Implemented in 1.1 | studio voice-index | Cross-engine voice records with editable rights, permitted uses, accent, favorites, tags and collections. Unknown rights remain identified as unknown. |
| 201 | Detailed Character Voice Profiles | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 202 | Voice Casting Workspace | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 203 | Multiple Narrator Profiles | Implemented in 1.1 | Audiobook chapter manifest / studio score | Independent settings, spoken titles, recorded or written intros/outros and per-chapter or per-scene narrators. |
| 204 | Character-Specific Speaking Speed | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 205 | Character-Specific Pitch Controls | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 206 | Character-Specific Vocal Energy | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 207 | Character-Specific Pause Settings | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 208 | Character Pronunciation Dictionaries | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 209 | Character Emotion Presets | Carried forward | Uploaded source audit | Emotion/style presets via voice design styles |
| 210 | Character Whispering Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 211 | Character Accent Preferences | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 212 | Contextual Dialogue Delivery | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 213 | Character Voice Consistency Checker | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 214 | Character Voice Inheritance | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 215 | Alternative Character Voice Takes | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 216 | Character Audition Studio | Implemented in 1.1 | studio audition | Render identical text with multiple profiles. Compare offline samples with controls, durations and signal diagnostics. |
| 217 | Voice Compatibility Recommendations | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 218 | Character-to-Speaker Mapping | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 219 | Character Profile Search | Implemented in 1.1 | studio cast | Search profiles, merge characters and reassign selected tagged passages to another identity. |
| 220 | Backup Character Voices | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 221 | Suggested Automatic Voice Casting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 222 | Character Loudness Targets | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 223 | Dialogue Turn-Taking Controls | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 224 | Scene-Specific Character Performance | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 225 | Voice Profile Testing Scripts | Implemented in 1.1 | studio score / studio audition | Per-passage engines, inherited voices, approved backups, scene cast overrides, named alternative takes and reusable listening samples. |
| 226 | Sentence Emphasis Editor | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 227 | Unified SSML Compatibility Layer | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 228 | Automatic Punctuation Interpretation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 229 | Custom Pause Insertion | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 230 | Pronunciation Dictionary with IPA Support | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 231 | Abbreviation Expansion Rules | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 232 | Custom Proper-Noun Pronunciation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 233 | Number Narration Settings | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 234 | Date and Time Pronunciation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 235 | Homograph Disambiguation | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 236 | Phoneme-Level Pronunciation Editor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 237 | Natural Speech Rhythm Controls | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 238 | Advanced Prosody Curves | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 239 | Emotion-Aware Speech Markup | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 240 | Optional Breathing Sounds | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 241 | Seamless Sentence Joining | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 242 | Intelligent Silence Trimming | Carried forward | Uploaded source audit | FFmpeg trim-silence removes leading and trailing silence with thresholds. |
| 243 | Automatic Pause Variation | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 244 | Dialogue Hesitation Controls | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 245 | Paragraph-Level Pacing | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 246 | Chapter-Level Pacing Curves | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 247 | Expressive Scene Transitions | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 248 | Contextual Emphasis Suggestions | Implemented in 1.1 | Sentence emphasis editor / studio score | Speech markup, contextual IPA, acoustic emotion presets, short seam fades, approved breaths, pause variation and pitch, gain and pace curves. |
| 249 | Pronunciation Audit Report | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 250 | Ellipsis and Dash Interpretation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 251 | Automatic Language Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 252 | Script-Aware Text Processing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 253 | Bidirectional Text Support | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 254 | Language Detection by Paragraph | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 255 | Mixed-Language Sentence Processing | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 256 | Intelligent Font Fallback | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 257 | Per-Language Pronunciation Dictionaries | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 258 | Language-Specific Text Normalization | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 259 | Unicode Normalization Controls | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 260 | Automatic Transliteration Suggestions | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 261 | Language-Specific Number Reading | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 262 | Localized Date and Currency Narration | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 263 | Languages Without Word Spaces | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 264 | Advanced Indic Script Shaping | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 265 | CJK Text Segmentation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 266 | Arabic Diacritic Processing | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 267 | Regional Language Variants | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 268 | Multilingual Character Voice Continuity | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 269 | Romanization Management | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 270 | Multilingual Dialogue Tagging | Implemented in 1.1 | studio cast-map / studio language-test / script-check | Language reports for individual passages, multilingual test material and Unicode script/control validation. |
| 271 | Voice-Language Compatibility Filtering | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 272 | Script-Specific Punctuation Rules | Implemented in 1.1 | studio localize / language-spans / score | Route mixed-script spans to selected voices. Normalize punctuation and diacritics, localize numbers/currencies/dates and transliterate with ICU. Bengali numbers support lakh/crore grouping. |
| 273 | Complex Grapheme Navigation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 274 | Language-Specific Speech Testing | Implemented in 1.1 | studio cast-map / studio language-test / script-check | Language reports for individual passages, multilingual test material and Unicode script/control validation. |
| 275 | Mixed-Script Audiobook Validation | Implemented in 1.1 | studio cast-map / studio language-test / script-check | Language reports for individual passages, multilingual test material and Unicode script/control validation. |
| 276 | Interactive Waveform Editor | Implemented in 1.1 | Waveform editor / Accessible workspace | Large waveform and spectrogram views, exact time selections, clip export and labelled browser playback controls. |
| 277 | Multitrack Audio Timeline | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 278 | Precision Audio Cutting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 279 | Fade-In and Fade-Out Controls | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 280 | Automatic Silence Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 281 | Noise Reduction | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 282 | De-Esser | Carried forward | Uploaded source audit | FFmpeg deesser wired to audio dialog and CLI. |
| 283 | Parametric Equalizer | Carried forward | Uploaded source audit | Frequency, gain and bandwidth-controlled FFmpeg parametric EQ (single-band). |
| 284 | Dynamic Range Compressor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 285 | True-Peak Limiter | Carried forward | Uploaded source audit | Loudness normalization chain includes true-peak limiting |
| 286 | Loudness Normalization | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 287 | True-Peak Analysis | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 288 | Mono and Stereo Processing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 289 | Room-Tone Management | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 290 | Passage-Level Loudness Matching | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 291 | Click and Pop Detection | Implemented in 1.1 | studio signal | Detect isolated spikes, near silence, repeated waveform blocks and clipped samples for listening review. |
| 292 | Real-Time Effects Preview | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 293 | Audio Spectrogram Viewer | Implemented in 1.1 | Waveform editor / Accessible workspace | Large waveform and spectrogram views, exact time selections, clip export and labelled browser playback controls. |
| 294 | Clipping Detection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 295 | Synthesis Artifact Detection | Implemented in 1.1 | studio signal | Detect isolated spikes, near silence, repeated waveform blocks and clipped samples for listening review. |
| 296 | Automatic Crossfading | Implemented in 1.1 | studio crossfade / compare-mixes | Crossfade recordings and compare reference/candidate levels, duration, clipping and transient counts. |
| 297 | Missing Audio Segment Detection | Implemented in 1.1 | segment-audit / studio passages --only | Audit a render manifest for absent, empty or checksum-mismatched files. Regenerate selected passages independently. |
| 298 | Audio Duration Recalculation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 299 | Selective Passage Regeneration | Implemented in 1.1 | segment-audit / studio passages --only | Audit a render manifest for absent, empty or checksum-mismatched files. Regenerate selected passages independently. |
| 300 | Automated Audio Quality Report | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 301 | Background Music Manager | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 302 | Automatic Music Ducking | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 303 | Scene-Based Music Assignment | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 304 | Music Licensing Tracker | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 305 | Sound Effects Library | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 306 | Sound Effects Timeline | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 307 | Ambient Soundscapes | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 308 | Reusable Sound Design Templates | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 309 | Sidechain Compression | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 310 | Environmental Sound Presets | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 311 | Stereo Panning Controls | Carried forward | Uploaded source audit | Stereo panning filter in CLI and audio dialog. |
| 312 | Convolution Reverb | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 313 | Scene-Based Sound Palettes | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 314 | Cinematic Audio Transitions | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 315 | Dialogue Priority Mixing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 316 | Sound Effects Preview Browser | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 317 | Looping Ambient Audio | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 318 | Audio Automation Curves | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 319 | Scene Boundary Markers | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 320 | Custom Sound Effect Import | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 321 | Music Edit Markers | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 322 | Audio Stem Export | Implemented in 1.1 | Sound timeline / studio mix | Timeline editing, previews, room-tone/palette assignment, ducking, room and convolution effects, loudness targets, loop seams, gain curves, cut markers, credits and stems. |
| 323 | Narration-Only Export Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 324 | Reference Mix Comparison | Implemented in 1.1 | studio crossfade / compare-mixes | Crossfade recordings and compare reference/candidate levels, duration, clipping and transient counts. |
| 325 | Audio Drama Production Mode | Carried forward | Uploaded source audit | Timed multi-character scenes with SFX/background/overlap (1.0.27) |
| 326 | Audiobook Production Dashboard | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 327 | Scene Production Status | Implemented in 1.1 | studio scene-status / pipeline | Save per-scene stages. Preview or run a reusable ordered series of editing, synthesis and export commands. |
| 328 | Chapter Workflow Status | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 329 | Advanced Rendering Queue | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 330 | Crash-Resistant Render Resumption | Implemented in 1.1 | render --cache-dir / studio passages | Content-addressed chunk cache, checksum validation, atomic commits and reuse after interruption or local text edits. |
| 331 | Selective Regeneration | Implemented in 1.1 | render --cache-dir / studio passages | Content-addressed chunk cache, checksum validation, atomic commits and reuse after interruption or local text edits. |
| 332 | Content-Hash Audio Caching | Implemented in 1.1 | render --cache-dir / studio passages | Content-addressed chunk cache, checksum validation, atomic commits and reuse after interruption or local text edits. |
| 333 | Scheduled Rendering | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 334 | Batch Audiobook Creation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 335 | Multicore CPU Scheduling | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 336 | Low-Memory Production Mode | External runtime | studio queue work | Limit thread counts and process-tree memory. Thermal/battery and memory controls can suspend active work when supported sensors are available. Requires psutil for native readings. |
| 337 | Energy-Saving Rendering Mode | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 338 | Temperature-Aware Performance Management | External runtime | studio queue work | Limit thread counts and process-tree memory. Thermal/battery and memory controls can suspend active work when supported sensors are available. Requires psutil for native readings. |
| 339 | Battery-Aware Processing | External runtime | studio queue work | Limit thread counts and process-tree memory. Thermal/battery and memory controls can suspend active work when supported sensors are available. Requires psutil for native readings. |
| 340 | Storage Availability Monitoring | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 341 | Rendering Time Estimation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 342 | Production Preset Manager | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 343 | Dry-Run Production Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 344 | Optional Background Rendering | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 345 | Detailed Production Logs | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 346 | Quality-Control Checkpoints | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 347 | Chapter Approval Workflow | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 348 | Production Pipeline Templates | Implemented in 1.1 | studio scene-status / pipeline | Save per-scene stages. Preview or run a reusable ordered series of editing, synthesis and export commands. |
| 349 | Resource Usage Forecasting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 350 | Production Queue Priorities | Implemented in 1.1 | studio queue | Durable scheduling, priority changes, parallel claims, capacity checks, timeouts, reduced process priority, cancellation and retry. |
| 351 | Video Template Library | Implemented in 1.1 | Cover designer / video --storyboard | Templates, scene titles, animated pans/zooms, easing, wipes, fades and dissolves. |
| 352 | Audio-Synchronized Subtitles | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 353 | Word-by-Word Highlighting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 354 | Advanced Typewriter Animation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 355 | Karaoke-Style Text Highlighting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 356 | Scrolling Book Text | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 357 | Static Cover Video Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 358 | Ken Burns Effect | Implemented in 1.1 | Cover designer / video --storyboard | Templates, scene titles, animated pans/zooms, easing, wipes, fades and dissolves. |
| 359 | Scene-Specific Title Cards | Implemented in 1.1 | Cover designer / video --storyboard | Templates, scene titles, animated pans/zooms, easing, wipes, fades and dissolves. |
| 360 | Vertical Video Mode | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 361 | Custom Aspect Ratios | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 362 | Optional 4K Video Rendering | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 363 | Frame-Accurate Timing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 364 | Animation Easing Controls | Implemented in 1.1 | Cover designer / video --storyboard | Templates, scene titles, animated pans/zooms, easing, wipes, fades and dissolves. |
| 365 | Advanced Video Transitions | Implemented in 1.1 | Cover designer / video --storyboard | Templates, scene titles, animated pans/zooms, easing, wipes, fades and dissolves. |
| 366 | Animated Paper Backgrounds | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 367 | Accessible Caption Color Presets | Implemented in 1.1 | Studio → Caption design / Subtitle editor | Contrast palettes, safe margins, collision checks, optional placement and time-scrubbed design previews. Edit and save cue times. |
| 368 | Caption Collision Detection | Implemented in 1.1 | Studio → Caption design / Subtitle editor | Contrast palettes, safe margins, collision checks, optional placement and time-scrubbed design previews. Edit and save cue times. |
| 369 | Live Video Layout Preview | Implemented in 1.1 | Studio → Caption design / Subtitle editor | Contrast palettes, safe margins, collision checks, optional placement and time-scrubbed design previews. Edit and save cue times. |
| 370 | Subtitle Safe-Zone Manager | Implemented in 1.1 | Studio → Caption design / Subtitle editor | Contrast palettes, safe margins, collision checks, optional placement and time-scrubbed design previews. Edit and save cue times. |
| 371 | Multilingual Video Font Management | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 372 | Manual Subtitle Timing Editor | Implemented in 1.1 | Studio → Caption design / Subtitle editor | Contrast palettes, safe margins, collision checks, optional placement and time-scrubbed design previews. Edit and save cue times. |
| 373 | Text Animation Effects Library | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 374 | Audio Waveform Visualizer | Implemented in 1.1 | Storyboard waveform and progress layers | Render real amplitude samples around playback time and visualize section progress. |
| 375 | Reading Progress Visualization | Implemented in 1.1 | Storyboard waveform and progress layers | Render real amplitude samples around playback time and visualize section progress. |
| 376 | True Stroke-Based Handwriting Engine | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 377 | Vector Stroke Representation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 378 | Pressure-Sensitive Pen Simulation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 379 | Realistic Brush Calligraphy | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 380 | Multiple Pen Types | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 381 | Calligraphy Nib Angle Control | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 382 | Realistic Ink Bleeding | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 383 | Dynamic Stroke Velocity | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 384 | Stroke Order Management | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 385 | Handwritten Punctuation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 386 | Script-Specific Handwriting Models | Implemented in 1.1 | Handwriting / Stroke Studio | Original compositional strokes cover all 11,172 modern Hangul syllables and a basic Han set. Shaped reconstruction uses other script-specific strategies, and manual stroke packs take precedence. Native trajectory coverage varies by script. |
| 387 | Connected-Letter Handwriting | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 388 | Right-to-Left Handwriting Animation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 389 | CJK Stroke-Order Animation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 390 | Indic Handwriting Support | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 391 | Natural Baseline Variation | Implemented in 1.1 | Handwriting / storyboard correction and notebook layers | Controlled baseline variation, ruled paper and timed crossing out, erasure and pen-painted rewriting. |
| 392 | Realistic Pen Lifts | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 393 | Synchronized Writing Animation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 394 | Handwriting Correction Animation | Implemented in 1.1 | Handwriting / storyboard correction and notebook layers | Controlled baseline variation, ruled paper and timed crossing out, erasure and pen-painted rewriting. |
| 395 | Notebook Line Templates | Implemented in 1.1 | Handwriting / storyboard correction and notebook layers | Controlled baseline variation, ruled paper and timed crossing out, erasure and pen-painted rewriting. |
| 396 | Paper Texture Simulation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 397 | Animated Pen Cursor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 398 | Custom Handwritten Character Editor | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 399 | Handwriting Style Presets | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 400 | Handwriting-to-Video Rendering | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 401 | Integrated Book Cover Designer | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 402 | Cover Layout Grid | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 403 | Cover Template Library | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 404 | Custom Cover Import | Carried forward | Uploaded source audit | Cover/cover-image import for videos and slideshows |
| 405 | Chapter Illustration Manager | Implemented in 1.1 | Chapter covers / storyboard | Assign images to chapters or use timed opening artwork. Portable projects retain referenced images. |
| 406 | Image Timeline Editor | Carried forward | Uploaded source audit | Multiple covers change during playback on the image timeline |
| 407 | Custom Text Boxes | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 408 | Optional AI Image Generation Integration | External runtime | studio illustrate | Submit an explicit request to a selected local AUTOMATIC1111-compatible image service. Requires that service and a local model. |
| 409 | Visual Theme Packs | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 410 | Manga and Comic Panel Navigation | Implemented in 1.1 | Cover designer → Panel tour | Animate panels in reading order, set independent layer motion and preserve descriptions in the design and exported PNG metadata. |
| 411 | Parallax Image Animation | Implemented in 1.1 | Cover designer → Panel tour | Animate panels in reading order, set independent layer motion and preserve descriptions in the design and exported PNG metadata. |
| 412 | Illustration Alternative Text | Implemented in 1.1 | Cover designer → Panel tour | Animate panels in reading order, set independent layer motion and preserve descriptions in the design and exported PNG metadata. |
| 413 | Advanced Image Cropping | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 414 | Animated Backgrounds | Carried forward | Uploaded source audit | Animated text/background modes |
| 415 | Watermark Manager | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 416 | Branding Presets | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 417 | Multilayer Visual Compositing | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 418 | Light and Dark Visual Themes | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 419 | Animated Book Title Sequences | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 420 | Chapter Opening Illustrations | Implemented in 1.1 | Chapter covers / storyboard | Assign images to chapters or use timed opening artwork. Portable projects retain referenced images. |
| 421 | Smart Image Focus Points | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 422 | Color Palette Manager | Implemented in 1.1 | Studio → Cover designer | Edit layers and typography, use grid and safety guides, choose colors, save branding, crop images and render static covers or animated titles. |
| 423 | Narrated Slideshow Mode | Carried forward | Uploaded source audit | Classic narrated slideshow mode |
| 424 | Animated Music Visualizers | Implemented in 1.1 | Storyboard waveform and progress layers | Render real amplitude samples around playback time and visualize section progress. |
| 425 | Automatic Credits Generator | Carried forward | Uploaded source audit | Attribution/credits document generator |
| 426 | Fully Scalable Interface | Implemented in 1.1 | Desktop layout / Studio toolbars | Windows fit available work areas, Studio toolbars wrap and per-monitor scaling supports a 50–300 percent preference. Windows/native high-DPI verification is pending. |
| 427 | High-Contrast Accessibility Themes | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 428 | Screen Reader Compatibility | Partial | Studio → Accessible manuscript and playback workspace | An opt-in local HTML control view mirrors native menus, buttons, fields, notebook tabs, lists, ranges and table rows. It also offers accessible editing and playback. Custom drawing also has arrow-key and coordinate entry. Full coverage across advanced native dialogs, operating-system pickers and assistive technologies still requires native-device verification. |
| 429 | Complete Keyboard Navigation | Partial | Studio → Accessible manuscript and playback workspace | An opt-in local HTML control view mirrors native menus, buttons, fields, notebook tabs, lists, ranges and table rows. It also offers accessible editing and playback. Custom drawing also has arrow-key and coordinate entry. Full coverage across advanced native dialogs, operating-system pickers and assistive technologies still requires native-device verification. |
| 430 | Customizable Keyboard Shortcuts | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 431 | Custom Workspace Layouts | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 432 | Touch-Friendly Interface Mode | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 433 | Guided First-Time Setup | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 434 | Interactive Feature Tutorials | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 435 | Global Undo and Redo | Implemented in 1.1 | Project, cover and sound editors | Standard edit commands route to focused text or structured cover/sound editing. Workspace preferences have a reversible history. Editing exports and irreversible external actions are outside undo. |
| 436 | Distraction-Free Writing Mode | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 437 | Reduced-Motion Mode | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 438 | Non-Color Status Indicators | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 439 | Custom Editor Font Preferences | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 440 | Multilingual GUI Localization | Implemented in 1.1 | Studio → Preferences → language | Bundled Bengali and Spanish catalogs include over 680 translated strings per language and 86 parameterized message templates. Tk labels, menus, modal prompts and the accessible browser editor use the language selection. External engine diagnostics can retain their original language. |
| 441 | Offline User Manual | Carried forward | Uploaded source audit | Offline user manual in the Help menu |
| 442 | Contextual Help System | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 443 | Actionable Error Messages | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 444 | Diagnostic Report Export | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 445 | Voice-Controlled Interface Commands | External runtime | Studio → Local voice command | An explicitly chosen Vosk model recognizes common commands. Requires the optional voice-control packages and an authorized microphone. |
| 446 | Large Waveform Editing Mode | Implemented in 1.1 | Waveform editor / Accessible workspace | Large waveform and spectrogram views, exact time selections, clip export and labelled browser playback controls. |
| 447 | Accessible Playback Controls | Implemented in 1.1 | Waveform editor / Accessible workspace | Large waveform and spectrogram views, exact time selections, clip export and labelled browser playback controls. |
| 448 | Left-Handed Workspace Presets | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 449 | Customizable Toolbar | Implemented in 1.1 | Studio → Preferences, setup and tutorial | Contrast, font, larger touch targets, workspace sides, shortcuts, toolbars, focus writing, textual statuses, reduced-motion previews and interactive setup/tutorial steps. |
| 450 | Split-Screen Editing Mode | Implemented in 1.1 | Studio → Split manuscript and preview | Edit the manuscript alongside synchronized waveform and artwork previews, then apply edits after a conflict check. |
| 451 | Comprehensive Audio Format Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 452 | M4B Audiobook Creation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 453 | Embedded Chapter Artwork | External runtime | studio chapter-art | Write chapter titles, times and artwork as ID3 CHAP/CTOC records in MP3. Requires mutagen. |
| 454 | Advanced Audio Metadata Editor | Implemented in 1.1 | tag-audio / studio metadata, daisy, preflight | Tags and artwork, Dublin Core or JSON metadata, DAISY 2.02 navigation packages and actual codec-header checks against destination profiles. |
| 455 | ID3 Tag Editor | Carried forward | Uploaded source audit | Edit common MP3 ID3 fields through FFmpeg stream-copy, CLI and GUI. |
| 456 | Embedded Cover Art | Carried forward | Uploaded source audit | Embed JPEG/PNG album artwork in MP3/M4A/M4B/FLAC using stream copy. |
| 457 | RSS Audiobook Feed Generator | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 458 | Podcast Episode Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 459 | Audiobook Distribution Metadata Export | Implemented in 1.1 | tag-audio / studio metadata, daisy, preflight | Tags and artwork, Dublin Core or JSON metadata, DAISY 2.02 navigation packages and actual codec-header checks against destination profiles. |
| 460 | EPUB Media Overlay Export | Carried forward | Uploaded source audit | Single-narration EPUB 3 with timed text, SMIL, navigation and embedded MP3. |
| 461 | DAISY-Compatible Production Workflow | Implemented in 1.1 | tag-audio / studio metadata, daisy, preflight | Tags and artwork, Dublin Core or JSON metadata, DAISY 2.02 navigation packages and actual codec-header checks against destination profiles. |
| 462 | WebVTT Subtitle Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 463 | SRT Subtitle Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 464 | ASS Subtitle Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 465 | Transcript PDF Export | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 466 | Multilingual Subtitle Packaging | Carried forward | Uploaded source audit | Language-keyed ASS, SRT and VTT tracks in a checksummed ZIP. |
| 467 | Audiobook Sample Generator | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 468 | Platform-Specific Export Presets | Implemented in 1.1 | tag-audio / studio metadata, daisy, preflight | Tags and artwork, Dublin Core or JSON metadata, DAISY 2.02 navigation packages and actual codec-header checks against destination profiles. |
| 469 | Export Compliance Checker | Implemented in 1.1 | tag-audio / studio metadata, daisy, preflight | Tags and artwork, Dublin Core or JSON metadata, DAISY 2.02 navigation packages and actual codec-header checks against destination profiles. |
| 470 | File Integrity Manifests | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 471 | Release Notes Generator | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 472 | Automated Attribution Document | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 473 | Custom Export Naming Rules | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 474 | Project Distribution Archive | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 475 | Optional Cloud Upload Integration | External runtime | studio upload | Copy a selected release file to a user-configured rclone destination. Requires an authorized rclone remote. |
| 476 | Universal Dependency Manager | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 477 | CPU-Optimized Dependency Selection | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 478 | Offline Dependency Validation | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 479 | Explicit Installation Consent System | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 480 | Digital Signature Verification | Implemented in 1.1 | studio sign, verify, extension, backup, restore | Ed25519 signatures, permission-limited declarative extensions and authenticated encrypted backup/restoration. |
| 481 | Reproducible Build System | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 482 | Software Bill of Materials Generator | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 483 | Multilingual Regression Test Corpus | Implemented in 1.1 | studio test languages | A multilingual corpus exercises normalization and grapheme round trips, including Bengali. |
| 484 | Reference Speech Quality Tests | Carried forward | Uploaded source audit | User-selected reference versus aligned integer PCM WAV with adjustable RMS tolerance. |
| 485 | Automatic Installation Repair | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 486 | Software Update Rollback | Implemented in 1.1 | studio versions | Install hash-verified single-file portable binaries side by side and switch the active version back. |
| 487 | Diagnostic Support Bundle | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 488 | Plugin Signing and Verification | Implemented in 1.1 | studio sign, verify, extension, backup, restore | Ed25519 signatures, permission-limited declarative extensions and authenticated encrypted backup/restoration. |
| 489 | Extension Sandboxing | Implemented in 1.1 | studio sign, verify, extension, backup, restore | Ed25519 signatures, permission-limited declarative extensions and authenticated encrypted backup/restoration. |
| 490 | Granular Application Permissions | Implemented in 1.1 | Studio → Preferences → permissions | Application-level audit hooks enforce selected folder, network and subprocess access. Microphone capture and native-plugin loading are gated separately. Explicitly trusted external programs retain their operating-system privileges. |
| 491 | Encrypted Project Backups | Implemented in 1.1 | studio sign, verify, extension, backup, restore | Ed25519 signatures, permission-limited declarative extensions and authenticated encrypted backup/restoration. |
| 492 | Private Information Redaction | Carried forward | Uploaded source audit | Production log field redaction for shared diagnostics |
| 493 | Dependency License Auditing | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 494 | Automated Accessibility Testing | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 495 | Integrated Software Test Runner | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
| 496 | Hardware Benchmark Profiles | Implemented in 1.1 | studio benchmark --output | Measure synthesis times, real-time factor, signal peaks, clipping and architecture. Optional psutil measures process-tree memory. |
| 497 | Audio Regression Testing | Carried forward | Uploaded source audit | CLI detects sample, format, channel or duration changes and returns failure for regressions. |
| 498 | Cross-Platform Continuous Integration | Carried forward | Uploaded source audit | Recorded as implemented in the supplied project. |
| 499 | Project Format Migration System | Implemented in 1.1 | studio migrate | Validate an earlier project and write a version 2 archive while preserving asset bytes and unknown manifest fields. |
| 500 | Integrated Developer Documentation Center | Implemented in 1.1 | F1 / Developer center / Run tests / Export diagnostics | Contextual guidance, bundled developer reference, redacted diagnostic packages and selectable language, rendering, accessibility and source checks. |
