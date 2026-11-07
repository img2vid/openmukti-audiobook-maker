# Openmukti 1.2.0 — Desktop authoring update

This update replaces the raw structured-data editors in routine desktop workflows and adds visual access to more production tools. Existing engines, rendering backends, projects, command-line entry points and build scripts are retained.

## Authoring and navigation

- Searchable task hub containing 47 tools in five categories.
- Tool descriptions, Enter-to-open, and shortcuts to reopen the hub.
- Responsive stacked descriptions on smaller windows.
- Recent projects and documents, including missing-file status.
- A production checklist and manuscript duration summary.
- Single project creation form with title, author, manuscript, template and save location.
- Double-click application and package-builder launchers.
- A new desktop user guide, with the prior technical README preserved separately.
- Empty initial manuscript, keeping startup instructions out of generated speech.

## Forms and tables

- Typed fields replace the previous raw-data settings editor across artwork, sound, captions, rules, subtitles and other callers.
- Checkboxes, dropdowns, numeric controls, file/folder browsers and color pickers.
- Coordinate controls for positions and crops, including fractional values.
- Automatic or manual image focal-point controls.
- Nested settings drafts with Apply, Cancel and Reset.
- Ordered list and named-dictionary editors with add, edit, duplicate, delete and search.
- Move controls preserve the full list order even while a filter is active.
- Unknown existing fields survive edits.
- Duplicate dictionary names and invalid numerical values receive an explanation without closing the editor.
- Checks reject invalid crop geometry, reversed subtitle times, non-finite numbers, invalid automation curves and invalid fade durations.
- Inner form cancellation and parent cancellation preserve the original project data.

## Preferences and comfort

- Preference tabs for appearance, quick access, production, access and translation.
- Dropdowns for language, performance and audio format.
- Visual toolbar-list editing and shortcut recording with action selection.
- Folder browsing for allowed paths and reusable audio.
- Persistent CPU and audio defaults.
- A graphical initial setup form.
- Platform font selection and matching dark styles for new tables and forms.
- Isolated scroll-wheel routing between tabbed panels.
- Cleanup of deferred toolbar and application callbacks on window closure.
- Manuscript save prompts before replacement and application closure.

## Narration and voices

- Scene-based narration planner with ordered speech, pause and sound passages.
- Per-passage character, emotion, pace, pitch and volume controls.
- Scene creation, renaming and removal; passage duplication and movement.
- Visual voice-profile and approved-local-sound editors.
- Import of supported older scores and speech markup into visual records.
- Narration-plan saving, checking, rendering and cancellation.
- Known character labels become profile assignments when ordinary manuscripts are imported into the planner.
- Timed legacy manuscripts remain intact and use the existing audio exporter.
- Cast-based voice auditions without a hand-authored cast data file.
- Main narrator selection and basic speech settings are retained in plans and auditions.
- Word substitution table with dictionary import, manuscript preview, saving and activation.

## Artwork, sound and publication

- Comic panel selection by drawing crop rectangles directly over a page image.
- Numbered panel order with move, remove and clear controls.
- Form-based layer timing, opacity, crop, easing, position and safe layout controls.
- Dropdown sound roles and expanded clip controls for panning, fades, loops, acoustic spaces, mute and credits.
- Editable automation-point and mix-marker tables.
- Live caption contrast and safe-area preview.
- Point-and-click audio processor covering all 18 existing processing operations.
- Ordered file selection for joining recordings.
- New graphical access to signal reports, recording comparison, crossfades, promotional samples, waveforms and spectrogram images.
- Graphical voice-model inventory, duplicate-file report, pack import and pack export.
- Language preparation with a preview and stale-manuscript protection before applying.
- Queue forms for single-voice document jobs or saved projects with complete casting.
- Document queue jobs preserve voice, speaker, prosody and pronunciation settings.
- Priority and local date/time fields replace command-argument editing in the queue.
- Friendly queue task names replace serialized command lists.
- Searchable hierarchical reports with readable detail, clipboard copy, and text/CSV export.

## Building and compatibility

- Graphical native-format picker using the existing host-specific builders.
- Package-profile selection, dependency-plan preview and optional automatic build dependency setup.
- Visible build output, saved logs, output-folder shortcut and stop control.
- Windows repair/resume option in the graphical builder.
- Version metadata updated to 1.2.0.
- No new mandatory third-party runtime package is added by the form or workflow layer.

The narration planner produces sequential performances. Existing overlapping sound-cue scripts continue through the established audio-export workflow. Optional engines, media codecs, OCR and platform-native packages remain subject to their existing runtime requirements.
