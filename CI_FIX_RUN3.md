# GitHub Actions run #2 cross-platform fixes (November 7, 2026)

This archive is a full Openmukti Audiobook Maker project, not a patch-only archive.

Changes based on the **full GitHub Actions logs** of run `42350458065`:

- `tests/test_neural_engines.py`: correctly mock the `scipy` and `scipy.io` parent packages when unit-testing the Pocket TTS worker. Production Pocket TTS still installs SciPy in its isolated environment; no speech engine is disabled.
- `openvoice/video.py`: validate absent cover images before checking whether FFmpeg is installed, keeping useful validation errors visible on minimal runners.
- `scripts/build_unix.py`: use `platform.uname()` instead of Unix-only `os.uname()` so cross-platform tests work on Windows.
- `tests/test_animated_video.py`, `tests/test_stroke_studio.py`, `tests/test_v130_features.py`: specify UTF-8 for non-ASCII test input, avoiding Windows CP1252 failures.
- `tests/test_studio_workflows.py`: explicitly close SQLite database connections before temporary folder cleanup, fixing Windows file locks.
- `openvoice/import_studio.py`: preserve caller-supplied lexical directory paths in FolderInbox (e.g. macOS `/var` versus `/private/var`, Windows long versus 8.3 paths).

- `.github/workflows/build.yml`: ensure Python defaults to UTF-8 for multilingual text handling on all CI runners.

The previous fixes restoring `openvoice/engines` and `openvoice/resources` are retained.

Run checks at the project root:

```bash
python scripts/verify_repository_assets.py
python -m compileall -q openvoice scripts packaging build.py build_select.py build_detect_os.py build_all_platforms.py
python -m unittest discover -s tests -v
```

The CI matrix remains enabled for Linux, Windows, and macOS and the full test suite is not bypassed.
The local environment cannot reproduce all OS-specific packaging stages; check the new GitHub Actions run after committing these files.
