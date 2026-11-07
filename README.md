# Openmukti Audiobook Maker 1.2.0

A desktop workspace for turning manuscripts into audiobooks, character narration, artwork and video.

## Start here

Open **Openmukti.pyw** to launch the application. Choose **Start creating** for a searchable list of 47 tools. You can also reopen that window from the menu or with **Ctrl+K**.

This ZIP contains the updated source application. Running the source requires Python 3.10 or newer, Tk, Pillow and the components used by your chosen features. A packaged application can include its own Python and media tools. To create native packages on your computer, open **Build-Application.pyw**. Select a package, choose **Check requirements**, then **Build selected packages**. The builder uses the existing host-native build scripts and displays their progress and results in a window.

On Linux, **Launch-Openmukti.sh** opens the source application. On macOS, **Openmukti.command** does the same when Python and Tk are installed. File managers may ask you to allow executable launchers.

## A first audiobook

1. Choose **Start creating → New audiobook project**. Enter the title, optionally choose a manuscript or template, and select where to save it.
2. Choose a speech engine and voice. Download neural voices through the voice manager before using them.
3. Use **Character voices** to assign speakers. Use **Word substitutions** to teach the narrator names and unusual words.
4. Preview a short passage with **Speak** or **Read along**.
5. Choose **Export audio**, **Combine chapters**, or **Make audiobook video**.
6. Run **Publishing check** on the finished export folder.

## What changed in this release

| Area | Graphical workflow |
| --- | --- |
| Finding tools | Searchable task hub, categories, recent files and production checklist |
| Preferences | Tabs for appearance, quick access, production, access and translation |
| Editing settings | Number controls, checkboxes, dropdowns, file pickers and color choosers |
| Lists and rules | Add, edit, duplicate, remove, reorder and search entries in tables |
| Narration | Scenes, character voices, emotions, speed, pitch, pauses and approved sounds |
| Voice auditions | Generate listening samples from the current cast and a typed sample passage |
| Word substitutions | Editable dictionary table, import, preview, save and enable |
| Artwork | Position and crop fields, opacity, camera easing, focal point and safe area controls |
| Comic panels | Draw crop rectangles over an image and reorder them visually |
| Sound | Clip volume, panning, duration, fades, loops, acoustic spaces and automation points |
| Captions | Timing forms and a live contrast / safe area preview |
| Production queue | Document or saved-project jobs, voice settings, priority and local start time |
| Reports | Searchable sections, readable results, clipboard copy and text / CSV export |
| Additional tools | Signal reports, recording comparison, crossfade, promotional samples and voice packs |
| Building | Graphical native package selection, requirements check, logs and stop controls |

Routine settings no longer require editing structured data. Existing project files and legacy data imports remain supported. The optional command-line interface is retained for existing integrations.

## Guides

- [User guide](openvoice/resources/GUI_GUIDE.txt): step-by-step desktop workflows.
- [Changes in 1.2.0](CHANGES_1.2.0.md): additions, fixes and compatibility details.
- [Verification](VERIFICATION_1.2.0.md): checks run and their limits.
- [Developer reference](DEVELOPER_REFERENCE.md): the earlier technical manual and command-line documentation.
- [Third-party notices](THIRD_PARTY_NOTICES.md): dependency and voice licensing information.

## Availability

The desktop interface uses Tk. Individual engines, GPU acceleration, OCR languages, media codecs and packaging tools depend on the operating system and installed components. GPU fallback and the existing voice download controls are retained. Optional voice models are not included in this source ZIP.

The narration planner creates sequential performances. Existing manuscripts with overlapping or explicitly timed sound cues continue through the normal audio export; opening the separate planner does not rewrite those manuscripts. Older narration scores and supported speech-markup files can be opened from the planner.

Created by **Aishik Dutta**. Project license: MIT. Third-party engines, model weights and voices retain their own licenses.
