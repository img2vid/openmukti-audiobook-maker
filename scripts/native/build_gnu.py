"""Build Openmukti on a native gnu host."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.platform_support import system
    from build_detect_os import main
    if system() != 'gnu':
        raise SystemExit('Run this script on gnu, or use build_all_platforms.py for remote native builds.')
    raise SystemExit(main())
