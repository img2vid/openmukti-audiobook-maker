"""Pillow text layout that works with both RAQM and BASIC FreeType fonts.

RAQM is optional in Pillow and its availability can differ between the build
interpreter and a frozen executable. Check the actual font as well as the
runtime; never send advanced layout keywords to a BASIC font.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_SEARCH_HANDLES = []
_DLL_PATHS_CONFIGURED = False


def _configure_windows_text_libraries():
    """Preload FriBiDi so Pillow's vendored libraqm can shape Indic/RTL text.

    The official Windows Pillow wheel loads libfribidi dynamically. Its RAQM
    flag may be false if the native DLL is absent *at import time*. Loading
    the DLL by absolute path before importing PIL._imagingft makes this work
    in both the build venv and PyInstaller's isolated one-file extraction.
    """
    global _DLL_PATHS_CONFIGURED
    if _DLL_PATHS_CONFIGURED or os.name != 'nt':
        return
    # Do not mark configured until probing paths; an interrupted first call
    # should not prevent a later check from trying again.
    roots = [Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))]
    roots.append(Path(__file__).resolve().parent)
    folders = []
    for root in roots:
        for relative in ('text_layout', 'pillow.libs', 'Pillow.libs', 'PIL.libs',
                         'PIL/.libs', 'PIL'):
            folder = root / relative
            if folder.is_dir():
                folders.append(folder)
    override = os.environ.get('OPENMUKTI_FRIBIDI_DLL', '').strip()
    # A custom DLL is optional and useful for LGPL library replacement.
    # Frozen verification launches with an empty environment to ensure the
    # embedded file really works by itself.
    dlls = ([Path(override)] if override else []) + [
        folder / name for folder in folders
        for name in ('libfribidi-0.dll', 'fribidi.dll', 'fribidi-0.dll')]
    if hasattr(os, 'add_dll_directory'):
        for folder in folders:
            try:
                _DLL_SEARCH_HANDLES.append(os.add_dll_directory(str(folder)))
            except OSError:
                pass
    # Do not silently ignore an existing but corrupt DLL. Verify on Windows
    # at build and standalone preflight; a failure should be visible.
    import ctypes
    for candidate in dlls:
        if not candidate.is_file():
            continue
        try:
            _DLL_SEARCH_HANDLES.append(ctypes.WinDLL(str(candidate.resolve())))
        except OSError as exc:
            if override and candidate == Path(override):
                raise RuntimeError(f'Could not load selected FriBiDi DLL: {candidate}: {exc}') from exc
            continue
        break
    _DLL_PATHS_CONFIGURED = True


def raqm_available() -> bool:
    try:
        _configure_windows_text_libraries()
        from PIL import features
        return bool(features.check_feature('raqm'))
    except (ImportError, AttributeError, ValueError, OSError):
        return False


def load_font(path, size, *, force_basic=False):
    _configure_windows_text_libraries()
    from PIL import ImageFont
    engine = (ImageFont.Layout.RAQM if not force_basic and raqm_available()
              else ImageFont.Layout.BASIC)
    return ImageFont.truetype(str(path), size, layout_engine=engine)


def layout_options(font, direction=None, *, language=None, features=None) -> dict:
    from PIL import ImageFont
    if (getattr(font, 'layout_engine', None) != ImageFont.Layout.RAQM
            or not raqm_available()):
        return {}
    options = {}
    if direction is not None:
        options['direction'] = direction
    if language is not None:
        options['language'] = language
    if features is not None:
        options['features'] = features
    return options


def _missing_raqm(exc: Exception) -> bool:
    message = str(exc).casefold()
    return 'libraqm' in message and ('not supported' in message or 'without' in message)


def text_length(font, text: str, direction='ltr') -> float:
    options = layout_options(font, direction)
    try:
        return font.getlength(text, **options)
    except (KeyError, ValueError) as exc:
        if not options or not _missing_raqm(exc):
            raise
        # A stale/partial native runtime can advertise RAQM, then reject its
        # keywords. Retry only this specific dependency error, not font errors.
        return font.getlength(text)


def draw_text(drawer, xy, text: str, font, fill, direction='ltr'):
    options = layout_options(font, direction)
    try:
        return drawer.text(xy, text, font=font, fill=fill, stroke_width=0, **options)
    except (KeyError, ValueError) as exc:
        if not options or not _missing_raqm(exc):
            raise
        return drawer.text(xy, text, font=font, fill=fill, stroke_width=0)


def layout_status() -> dict:
    available = raqm_available()
    return {
        'raqm': available,
        'engine': 'raqm' if available else 'basic',
        'complex_script_shaping': available,
        'detail': ('Advanced text shaping available' if available else
                   'Basic text rendering is available. Arabic/Indic shaping and '
                   'bidirectional layout require a RAQM-enabled Pillow runtime.'),
    }
