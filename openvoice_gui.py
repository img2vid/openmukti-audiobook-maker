import os
import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    os.environ['PATH'] = str(Path(sys.executable).resolve().parent) + os.pathsep + os.environ.get('PATH', '')

# Preload native text shaping before any GUI/video imports initialize Pillow.
from openvoice.text_layout import _configure_windows_text_libraries
_configure_windows_text_libraries()

from openvoice.gui import main

if __name__ == '__main__':
    if '--portable-check' in sys.argv[1:]:
        from openvoice.portable import main as verify_portable
        raise SystemExit(verify_portable(gui=True))
    raise SystemExit(main())
