"""Collect Pillow's optional native wheel libraries without changing architectures.

Windows wheels may keep dynamically loaded text-layout DLLs in a sibling
pillow.libs directory, outside --collect-all PIL. Preserve that directory and
its load-order files so its own wheel loader can find the matching libraries.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def pillow_options(pil_directory: Path | None=None) -> list[str]:
    if pil_directory is None:
        import PIL
        pil_directory=Path(PIL.__file__).resolve().parent
    pil_directory=Path(pil_directory)
    options=[]
    visited=set()
    for folder in (pil_directory.parent/'pillow.libs',pil_directory.parent/'Pillow.libs',
                   pil_directory.parent/'PIL.libs',pil_directory/'.libs'):
        if not folder.is_dir() or folder.resolve() in visited:continue
        visited.add(folder.resolve())
        for path in sorted(folder.rglob('*')):
            if not path.is_file():continue
            relative=path.parent.relative_to(pil_directory.parent).as_posix()
            binary=path.suffix.casefold() in {'.dll','.dylib','.so'} or '.so.' in path.name
            options.extend(['--add-binary' if binary else '--add-data',str(path)+os.pathsep+relative])
    return options


if __name__=='__main__':
    print(json.dumps(pillow_options()))
