# Openmukti Audiobook Maker — 500-Feature Status and Roadmap

> **Latest source update:** [FEATURES_STATUS_1.0.30.md](FEATURES_STATUS_1.0.30.md) is the newer audit. The 1.0.29 counts and tables below are preserved as a historical baseline.

Generated 2026-11-04 for version 1.0.29.

## How this map was made

Every one of the 500 requested features was compared against the actual source code,
the bundled regression tests and the documented behavior of release 1.0.28, then marked:

- **✅ Shipped** — implemented and exercised in v1.0.28 or earlier.
- **🆕 Added in 1.0.29** — implemented in this development session as working, tested code.
- **🔶 Partial** — a meaningful capability exists; the full feature needs more work.
- **🗺 Roadmap** — not implemented; assigned to a delivery phase below.

Statuses are conservative: when evidence was ambiguous, the feature was marked Partial
or Roadmap rather than Shipped.

## Summary

| Status | Count |
|---|---|
| ✅ Shipped (≤1.0.28) | 213 |
| 🆕 Added in 1.0.29 | 38 |
| 🔶 Partial | 76 |
| 🗺 Roadmap | 173 |

**Working after this session: 251 of 500 features (50%).** With the 76 partial features
completed, roughly two thirds of the list would be covered.

## What was added in version 1.0.29 (38 features)

All additions are offline, CPU-only, covered by 36 new regression tests, and integrated
into both the CLI and (where relevant) the GUI Tools menu and text-tool pipeline.

### Advanced Project Management

- **10. Project Health Analyzer**
- **12. Global Project Search**
- **13. Batch Project Renaming**
- **16. Project Favorites**
- **19. Project Bookmarks**
- **21. Project Duplicate Detection**
- **22. Project Storage Analyzer**

### Intelligent Text Editor and Proofreading

- **81. Proper-Name Consistency Checker**
- **85. Dialogue Punctuation Checker**
- **97. Grammar and Readability Statistics**
- **99. Cross-Chapter Terminology Consistency**

### Chapter, Section, and Book Structure Management

- **102. Configurable Chapter Recognition Rules**
- **104. Chapter Splitting and Merging**
- **105. Hierarchical Section Management**
- **108. Automatic Table of Contents Generation**
- **115. Section Metadata Editor**
- **122. Chapter Duration Estimation**
- **123. Chapter Completion Tracking**

### Expressive Speech and Prosody Engine

- **231. Abbreviation Expansion Rules**
- **233. Number Narration Settings**
- **234. Date and Time Pronunciation**
- **249. Pronunciation Audit Report**
- **250. Ellipsis and Dash Interpretation**

### Intelligent Audiobook Production Automation

- **326. Audiobook Production Dashboard**
- **328. Chapter Workflow Status**
- **341. Rendering Time Estimation**
- **345. Detailed Production Logs**
- **346. Quality-Control Checkpoints**
- **347. Chapter Approval Workflow**
- **349. Resource Usage Forecasting**

### Cover Art, Illustrations, and Visual Production

- **425. Automatic Credits Generator** — Attribution/credits document generator

### Audiobook Exporting, Formats, and Publishing

- **464. ASS Subtitle Export**
- **465. Transcript PDF Export**
- **467. Audiobook Sample Generator**
- **471. Release Notes Generator**
- **472. Automated Attribution Document**
- **473. Custom Export Naming Rules**

### Advanced Software Engineering and Build Infrastructure

- **492. Private Information Redaction** — Production log field redaction for shared diagnostics

### New commands and entry points

| Command / entry point | Purpose |
|---|---|
| `openmukti library …` | Index, categorize, tag, favorite, search, batch-rename, duplicate-detect, storage-analyze and health-check projects |
| `openmukti chapters …` | Chapter detection, table of contents, scene breaks, headers, duration estimates, completion status |
| `openmukti proofread …` | Name consistency, dialogue punctuation, OCR artifacts, readability, terminology, pronunciation audit |
| `openmukti captions in.json out.ass` | Styled ASS subtitle export |
| `openmukti name-files …` | Pattern-based export naming (`{title}-{number:03}-{chapter}`) |
| `openmukti sample …` | Promotional audio excerpt with fades |
| `openmukti release-notes …` | Markdown release notes from structured changes |
| `openmukti attribution …` | Credits/licensing document from asset records |
| `openmukti transcript …` | Transcript as PDF (dependency-free), HTML or TXT |
| `openmukti production …` | Workflow stages, QC checkpoints, approvals, dashboard, estimates, forecasts, redacted JSONL logs |
| Text tools `expand-abbreviations`, `speak-numbers`, `speak-numbers-plain`, `speak-dates-times`, `pauses-to-tags` | Speech preparation in `transform --apply` and the GUI |
| GUI Tools menu | Chapter overview, editorial reports, speech preparation, transcript export |

## Complete 500-feature status map

### Features 1–25 — Advanced Project Management

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 1 | Advanced Project Creation Wizard | 🗺 Roadmap | Phase 2 (weeks) — Guided GUI setup wizard |
| 2 | Reusable Project Templates | 🔶 Partial | Phase 2 (weeks) — Voice presets exist; full project templates remain |
| 3 | Automatic Project Saving | 🔶 Partial | Phase 3 (months) — Automatic backups exist; in-place autosave remains |
| 4 | Project Recovery System | ✅ Shipped |  |
| 5 | Project Version History | ✅ Shipped |  |
| 6 | Project Snapshots | ✅ Shipped |  |
| 7 | Project Comparison Tool | ✅ Shipped |  |
| 8 | Portable Project Packages | ✅ Shipped |  |
| 9 | Project Dependency Viewer | ✅ Shipped |  |
| 10 | Project Health Analyzer | 🆕 Added in 1.0.29 |  |
| 11 | Project Notes | ✅ Shipped | Notes stored in projects; library notes added in 1.0.29 |
| 12 | Global Project Search | 🆕 Added in 1.0.29 |  |
| 13 | Batch Project Renaming | 🆕 Added in 1.0.29 |  |
| 14 | Project Categories | ✅ Shipped | Category/tags fields ship in projects; library-wide category/tag management added in 1.0.29 |
| 15 | Project Tags | ✅ Shipped | Category/tags fields ship in projects; library-wide category/tag management added in 1.0.29 |
| 16 | Project Favorites | 🆕 Added in 1.0.29 |  |
| 17 | Multiple Project Tabs | 🗺 Roadmap | Phase 3 (months) — Multi-tab GUI architecture change |
| 18 | Project Activity History | 🗺 Roadmap | Phase 3 (months) — Per-project edit activity log |
| 19 | Project Bookmarks | 🆕 Added in 1.0.29 |  |
| 20 | Intelligent Missing-File Recovery | 🗺 Roadmap | Phase 3 (months) — Relocated-asset folder search |
| 21 | Project Duplicate Detection | 🆕 Added in 1.0.29 |  |
| 22 | Project Storage Analyzer | 🆕 Added in 1.0.29 |  |
| 23 | Read-Only Project Mode | 🗺 Roadmap | Phase 3 (months) — Read-only project mode |
| 24 | Automatic Project Backups | ✅ Shipped |  |
| 25 | Project Archive Manager | ✅ Shipped |  |

### Features 26–50 — Advanced Document Import and Conversion

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 26 | Advanced PDF Import | ✅ Shipped |  |
| 27 | DOCX Import Improvements | ✅ Shipped |  |
| 28 | ODT Import | ✅ Shipped |  |
| 29 | EPUB Import | ✅ Shipped |  |
| 30 | HTML Import | ✅ Shipped |  |
| 31 | Markdown Import | ✅ Shipped |  |
| 32 | RTF Import | ✅ Shipped | RTF listed among archive document formats |
| 33 | FictionBook Import | ✅ Shipped |  |
| 34 | DRM-Free MOBI/AZW Import | 🗺 Roadmap | Phase 3 (months) — DRM-free MOBI/AZW parsing (legacy Kindle formats) |
| 35 | Comic Archive Import | ✅ Shipped |  |
| 36 | Scanned Book Import | ✅ Shipped |  |
| 37 | Clipboard Import | 🗺 Roadmap | Phase 2 (weeks) — Clipboard import button (small GUI feature) |
| 38 | Web Article Import | 🗺 Roadmap | Phase 3 (months) — Web article fetch with permission handling |
| 39 | ZIP Document Import | ✅ Shipped |  |
| 40 | Multi-Document Book Assembly | ✅ Shipped | Repeated -f inputs and audiobook manifests assemble books |
| 41 | Automatic Folder Monitoring | 🗺 Roadmap | Phase 3 (months) — Watched-folder monitoring service |
| 42 | Advanced Drag-and-Drop Import | 🗺 Roadmap | Phase 3 (months) — Multi-file drag-and-drop into the GUI |
| 43 | Batch Import Presets | 🗺 Roadmap | Phase 3 (months) — Saved batch import rule presets |
| 44 | Character Encoding Detection | ✅ Shipped |  |
| 45 | Encoding Conversion Engine | ✅ Shipped |  |
| 46 | Automatic Line-Unwrapping | ✅ Shipped |  |
| 47 | Formatting Preservation | ✅ Shipped |  |
| 48 | Footnote Import | 🗺 Roadmap | Phase 2 (weeks) — Footnote extraction and organization |
| 49 | Table Interpretation | 🗺 Roadmap | Phase 3 (months) — Table-to-speech-friendly description conversion |
| 50 | Image Description Import | 🗺 Roadmap | Phase 3 (months) — Image alt-text preservation on import |

### Features 51–75 — Extremely Advanced OCR System

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 51 | Intelligent Image Preprocessing | ✅ Shipped |  |
| 52 | Automatic Skew Correction | ✅ Shipped |  |
| 53 | Perspective Correction | 🗺 Roadmap | Phase 3 (months) — Perspective correction for photographed pages |
| 54 | Advanced Image Denoising | ✅ Shipped |  |
| 55 | Blur Detection and Enhancement | 🗺 Roadmap | Phase 3 (months) — Blur detection and enhancement |
| 56 | Adaptive Contrast Enhancement | ✅ Shipped |  |
| 57 | Automatic Page Layout Analysis | 🔶 Partial | Phase 3 (months) — Tesseract PSM modes give basic layout handling |
| 58 | Multilingual OCR Script Detection | ✅ Shipped |  |
| 59 | Selective Region OCR | 🗺 Roadmap | Phase 2 (weeks) — User-selected region OCR |
| 60 | Intelligent Reading-Order Detection | 🔶 Partial | Phase 3 (months) — PSM auto layout; complex reading-order reconstruction remains |
| 61 | Multi-Column OCR | 🔶 Partial | Phase 3 (months) — PSM 3/4 handles common multi-column pages |
| 62 | Table OCR | 🗺 Roadmap | Phase 3 (months) — Cell-structure table recognition |
| 63 | Mathematical Formula Detection | 🗺 Roadmap | Phase 4 (major effort) — Math formula detection (specialized models) |
| 64 | Searchable PDF Layer Creation | 🗺 Roadmap | Phase 2 (weeks) — Text-layer PDF creation (Tesseract PDF output) |
| 65 | OCR Confidence Visualization | ✅ Shipped |  |
| 66 | Interactive OCR Correction Workspace | ✅ Shipped |  |
| 67 | Dictionary-Assisted OCR Correction | ✅ Shipped |  |
| 68 | Cross-Page Hyphenation Repair | ✅ Shipped |  |
| 69 | Historical Typography Recognition | 🗺 Roadmap | Phase 4 (major effort) — Historical typeface OCR workflows |
| 70 | Batch OCR Processing | ✅ Shipped |  |
| 71 | OCR Comparison Mode | 🗺 Roadmap | Phase 3 (months) — Side-by-side OCR engine comparison |
| 72 | Image-to-Text Alignment | 🗺 Roadmap | Phase 3 (months) — Word-to-image location mapping (Tesseract TSV) |
| 73 | Formatting-Aware OCR | 🗺 Roadmap | Phase 3 (months) — Bold/italic-aware OCR |
| 74 | Marginal Note Recognition | 🗺 Roadmap | Phase 4 (major effort) — Marginalia separation (handwriting recognition) |
| 75 | OCR Quality Scoring | ✅ Shipped |  |

### Features 76–100 — Intelligent Text Editor and Proofreading

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 76 | Advanced Grammar Correction | 🗺 Roadmap | Phase 2 (weeks) — Grammar engine integration (e.g. rule-based checker) |
| 77 | Nonintrusive Spelling Suggestions | ✅ Shipped |  |
| 78 | Keyboard-Based Correction Navigation | ✅ Shipped |  |
| 79 | Custom Dictionary Manager | ✅ Shipped | Custom dictionaries via spelling settings and name-list import |
| 80 | Project Terminology Dictionaries | 🔶 Partial | Phase 3 (months) — IPA/terminology dictionaries exist per project |
| 81 | Proper-Name Consistency Checker | 🆕 Added in 1.0.29 |  |
| 82 | Automatic Punctuation Cleanup | ✅ Shipped | Cleanup transforms existed; 1.0.29 adds the artifact report |
| 83 | OCR Error Pattern Learning | 🗺 Roadmap | Phase 3 (months) — Learning recurring OCR mistakes per project |
| 84 | Quotation Mark Normalization | ✅ Shipped |  |
| 85 | Dialogue Punctuation Checker | 🆕 Added in 1.0.29 |  |
| 86 | Custom Writing Style Guides | 🗺 Roadmap | Phase 3 (months) — Configurable editorial style guides |
| 87 | Contextual Language Issue Detection | 🗺 Roadmap | Phase 4 (major effort) — Contextual word-choice detection needs a language model |
| 88 | Side-by-Side Text Comparison | 🔶 Partial | Phase 3 (months) — Project-version comparison exists; editor passage compare remains |
| 89 | Track Changes | 🗺 Roadmap | Phase 3 (months) — Reviewable tracked changes |
| 90 | Unlimited Editing History | ✅ Shipped |  |
| 91 | Regular Expression Search | ✅ Shipped |  |
| 92 | Batch Replacement Preview | ✅ Shipped |  |
| 93 | Character Tag Syntax Highlighting | 🔶 Partial | Phase 3 (months) — Timing/character tags parsed; dedicated highlighting remains |
| 94 | Protected Text Regions | 🗺 Roadmap | Phase 3 (months) — Protected (locked) text regions |
| 95 | Pronunciation Override Editor | ✅ Shipped |  |
| 96 | Non-Destructive Text Transformations | 🗺 Roadmap | Phase 3 (months) — Reversible non-destructive transformation stack |
| 97 | Grammar and Readability Statistics | 🆕 Added in 1.0.29 |  |
| 98 | Duplicate Paragraph Detection | ✅ Shipped |  |
| 99 | Cross-Chapter Terminology Consistency | 🆕 Added in 1.0.29 |  |
| 100 | Synchronized Read-Aloud Editing | 🗺 Roadmap | Phase 3 (months) — Playback-position text highlighting |

### Features 101–125 — Chapter, Section, and Book Structure Management

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 101 | Intelligent Chapter Detection | ✅ Shipped | v1.0.28 keyword splitter; 1.0.29 adds Markdown/numbered/ALL-CAPS/custom rules |
| 102 | Configurable Chapter Recognition Rules | 🆕 Added in 1.0.29 |  |
| 103 | Drag-and-Drop Chapter Reordering | 🔶 Partial | Phase 3 (months) — Data-level reordering in 1.0.29; GUI drag-and-drop remains |
| 104 | Chapter Splitting and Merging | 🆕 Added in 1.0.29 |  |
| 105 | Hierarchical Section Management | 🆕 Added in 1.0.29 |  |
| 106 | Front-Matter Management | 🔶 Partial | Phase 3 (months) — Front matter auto-detected; dedicated management UI remains |
| 107 | Back-Matter Management | 🗺 Roadmap | Phase 3 (months) — Back-matter (appendix/glossary) management |
| 108 | Automatic Table of Contents Generation | 🆕 Added in 1.0.29 |  |
| 109 | Footnote Narration Rules | 🗺 Roadmap | Phase 3 (months) — Footnote narration rules |
| 110 | Nested Quotation Handling | ✅ Shipped | Nested quote attribution in the character engine |
| 111 | Scene Break Detection | ✅ Shipped | Scene boundaries in character engine; 1.0.29 adds standalone detection |
| 112 | Author's Note Recognition | 🗺 Roadmap | Phase 3 (months) — Author-note recognition |
| 113 | Automatic Page Number Removal | ✅ Shipped | Existing splitter; detection greatly extended in 1.0.29 |
| 114 | Header and Footer Detection | ✅ Shipped | Repeated-header stripping existed; 1.0.29 adds detection reports |
| 115 | Section Metadata Editor | 🆕 Added in 1.0.29 |  |
| 116 | Interactive Chapter Navigator | 🗺 Roadmap | Phase 2 (weeks) — GUI chapter navigator panel |
| 117 | Scene Timeline | 🗺 Roadmap | Phase 3 (months) — Visual scene timeline |
| 118 | Batch Chapter Formatting | 🗺 Roadmap | Phase 3 (months) — Batch chapter formatting |
| 119 | Custom Chapter Title Pronunciation | 🔶 Partial | Phase 3 (months) — Inline IPA covers custom pronunciation manually |
| 120 | Chapter-Specific Narration Settings | 🔶 Partial | Phase 3 (months) — Per-book voice projects; per-chapter narration settings remain |
| 121 | Independent Chapter Export | ✅ Shipped | Existing splitter; detection greatly extended in 1.0.29 |
| 122 | Chapter Duration Estimation | 🆕 Added in 1.0.29 |  |
| 123 | Chapter Completion Tracking | 🆕 Added in 1.0.29 |  |
| 124 | Chapter-Specific Intro and Outro Templates | 🗺 Roadmap | Phase 3 (months) — Chapter intro/outro audio templates |
| 125 | Chapter Preview Queue | 🗺 Roadmap | Phase 3 (months) — Chapter preview queue |

### Features 126–150 — Advanced Character Detection and Dialogue Attribution

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 126 | Multi-Algorithm Character Recognition | ✅ Shipped |  |
| 127 | Character Alias Detection | ✅ Shipped |  |
| 128 | Pronoun-Based Speaker Identification | ✅ Shipped |  |
| 129 | Unnamed Character Tracking | ✅ Shipped |  |
| 130 | Character Identity Linking | ✅ Shipped |  |
| 131 | Character Relationship Graph | 🗺 Roadmap | Phase 3 (months) — Visual character relationship graph |
| 132 | Speaker Attribution Confidence Scores | ✅ Shipped |  |
| 133 | Uncertain Dialogue Review Queue | ✅ Shipped |  |
| 134 | Multi-Paragraph Dialogue Recognition | ✅ Shipped |  |
| 135 | Nested Dialogue Attribution | ✅ Shipped |  |
| 136 | Indirect Speech Recognition | 🗺 Roadmap | Phase 3 (months) — Reported-speech vs direct-quote classification |
| 137 | Cross-Chapter Character Continuity | ✅ Shipped |  |
| 138 | Narrator and Character Separation | ✅ Shipped |  |
| 139 | Internal Monologue Recognition | 🗺 Roadmap | Phase 3 (months) — Internal monologue recognition |
| 140 | Thought-versus-Dialogue Classification | 🗺 Roadmap | Phase 3 (months) — Thought-vs-dialogue classification |
| 141 | Speech Verb Analysis | ✅ Shipped |  |
| 142 | Dialogue Attribution Timeline | 🗺 Roadmap | Phase 3 (months) — Speaker-change timeline visualization |
| 143 | Interactive Speaker Correction | ✅ Shipped |  |
| 144 | Explainable Speaker Detection | ✅ Shipped |  |
| 145 | Character Merge Tool | 🔶 Partial | Phase 3 (months) — Alias/identity linking merges duplicates; explicit merge tool remains |
| 146 | Character Split Tool | 🗺 Roadmap | Phase 3 (months) — Split incorrectly merged characters |
| 147 | Dialogue Distribution Statistics | 🔶 Partial | Phase 3 (months) — Quote line counts exist; distribution statistics remain |
| 148 | Custom Speaker Recognition Rules | 🔶 Partial | Phase 3 (months) — Alias rules exist; general custom attribution rules remain |
| 149 | Character Appearance and Mention Tracker | 🔶 Partial | Phase 3 (months) — Quote line numbers exist; full mention tracking remains |
| 150 | Multilingual Quotation Recognition | ✅ Shipped |  |

### Features 151–175 — Universal Text-to-Speech Engine Framework

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 151 | Universal TTS Plugin Architecture | 🔶 Partial | Phase 3 (months) — Engine registry is extensible; a public plugin API remains |
| 152 | Automatic Engine Capability Detection | ✅ Shipped |  |
| 153 | Engine Compatibility Analyzer | ✅ Shipped |  |
| 154 | Isolated Engine Environments | ✅ Shipped |  |
| 155 | CPU Performance Profiles | 🗺 Roadmap | Phase 2 (weeks) — CPU performance profiles (low/mid/high presets) |
| 156 | Optional GPU Acceleration | ✅ Shipped |  |
| 157 | Automatic Engine Fallback | ✅ Shipped |  |
| 158 | Paragraph-Level Engine Selection | 🔶 Partial | Phase 3 (months) — Per-character engine selection exists; arbitrary paragraph selection remains |
| 159 | Strict Offline Synthesis Mode | ✅ Shipped |  |
| 160 | Local TTS Server Mode | 🗺 Roadmap | Phase 2 (weeks) — Local TTS server mode for other apps |
| 161 | Engine Diagnostics Center | ✅ Shipped |  |
| 162 | TTS Engine Benchmarking | 🗺 Roadmap | Phase 2 (weeks) — Engine benchmarking (speed/memory/output) |
| 163 | Intelligent Synthesis Queue | 🔶 Partial | Phase 3 (months) — Sequential job queue exists; resource-aware scheduling remains |
| 164 | Engine-Specific Text Normalization | ✅ Shipped |  |
| 165 | Streaming Speech Generation | 🗺 Roadmap | Phase 3 (months) — Streaming synthesis playback |
| 166 | Adaptive Text Chunking | ✅ Shipped |  |
| 167 | Interrupted Synthesis Recovery | 🗺 Roadmap | Phase 2 (weeks) — Resume synthesis without regenerating finished passages |
| 168 | Reproducible Synthesis Settings | ✅ Shipped |  |
| 169 | Automatic Sample-Rate Compatibility | ✅ Shipped |  |
| 170 | Engine Feature Detection | ✅ Shipped |  |
| 171 | Speech Engine Process Isolation | ✅ Shipped |  |
| 172 | CPU and Memory Resource Governor | 🗺 Roadmap | Phase 3 (months) — CPU/memory resource governor |
| 173 | Speech Engine Watchdog | 🗺 Roadmap | Phase 2 (weeks) — Stalled-engine watchdog |
| 174 | Engine Version Pinning | ✅ Shipped |  |
| 175 | On-Demand Engine Loading | ✅ Shipped |  |

### Features 176–200 — Advanced Voice and Model Management

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 176 | Unified Voice Library | ✅ Shipped |  |
| 177 | Automatic Multi-Speaker Enumeration | ✅ Shipped |  |
| 178 | Individual Voice Preview Samples | ✅ Shipped |  |
| 179 | Side-by-Side Voice Comparison | 🗺 Roadmap | Phase 2 (weeks) — Side-by-side identical-text voice comparison |
| 180 | Explicit Voice Download Approval | ✅ Shipped |  |
| 181 | Detailed Download Progress | ✅ Shipped |  |
| 182 | Model Integrity Verification | ✅ Shipped |  |
| 183 | Voice Licensing Information | 🔶 Partial | Phase 3 (months) — Third-party notices exist; per-voice license display remains |
| 184 | Model Storage Information | ✅ Shipped |  |
| 185 | Accent-Based Voice Filtering | 🔶 Partial | Phase 2 (weeks) — Locale metadata exists; accent-based filtering remains |
| 186 | Language-Based Voice Filtering | ✅ Shipped |  |
| 187 | Voice Favorites | 🗺 Roadmap | Phase 2 (weeks) — Voice favorites/tags/collection presets (library-style metadata) |
| 188 | Voice Tags | 🗺 Roadmap | Phase 2 (weeks) — Voice favorites/tags/collection presets (library-style metadata) |
| 189 | Offline Voice Preview Library | 🗺 Roadmap | Phase 3 (months) — Offline voice preview sample library |
| 190 | Installed Voice Manager | ✅ Shipped |  |
| 191 | Duplicate Voice File Detection | 🗺 Roadmap | Phase 2 (weeks) — Duplicate voice file detection |
| 192 | Custom Voice Model Import | ✅ Shipped |  |
| 193 | Voice Format Conversion | 🗺 Roadmap | Phase 4 (major effort) — Voice format conversion (model-dependent) |
| 194 | Voice Cache Repair | 🔶 Partial | Phase 2 (weeks) — Engine install repair exists; voice cache repair remains |
| 195 | Voice Pack Import and Export | 🗺 Roadmap | Phase 2 (weeks) — Voice pack import/export between computers |
| 196 | Voice Model Version Locking | 🗺 Roadmap | Phase 3 (months) — Model version locking |
| 197 | Voice Quality Evaluation | 🗺 Roadmap | Phase 3 (months) — Voice quality evaluation tools |
| 198 | Queued Manual Downloads | ✅ Shipped |  |
| 199 | Resumable Model Downloads | 🗺 Roadmap | Phase 3 (months) — Resumable downloads |
| 200 | Voice Collection Presets | 🗺 Roadmap | Phase 2 (weeks) — Voice favorites/tags/collection presets (library-style metadata) |

### Features 201–225 — Intelligent Character Voice Profiles

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 201 | Detailed Character Voice Profiles | ✅ Shipped |  |
| 202 | Voice Casting Workspace | ✅ Shipped |  |
| 203 | Multiple Narrator Profiles | 🔶 Partial | Phase 3 (months) — Per-book narrators via manifests; per-section narrators remain |
| 204 | Character-Specific Speaking Speed | ✅ Shipped |  |
| 205 | Character-Specific Pitch Controls | ✅ Shipped |  |
| 206 | Character-Specific Vocal Energy | ✅ Shipped |  |
| 207 | Character-Specific Pause Settings | ✅ Shipped |  |
| 208 | Character Pronunciation Dictionaries | ✅ Shipped |  |
| 209 | Character Emotion Presets | ✅ Shipped | Emotion/style presets via voice design styles |
| 210 | Character Whispering Mode | ✅ Shipped |  |
| 211 | Character Accent Preferences | ✅ Shipped |  |
| 212 | Contextual Dialogue Delivery | ✅ Shipped |  |
| 213 | Character Voice Consistency Checker | ✅ Shipped |  |
| 214 | Character Voice Inheritance | 🗺 Roadmap | Phase 3 (months) — Voice profile inheritance/templates |
| 215 | Alternative Character Voice Takes | 🗺 Roadmap | Phase 3 (months) — Alternative takes per dialogue line |
| 216 | Character Audition Studio | 🔶 Partial | Phase 3 (months) — Per-character preview exists; dedicated audition studio remains |
| 217 | Voice Compatibility Recommendations | ✅ Shipped |  |
| 218 | Character-to-Speaker Mapping | ✅ Shipped |  |
| 219 | Character Profile Search | 🗺 Roadmap | Phase 2 (weeks) — Character profile search |
| 220 | Backup Character Voices | 🗺 Roadmap | Phase 3 (months) — Fallback voice definitions |
| 221 | Suggested Automatic Voice Casting | ✅ Shipped |  |
| 222 | Character Loudness Targets | ✅ Shipped |  |
| 223 | Dialogue Turn-Taking Controls | ✅ Shipped |  |
| 224 | Scene-Specific Character Performance | 🗺 Roadmap | Phase 3 (months) — Scene-specific performance overrides |
| 225 | Voice Profile Testing Scripts | 🗺 Roadmap | Phase 3 (months) — Reusable voice test scripts |

### Features 226–250 — Expressive Speech and Prosody Engine

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 226 | Sentence Emphasis Editor | 🗺 Roadmap | Phase 2 (weeks) — Word-emphasis editor (engine-dependent) |
| 227 | Unified SSML Compatibility Layer | 🗺 Roadmap | Phase 3 (months) — SSML compatibility layer |
| 228 | Automatic Punctuation Interpretation | ✅ Shipped |  |
| 229 | Custom Pause Insertion | ✅ Shipped |  |
| 230 | Pronunciation Dictionary with IPA Support | ✅ Shipped |  |
| 231 | Abbreviation Expansion Rules | 🆕 Added in 1.0.29 |  |
| 232 | Custom Proper-Noun Pronunciation | ✅ Shipped |  |
| 233 | Number Narration Settings | 🆕 Added in 1.0.29 |  |
| 234 | Date and Time Pronunciation | 🆕 Added in 1.0.29 |  |
| 235 | Homograph Disambiguation | 🗺 Roadmap | Phase 3 (months) — Homograph disambiguation rules engine |
| 236 | Phoneme-Level Pronunciation Editor | ✅ Shipped |  |
| 237 | Natural Speech Rhythm Controls | 🔶 Partial | Phase 3 (months) — Rate controls exist; phrasing rhythm controls remain |
| 238 | Advanced Prosody Curves | 🗺 Roadmap | Phase 4 (major effort) — Editable prosody curves |
| 239 | Emotion-Aware Speech Markup | 🔶 Partial | Phase 3 (months) — Style-based emotion presets; SSML emotion markup remains |
| 240 | Optional Breathing Sounds | 🗺 Roadmap | Phase 4 (major effort) — Optional breathing sounds |
| 241 | Seamless Sentence Joining | 🔶 Partial | Phase 3 (months) — Chunk merging exists; discontinuity reduction remains |
| 242 | Intelligent Silence Trimming | 🗺 Roadmap | Phase 2 (weeks) — Intelligent silence trimming |
| 243 | Automatic Pause Variation | 🗺 Roadmap | Phase 3 (months) — Automatic pause-length variation |
| 244 | Dialogue Hesitation Controls | ✅ Shipped |  |
| 245 | Paragraph-Level Pacing | 🔶 Partial | Phase 3 (months) — Per-chunk pacing; paragraph pacing UI remains |
| 246 | Chapter-Level Pacing Curves | 🗺 Roadmap | Phase 3 (months) — Chapter-level pacing curves |
| 247 | Expressive Scene Transitions | 🔶 Partial | Phase 3 (months) — Scene boundaries exist; transition narration settings remain |
| 248 | Contextual Emphasis Suggestions | 🗺 Roadmap | Phase 3 (months) — Contextual emphasis suggestions |
| 249 | Pronunciation Audit Report | 🆕 Added in 1.0.29 |  |
| 250 | Ellipsis and Dash Interpretation | 🆕 Added in 1.0.29 |  |

### Features 251–275 — Comprehensive Multilingual Support

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 251 | Automatic Language Detection | ✅ Shipped |  |
| 252 | Script-Aware Text Processing | ✅ Shipped |  |
| 253 | Bidirectional Text Support | ✅ Shipped |  |
| 254 | Language Detection by Paragraph | ✅ Shipped |  |
| 255 | Mixed-Language Sentence Processing | 🔶 Partial | Phase 3 (months) — Paragraph-level detection exists; sentence-level mixing remains |
| 256 | Intelligent Font Fallback | ✅ Shipped |  |
| 257 | Per-Language Pronunciation Dictionaries | ✅ Shipped |  |
| 258 | Language-Specific Text Normalization | 🔶 Partial | Phase 3 (months) — Unicode/whitespace normalization exists; per-language rules remain |
| 259 | Unicode Normalization Controls | ✅ Shipped |  |
| 260 | Automatic Transliteration Suggestions | 🗺 Roadmap | Phase 3 (months) — Automatic transliteration suggestions |
| 261 | Language-Specific Number Reading | 🔶 Partial | Phase 3 (months) — English number narration added in 1.0.29; other locales remain |
| 262 | Localized Date and Currency Narration | 🗺 Roadmap | Phase 3 (months) — Localized date/currency narration beyond English |
| 263 | Languages Without Word Spaces | ✅ Shipped |  |
| 264 | Advanced Indic Script Shaping | ✅ Shipped |  |
| 265 | CJK Text Segmentation | ✅ Shipped |  |
| 266 | Arabic Diacritic Processing | 🔶 Partial | Phase 3 (months) — Arabic shaping works; diacritic-aware processing remains |
| 267 | Regional Language Variants | 🔶 Partial | Phase 3 (months) — Locale voices matched; explicit variant handling remains |
| 268 | Multilingual Character Voice Continuity | ✅ Shipped |  |
| 269 | Romanization Management | 🗺 Roadmap | Phase 3 (months) — Configurable romanization standards |
| 270 | Multilingual Dialogue Tagging | 🔶 Partial | Phase 3 (months) — Per-character languages exist; per-passage tagging remains |
| 271 | Voice-Language Compatibility Filtering | ✅ Shipped |  |
| 272 | Script-Specific Punctuation Rules | 🔶 Partial | Phase 3 (months) — Multilingual quotes exist; script punctuation rules remain |
| 273 | Complex Grapheme Navigation | ✅ Shipped |  |
| 274 | Language-Specific Speech Testing | 🗺 Roadmap | Phase 3 (months) — Per-language pronunciation test passages |
| 275 | Mixed-Script Audiobook Validation | 🗺 Roadmap | Phase 2 (weeks) — Mixed-script audiobook validation report |

### Features 276–300 — Professional Audio Editing and Mastering

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 276 | Interactive Waveform Editor | 🗺 Roadmap | Phase 3 (months) — Interactive waveform editor |
| 277 | Multitrack Audio Timeline | 🗺 Roadmap | Phase 3 (months) — Multitrack timeline editor (mixing exists, editor remains) |
| 278 | Precision Audio Cutting | ✅ Shipped |  |
| 279 | Fade-In and Fade-Out Controls | ✅ Shipped |  |
| 280 | Automatic Silence Detection | ✅ Shipped |  |
| 281 | Noise Reduction | ✅ Shipped |  |
| 282 | De-Esser | 🗺 Roadmap | Phase 2 (weeks) — De-esser (FFmpeg deesser filter wiring) |
| 283 | Parametric Equalizer | 🗺 Roadmap | Phase 2 (weeks) — Parametric equalizer |
| 284 | Dynamic Range Compressor | ✅ Shipped |  |
| 285 | True-Peak Limiter | ✅ Shipped | Loudness normalization chain includes true-peak limiting |
| 286 | Loudness Normalization | ✅ Shipped |  |
| 287 | True-Peak Analysis | ✅ Shipped |  |
| 288 | Mono and Stereo Processing | ✅ Shipped |  |
| 289 | Room-Tone Management | 🗺 Roadmap | Phase 3 (months) — Room-tone management |
| 290 | Passage-Level Loudness Matching | 🔶 Partial | Phase 3 (months) — Per-file normalization; passage-level matching remains |
| 291 | Click and Pop Detection | 🗺 Roadmap | Phase 3 (months) — Click/pop detection |
| 292 | Real-Time Effects Preview | 🔶 Partial | Phase 3 (months) — Speak/preview exists; effects preview remains |
| 293 | Audio Spectrogram Viewer | 🗺 Roadmap | Phase 3 (months) — Spectrogram viewer |
| 294 | Clipping Detection | ✅ Shipped |  |
| 295 | Synthesis Artifact Detection | 🗺 Roadmap | Phase 4 (major effort) — Synthesis artifact detection |
| 296 | Automatic Crossfading | 🔶 Partial | Phase 3 (months) — Fade filters exist; automatic crossfade chains remain |
| 297 | Missing Audio Segment Detection | 🗺 Roadmap | Phase 2 (weeks) — Missing audio segment detection |
| 298 | Audio Duration Recalculation | ✅ Shipped |  |
| 299 | Selective Passage Regeneration | 🗺 Roadmap | Phase 3 (months) — Selective passage regeneration |
| 300 | Automated Audio Quality Report | ✅ Shipped |  |

### Features 301–325 — Background Music, Sound Effects, and Audio Drama

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 301 | Background Music Manager | ✅ Shipped |  |
| 302 | Automatic Music Ducking | 🔶 Partial | Phase 3 (months) — FFmpeg mixing exists; automatic ducking curves remain |
| 303 | Scene-Based Music Assignment | ✅ Shipped |  |
| 304 | Music Licensing Tracker | 🔶 Partial | Phase 3 (months) — Attribution documents (1.0.29) record licenses; tracker UI remains |
| 305 | Sound Effects Library | ✅ Shipped |  |
| 306 | Sound Effects Timeline | ✅ Shipped |  |
| 307 | Ambient Soundscapes | ✅ Shipped |  |
| 308 | Reusable Sound Design Templates | 🗺 Roadmap | Phase 3 (months) — Reusable sound design templates |
| 309 | Sidechain Compression | 🗺 Roadmap | Phase 2 (weeks) — Sidechain compression |
| 310 | Environmental Sound Presets | 🗺 Roadmap | Phase 3 (months) — Environmental sound presets |
| 311 | Stereo Panning Controls | 🗺 Roadmap | Phase 2 (weeks) — Stereo panning controls |
| 312 | Convolution Reverb | 🗺 Roadmap | Phase 3 (months) — Convolution reverb |
| 313 | Scene-Based Sound Palettes | 🗺 Roadmap | Phase 3 (months) — Scene-based sound palettes |
| 314 | Cinematic Audio Transitions | 🗺 Roadmap | Phase 3 (months) — Cinematic audio transitions |
| 315 | Dialogue Priority Mixing | ✅ Shipped |  |
| 316 | Sound Effects Preview Browser | 🔶 Partial | Phase 3 (months) — SFX import/management exists; audition browser remains |
| 317 | Looping Ambient Audio | 🔶 Partial | Phase 3 (months) — Background tags loop ambience; seamless looping controls remain |
| 318 | Audio Automation Curves | 🗺 Roadmap | Phase 3 (months) — Audio automation curves |
| 319 | Scene Boundary Markers | ✅ Shipped |  |
| 320 | Custom Sound Effect Import | ✅ Shipped |  |
| 321 | Music Edit Markers | 🗺 Roadmap | Phase 3 (months) — Music edit markers |
| 322 | Audio Stem Export | 🗺 Roadmap | Phase 2 (weeks) — Separate stem export (narration/music/effects) |
| 323 | Narration-Only Export Mode | ✅ Shipped |  |
| 324 | Reference Mix Comparison | 🗺 Roadmap | Phase 3 (months) — Reference mix comparison |
| 325 | Audio Drama Production Mode | ✅ Shipped | Timed multi-character scenes with SFX/background/overlap (1.0.27) |

### Features 326–350 — Intelligent Audiobook Production Automation

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 326 | Audiobook Production Dashboard | 🆕 Added in 1.0.29 |  |
| 327 | Scene Production Status | 🔶 Partial | Phase 3 (months) — Chapter stages added in 1.0.29; scene-level status remains |
| 328 | Chapter Workflow Status | 🆕 Added in 1.0.29 |  |
| 329 | Advanced Rendering Queue | 🔶 Partial | Phase 3 (months) — Batch processing exists; full render queue remains |
| 330 | Crash-Resistant Render Resumption | 🗺 Roadmap | Phase 2 (weeks) — Crash-resistant render resumption |
| 331 | Selective Regeneration | 🗺 Roadmap | Phase 3 (months) — Change-aware selective regeneration |
| 332 | Content-Hash Audio Caching | 🗺 Roadmap | Phase 3 (months) — Content-hash audio caching |
| 333 | Scheduled Rendering | 🗺 Roadmap | Phase 3 (months) — Scheduled rendering |
| 334 | Batch Audiobook Creation | ✅ Shipped |  |
| 335 | Multicore CPU Scheduling | 🔶 Partial | Phase 3 (months) — FFmpeg is multicore; synthesis scheduling remains |
| 336 | Low-Memory Production Mode | 🗺 Roadmap | Phase 3 (months) — Low-memory production mode |
| 337 | Energy-Saving Rendering Mode | 🗺 Roadmap | Phase 4 (major effort) — Energy-saving rendering mode |
| 338 | Temperature-Aware Performance Management | 🗺 Roadmap | Phase 4 (major effort) — Temperature-aware performance management |
| 339 | Battery-Aware Processing | 🗺 Roadmap | Phase 4 (major effort) — Battery-aware processing |
| 340 | Storage Availability Monitoring | 🗺 Roadmap | Phase 2 (weeks) — Disk-space monitoring with warnings |
| 341 | Rendering Time Estimation | 🆕 Added in 1.0.29 |  |
| 342 | Production Preset Manager | ✅ Shipped |  |
| 343 | Dry-Run Production Mode | ✅ Shipped |  |
| 344 | Optional Background Rendering | ✅ Shipped |  |
| 345 | Detailed Production Logs | 🆕 Added in 1.0.29 |  |
| 346 | Quality-Control Checkpoints | 🆕 Added in 1.0.29 |  |
| 347 | Chapter Approval Workflow | 🆕 Added in 1.0.29 |  |
| 348 | Production Pipeline Templates | 🗺 Roadmap | Phase 3 (months) — Production pipeline templates |
| 349 | Resource Usage Forecasting | 🆕 Added in 1.0.29 |  |
| 350 | Production Queue Priorities | 🗺 Roadmap | Phase 3 (months) — Production queue priorities |

### Features 351–375 — Advanced Audiobook Video Generation

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 351 | Video Template Library | 🗺 Roadmap | Phase 3 (months) — Reusable video template library |
| 352 | Audio-Synchronized Subtitles | ✅ Shipped |  |
| 353 | Word-by-Word Highlighting | ✅ Shipped |  |
| 354 | Advanced Typewriter Animation | ✅ Shipped |  |
| 355 | Karaoke-Style Text Highlighting | ✅ Shipped |  |
| 356 | Scrolling Book Text | ✅ Shipped |  |
| 357 | Static Cover Video Mode | ✅ Shipped |  |
| 358 | Ken Burns Effect | 🗺 Roadmap | Phase 2 (weeks) — Ken Burns pan/zoom effect |
| 359 | Scene-Specific Title Cards | 🗺 Roadmap | Phase 2 (weeks) — Scene-specific title cards |
| 360 | Vertical Video Mode | ✅ Shipped |  |
| 361 | Custom Aspect Ratios | ✅ Shipped |  |
| 362 | Optional 4K Video Rendering | ✅ Shipped |  |
| 363 | Frame-Accurate Timing | ✅ Shipped |  |
| 364 | Animation Easing Controls | 🗺 Roadmap | Phase 3 (months) — Animation easing controls |
| 365 | Advanced Video Transitions | 🔶 Partial | Phase 3 (months) — Motion modes (fade/zoom/slide) exist; transition effects remain |
| 366 | Animated Paper Backgrounds | ✅ Shipped |  |
| 367 | Accessible Caption Color Presets | 🔶 Partial | Phase 3 (months) — Configurable caption colors; preset gallery remains |
| 368 | Caption Collision Detection | 🗺 Roadmap | Phase 3 (months) — Caption collision detection |
| 369 | Live Video Layout Preview | 🔶 Partial | Phase 3 (months) — Frame-exact rendering exists; live layout preview remains |
| 370 | Subtitle Safe-Zone Manager | 🗺 Roadmap | Phase 3 (months) — Subtitle safe-zone manager |
| 371 | Multilingual Video Font Management | ✅ Shipped |  |
| 372 | Manual Subtitle Timing Editor | 🔶 Partial | Phase 2 (weeks) — Timing files are editable; dedicated timing editor remains |
| 373 | Text Animation Effects Library | ✅ Shipped |  |
| 374 | Audio Waveform Visualizer | 🗺 Roadmap | Phase 3 (months) — Audio waveform visualizer |
| 375 | Reading Progress Visualization | 🗺 Roadmap | Phase 3 (months) — Reading progress visualization |

### Features 376–400 — Extremely Advanced Handwriting and Calligraphy Engine

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 376 | True Stroke-Based Handwriting Engine | ✅ Shipped |  |
| 377 | Vector Stroke Representation | ✅ Shipped |  |
| 378 | Pressure-Sensitive Pen Simulation | ✅ Shipped |  |
| 379 | Realistic Brush Calligraphy | ✅ Shipped |  |
| 380 | Multiple Pen Types | ✅ Shipped |  |
| 381 | Calligraphy Nib Angle Control | ✅ Shipped |  |
| 382 | Realistic Ink Bleeding | ✅ Shipped |  |
| 383 | Dynamic Stroke Velocity | ✅ Shipped |  |
| 384 | Stroke Order Management | ✅ Shipped |  |
| 385 | Handwritten Punctuation | ✅ Shipped |  |
| 386 | Script-Specific Handwriting Models | 🔶 Partial | Phase 3 (months) — Per-script stroke data is user-supplied; bundled script models remain |
| 387 | Connected-Letter Handwriting | ✅ Shipped |  |
| 388 | Right-to-Left Handwriting Animation | ✅ Shipped |  |
| 389 | CJK Stroke-Order Animation | ✅ Shipped |  |
| 390 | Indic Handwriting Support | ✅ Shipped |  |
| 391 | Natural Baseline Variation | 🔶 Partial | Phase 3 (months) — Natural variation via pressure/grain; baseline modeling remains |
| 392 | Realistic Pen Lifts | ✅ Shipped |  |
| 393 | Synchronized Writing Animation | ✅ Shipped |  |
| 394 | Handwriting Correction Animation | 🗺 Roadmap | Phase 4 (major effort) — Correction animation (erase/rewrite) |
| 395 | Notebook Line Templates | 🗺 Roadmap | Phase 2 (weeks) — Ruled/grid notebook templates |
| 396 | Paper Texture Simulation | ✅ Shipped |  |
| 397 | Animated Pen Cursor | ✅ Shipped |  |
| 398 | Custom Handwritten Character Editor | ✅ Shipped |  |
| 399 | Handwriting Style Presets | ✅ Shipped |  |
| 400 | Handwriting-to-Video Rendering | ✅ Shipped |  |

### Features 401–425 — Cover Art, Illustrations, and Visual Production

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 401 | Integrated Book Cover Designer | 🗺 Roadmap | Phase 3 (months) — Integrated cover designer |
| 402 | Cover Layout Grid | 🗺 Roadmap | Phase 3 (months) — Cover layout grid |
| 403 | Cover Template Library | 🗺 Roadmap | Phase 3 (months) — Cover template library |
| 404 | Custom Cover Import | ✅ Shipped | Cover/cover-image import for videos and slideshows |
| 405 | Chapter Illustration Manager | 🗺 Roadmap | Phase 2 (weeks) — Chapter illustration manager |
| 406 | Image Timeline Editor | ✅ Shipped | Multiple covers change during playback on the image timeline |
| 407 | Custom Text Boxes | 🔶 Partial | Phase 3 (months) — Styled text overlay exists; free text boxes remain |
| 408 | Optional AI Image Generation Integration | 🗺 Roadmap | Phase 4 (major effort) — Optional AI image generation integration |
| 409 | Visual Theme Packs | 🗺 Roadmap | Phase 3 (months) — Visual theme packs |
| 410 | Manga and Comic Panel Navigation | 🗺 Roadmap | Phase 4 (major effort) — Manga/comic panel navigation |
| 411 | Parallax Image Animation | 🗺 Roadmap | Phase 3 (months) — Parallax image animation |
| 412 | Illustration Alternative Text | 🗺 Roadmap | Phase 2 (weeks) — Illustration alternative text |
| 413 | Advanced Image Cropping | 🔶 Partial | Phase 3 (months) — Fit modes exist; advanced cropping/reframing remains |
| 414 | Animated Backgrounds | ✅ Shipped | Animated text/background modes |
| 415 | Watermark Manager | 🗺 Roadmap | Phase 2 (weeks) — Watermark manager |
| 416 | Branding Presets | 🗺 Roadmap | Phase 3 (months) — Branding presets |
| 417 | Multilayer Visual Compositing | 🔶 Partial | Phase 3 (months) — Image+text compositing exists; multilayer editor remains |
| 418 | Light and Dark Visual Themes | 🔶 Partial | Phase 3 (months) — Configurable colors; full light/dark theme packs remain |
| 419 | Animated Book Title Sequences | 🗺 Roadmap | Phase 3 (months) — Animated title sequences |
| 420 | Chapter Opening Illustrations | 🔶 Partial | Phase 3 (months) — Per-chapter covers exist; opening illustration workflow remains |
| 421 | Smart Image Focus Points | 🗺 Roadmap | Phase 3 (months) — Smart image focus points |
| 422 | Color Palette Manager | 🗺 Roadmap | Phase 3 (months) — Color palette manager |
| 423 | Narrated Slideshow Mode | ✅ Shipped | Classic narrated slideshow mode |
| 424 | Animated Music Visualizers | 🗺 Roadmap | Phase 3 (months) — Animated music visualizers |
| 425 | Automatic Credits Generator | 🆕 Added in 1.0.29 | Attribution/credits document generator |

### Features 426–450 — Accessibility, Interface, and User Experience

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 426 | Fully Scalable Interface | 🔶 Partial | Phase 3 (months) — Editor font scaling exists; full UI scaling remains |
| 427 | High-Contrast Accessibility Themes | 🗺 Roadmap | Phase 2 (weeks) — High-contrast accessibility themes |
| 428 | Screen Reader Compatibility | 🗺 Roadmap | Phase 2 (weeks) — Screen reader names/roles |
| 429 | Complete Keyboard Navigation | 🔶 Partial | Phase 3 (months) — Keyboard correction navigation exists; full app coverage remains |
| 430 | Customizable Keyboard Shortcuts | 🗺 Roadmap | Phase 3 (months) — Customizable keyboard shortcuts |
| 431 | Custom Workspace Layouts | 🗺 Roadmap | Phase 3 (months) — Custom workspace layouts |
| 432 | Touch-Friendly Interface Mode | 🗺 Roadmap | Phase 3 (months) — Touch-friendly interface mode |
| 433 | Guided First-Time Setup | 🗺 Roadmap | Phase 2 (weeks) — Guided first-time setup |
| 434 | Interactive Feature Tutorials | 🗺 Roadmap | Phase 3 (months) — Interactive in-app tutorials |
| 435 | Global Undo and Redo | 🔶 Partial | Phase 3 (months) — Editor undo/redo exists; app-wide undo remains |
| 436 | Distraction-Free Writing Mode | 🔶 Partial | Phase 2 (weeks) — Fullscreen mode exists; distraction-free editor remains |
| 437 | Reduced-Motion Mode | 🗺 Roadmap | Phase 2 (weeks) — Reduced-motion mode |
| 438 | Non-Color Status Indicators | 🗺 Roadmap | Phase 2 (weeks) — Non-color status indicators |
| 439 | Custom Editor Font Preferences | 🔶 Partial | Phase 3 (months) — Font size preferences exist; family selection remains |
| 440 | Multilingual GUI Localization | 🗺 Roadmap | Phase 3 (months) — Multilingual GUI localization |
| 441 | Offline User Manual | ✅ Shipped | Offline user manual in the Help menu |
| 442 | Contextual Help System | 🔶 Partial | Phase 3 (months) — Help documents exist; context-sensitive help remains |
| 443 | Actionable Error Messages | 🔶 Partial | Phase 3 (months) — Many actionable errors; systematic coverage remains |
| 444 | Diagnostic Report Export | 🔶 Partial | Phase 3 (months) — Logs exist; redacted diagnostic export added via production log redaction |
| 445 | Voice-Controlled Interface Commands | 🗺 Roadmap | Phase 4 (major effort) — Voice-controlled commands (local speech recognition) |
| 446 | Large Waveform Editing Mode | 🗺 Roadmap | Phase 3 (months) — Large waveform editing mode |
| 447 | Accessible Playback Controls | 🔶 Partial | Phase 3 (months) — Keyboard-friendly preview controls exist; audit remains |
| 448 | Left-Handed Workspace Presets | 🗺 Roadmap | Phase 3 (months) — Left-handed workspace presets |
| 449 | Customizable Toolbar | 🗺 Roadmap | Phase 3 (months) — Customizable toolbar |
| 450 | Split-Screen Editing Mode | 🗺 Roadmap | Phase 3 (months) — Split-screen editing mode |

### Features 451–475 — Audiobook Exporting, Formats, and Publishing

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 451 | Comprehensive Audio Format Export | ✅ Shipped |  |
| 452 | M4B Audiobook Creation | ✅ Shipped |  |
| 453 | Embedded Chapter Artwork | 🗺 Roadmap | Phase 2 (weeks) — Embedded per-chapter artwork in M4B |
| 454 | Advanced Audio Metadata Editor | 🔶 Partial | Phase 3 (months) — Manifest metadata exists; full metadata editor remains |
| 455 | ID3 Tag Editor | 🗺 Roadmap | Phase 2 (weeks) — ID3 tag editor |
| 456 | Embedded Cover Art | 🗺 Roadmap | Phase 2 (weeks) — Embedded cover art in audio files |
| 457 | RSS Audiobook Feed Generator | ✅ Shipped |  |
| 458 | Podcast Episode Export | ✅ Shipped |  |
| 459 | Audiobook Distribution Metadata Export | 🔶 Partial | Phase 3 (months) — RSS/M4B metadata; platform metadata export remains |
| 460 | EPUB Media Overlay Export | 🗺 Roadmap | Phase 3 (months) — EPUB media overlay (SMIL) export |
| 461 | DAISY-Compatible Production Workflow | 🗺 Roadmap | Phase 4 (major effort) — DAISY talking-book production |
| 462 | WebVTT Subtitle Export | ✅ Shipped |  |
| 463 | SRT Subtitle Export | ✅ Shipped |  |
| 464 | ASS Subtitle Export | 🆕 Added in 1.0.29 |  |
| 465 | Transcript PDF Export | 🆕 Added in 1.0.29 |  |
| 466 | Multilingual Subtitle Packaging | 🗺 Roadmap | Phase 3 (months) — Multilingual subtitle packaging |
| 467 | Audiobook Sample Generator | 🆕 Added in 1.0.29 |  |
| 468 | Platform-Specific Export Presets | 🔶 Partial | Phase 3 (months) — Format options exist; named platform presets remain |
| 469 | Export Compliance Checker | 🗺 Roadmap | Phase 2 (weeks) — Pre-publication compliance checker |
| 470 | File Integrity Manifests | ✅ Shipped |  |
| 471 | Release Notes Generator | 🆕 Added in 1.0.29 |  |
| 472 | Automated Attribution Document | 🆕 Added in 1.0.29 |  |
| 473 | Custom Export Naming Rules | 🆕 Added in 1.0.29 |  |
| 474 | Project Distribution Archive | ✅ Shipped |  |
| 475 | Optional Cloud Upload Integration | 🗺 Roadmap | Phase 4 (major effort) — Cloud upload integration (user-authorized) |

### Features 476–500 — Advanced Software Engineering and Build Infrastructure

| # | Feature | Status | Phase / note |
|---|---|---|---|
| 476 | Universal Dependency Manager | ✅ Shipped |  |
| 477 | CPU-Optimized Dependency Selection | ✅ Shipped |  |
| 478 | Offline Dependency Validation | ✅ Shipped |  |
| 479 | Explicit Installation Consent System | ✅ Shipped |  |
| 480 | Digital Signature Verification | 🔶 Partial | Phase 3 (months) — SHA-256 verification; publisher signature verification remains |
| 481 | Reproducible Build System | ✅ Shipped |  |
| 482 | Software Bill of Materials Generator | ✅ Shipped |  |
| 483 | Multilingual Regression Test Corpus | 🔶 Partial | Phase 3 (months) — Script regression tests exist; full corpus remains |
| 484 | Reference Speech Quality Tests | 🗺 Roadmap | Phase 3 (months) — Reference speech quality tests |
| 485 | Automatic Installation Repair | ✅ Shipped |  |
| 486 | Software Update Rollback | 🗺 Roadmap | Phase 3 (months) — Software update rollback |
| 487 | Diagnostic Support Bundle | 🔶 Partial | Phase 3 (months) — Build/status logs exist; support bundle packaging remains |
| 488 | Plugin Signing and Verification | 🗺 Roadmap | Phase 4 (major effort) — Plugin signing and verification |
| 489 | Extension Sandboxing | 🗺 Roadmap | Phase 4 (major effort) — Extension sandboxing |
| 490 | Granular Application Permissions | 🔶 Partial | Phase 3 (months) — Engine network isolation exists; full permission system remains |
| 491 | Encrypted Project Backups | 🗺 Roadmap | Phase 3 (months) — Encrypted project backups |
| 492 | Private Information Redaction | 🆕 Added in 1.0.29 | Production log field redaction for shared diagnostics |
| 493 | Dependency License Auditing | ✅ Shipped |  |
| 494 | Automated Accessibility Testing | 🗺 Roadmap | Phase 3 (months) — Automated accessibility testing |
| 495 | Integrated Software Test Runner | 🔶 Partial | Phase 3 (months) — unittest suite exists; in-app test runner remains |
| 496 | Hardware Benchmark Profiles | 🗺 Roadmap | Phase 3 (months) — Hardware benchmark profiles |
| 497 | Audio Regression Testing | 🗺 Roadmap | Phase 3 (months) — Audio regression testing |
| 498 | Cross-Platform Continuous Integration | ✅ Shipped |  |
| 499 | Project Format Migration System | 🔶 Partial | Phase 2 (weeks) — Project format version checks exist; migration tooling remains |
| 500 | Integrated Developer Documentation Center | 🔶 Partial | Phase 3 (months) — README/notices exist; integrated developer documentation center remains |

## Delivery roadmap for the remaining features

Phases are ordered by value-per-effort and dependency order. Estimates assume one
experienced developer working on this codebase; hardware-dependent items assume access
to the relevant devices.

### Phase 2 — High-value, low-dependency (≈4–8 weeks)

Clipboard import, footnote extraction, searchable-PDF layers, selective-region OCR,
region/TSV word alignment, grammar-checker integration, GUI chapter navigator,
voice favorites/tags/collection presets, side-by-side voice comparison, voice pack
import/export, duplicate voice detection, word-emphasis editor, silence trimming,
de-esser and parametric EQ (FFmpeg filters), missing-segment detection, crash-resistant
render resumption, engine benchmarking, watchdog, disk-space monitoring, Ken Burns
effect, title cards, manual subtitle timing editor, notebook line templates, chapter
illustration manager, alt-text for illustrations, watermark manager, high-contrast
themes, screen-reader labels, reduced-motion mode, first-time setup wizard, embedded
chapter artwork, ID3 editor, embedded cover art, export compliance checker, project
format migration tooling, homograph disambiguation rules.

### Phase 3 — Substantial subsystems (≈3–9 months)

Multi-tab projects, project activity history, read-only mode, missing-file recovery,
watched folders, drag-and-drop import, import presets, batch formatting, table OCR,
OCR engine comparison, formatting-aware OCR, tracked changes, protected regions,
non-destructive transform stack, synchronized read-aloud editing, relationship graph,
indirect-speech and internal-monologue classification, attribution timeline, character
merge/split tools, local TTS server mode, streaming synthesis, paragraph-level engine
selection, resource governor, resumable downloads, offline preview library, model
version locking, voice quality evaluation, profile inheritance, alternative takes,
backup voices, scene-specific performance, SSML compatibility layer, prosody curves,
pause variation, chapter pacing curves, emphasis suggestions, transliteration and
romanization management, per-language number/date/currency narration beyond English,
waveform editor, multitrack timeline editor, room tone, click/pop detection,
spectrogram, sidechain compression, automation curves, sound design templates,
environmental presets, stereo panning, convolution reverb, sound palettes, cinematic
transitions, music edit markers, stem export, reference mixes, render queue with
priorities, scheduled rendering, content-hash caching, selective regeneration,
low-memory mode, pipeline templates, video template library, animation easing, caption
collision detection, safe zones, waveform visualizer, progress visualization, cover
designer with layout grid and templates, theme packs, parallax, branding presets,
title sequences, smart focus, palette manager, music visualizers, UI localization,
workspace layouts, touch mode, tutorials, global undo, custom shortcuts, toolbar,
left-handed presets, split-screen editing, correction animation, EPUB media overlays,
multilingual subtitle packaging, platform export presets, cloud upload integration,
encrypted backups, update rollback, support bundles, reference speech tests, audio
regression testing, hardware benchmark profiles, accessibility test automation,
in-app test runner, developer documentation center, distraction-free mode, large
waveform mode, battery/thermal awareness.

### Phase 4 — Major or research-grade efforts (≈6+ months each)

Mathematical formula detection, historical typography OCR, marginalia recognition,
contextual word-choice detection (language models), voice format conversion, editable
prosody curves, breathing-sound synthesis, synthesis artifact detection, energy/thermal
management, handwriting correction animation, AI image generation integration, manga
panel navigation, voice-controlled interface, DAISY production tooling, plugin signing
and extension sandboxing. These need dedicated research, per-script or per-locale data,
or hardware/security infrastructure beyond ordinary application development.

### Items intentionally scoped by hardware and third parties

Universal GPU acceleration (feature preamble and #156) is implemented per-engine —
Piper CUDA today — because no single API drives every GPU vendor; each engine surfaces
its own acceleration where the upstream runtime supports it. Cloud upload (#475) and
AI image generation (#408) stay user-authorized integrations, never bundled services.
