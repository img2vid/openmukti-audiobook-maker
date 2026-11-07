# GitHub Actions checks — run #4 fixes

## Issues found in GitHub Actions run #3 (2026-11-07)

- Windows failed `Caching.test_model_weights_change_key`: file checksum memoization keyed by metadata could return a stale SHA-256 if model weights changed within the same filesystem time tick. `openvoice/render_cache.py` now always hashes actual file content, once per render session via `ChunkStore`'s existing identity cache.
- macOS crashed in `VisualForms.test_reset_does_not_leave_wheel_callbacks_on_destroyed_canvas` with native Tk segmentation fault 11. `openvoice/windowing.py` now installs one mouse-wheel dispatcher per top-level window and removes destroyed scroll panels from a registry without modifying Tcl bindings in destruction callbacks. VisualForms tests use one Tk interpreter with per-test isolated Toplevel windows. Repeated form resets verify the registry and no stale canvases.

The earlier required engine and resource files, Windows UTF-8 handling and other run #2 fixes are unchanged.

## Validation

Run `python -m unittest discover -s tests -v`, followed by `python -m compileall -q openvoice scripts packaging build.py build_select.py build_detect_os.py build_all_platforms.py` and `python scripts/verify_repository_assets.py`. On a Linux machine with Xvfb, also run `xvfb-run -a python -m unittest discover -s tests -v` to exercise the Tkinter tests. Only GitHub's hosted macOS runner can confirm whether the platform-specific native Tk crash is fully resolved.

## Updating an existing GitHub checkout

This source update ZIP does not redistribute the 21 unchanged Noto font binaries already committed under `openvoice/resources/fonts/` in your GitHub repository. Those existing assets must remain in place. Extract this project over a checkout of `img2vid/openmukti-audiobook-maker`, preserving the `.github` directory and keeping existing files that are not in the ZIP. After copying, run `python scripts/verify_repository_assets.py` and commit the changed source. To create a fresh local workspace, clone the repository first, then overlay these source files.
