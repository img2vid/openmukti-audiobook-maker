# Verification — Openmukti 1.2.0

Validation was performed on Linux with Python 3.12 and Tk 9.0. A virtual display was used to exercise the actual desktop widgets.

| Check | Result |
| --- | --- |
| Complete automated suite | 324 tests run: 323 passed, 1 skipped, no failures |
| New authoring tests | 25 tests added for forms, navigation, queues, plans and rendering |
| Python syntax | Application modules, graphical builder and launchers compiled successfully |
| Complete desktop | Started successfully; project creation, preferences, caption settings, narration editing and shutdown exercised |
| Compact task hub | Checked at 480 × 540 pixels with stacked descriptions and scrolling |
| Compact preference form | Checked at 460 × 500 pixels; Apply remains visible; section navigation works |
| Keyboard shortcut | Ctrl+K opens the hub without deleting manuscript text |
| Form safety | Nested cancellation, reset, invalid input, preserved unknown fields and duplicate-name checks passed |
| Lists and mappings | Search, edit, reorder, duplicate, remove and apply checks passed |
| Comic panels | Screen rectangles converted correctly to normalized crop coordinates |
| Narration plan | Scene editing, cast retention, pause insertion, save and load checks passed |
| Narration rendering | A real Flite narration plus a pause rendered successfully through the performance renderer |
| Real audio measurement | 3.3516 seconds; peak approximately 0.6165 of full scale; 0 clipped samples |
| Graphical builder | Window, package choices and principal controls launched successfully; build-argument translation tested |
| Shell launchers | Syntax checked; executable permissions set |

The test suite includes platform/build simulations. Successful tests do not establish that every optional engine, graphics card, operating system or native package format works on every machine. Native Windows and macOS packages were not built or executed here. Neural model weights were not downloaded for this change.

This delivery is the updated source application. Existing host-native builders remain available through the new graphical builder. Optional voice, OCR, translation and media tools retain their existing installation requirements.

The source archive excludes test-generated build logs, bytecode, temporary screenshots, test audio and local validation tools. The original source files are retained, with the earlier README preserved as DEVELOPER_REFERENCE.md. Routine settings and reports use graphical controls; legacy data imports and the optional command-line interface remain available for compatibility.
