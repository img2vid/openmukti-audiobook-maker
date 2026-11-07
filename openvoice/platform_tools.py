"""Managed installation slots, format checks, optional local accelerators and tutorials."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .security_tools import file_digest,staged_file
from .voice_library import _atomic_json


def deployment(folder,action,value=''):
    """Manage explicit executable copies. A failed install never changes the active slot."""
    root=Path(folder).expanduser().resolve()
    root.mkdir(parents=True,exist_ok=True)
    state_path=root/'versions.json'
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'slots':{},'active':'','previous':''}
    if action=='install':
        src=Path(value).expanduser().resolve(strict=True)
        if not src.is_file() or src.suffix.lower() not in ('.exe','.appimage','') or (os.name!='nt' and not os.access(src,os.X_OK)):
            raise ValueError('Select a single portable application executable')
        key=file_digest(src).hex()
        slot=root/key
        slot.mkdir(exist_ok=True)
        target=slot/src.name
        with staged_file(target) as tmp:
            shutil.copy2(src,tmp)
            if file_digest(tmp).hex()!=key:
                raise ValueError('Application changed during copying')
        state['slots'][key]=src.name
        if state['active']!=key:
            state.update(previous=state['active'],active=key)
        _atomic_json(state_path,state)
    elif action=='rollback':
        key=state['previous']
        if not key or key not in state['slots']:
            raise ValueError('Install a second version before rollback')
        if file_digest(root/key/state['slots'][key]).hex()!=key:
            raise ValueError('Previous application checksum failed')
        state.update(active=key,previous=state['active'])
        _atomic_json(state_path,state)
    elif action=='launch':
        key=state['active']
        if key not in state['slots']:
            raise ValueError('No active portable version')
        file=root/key/state['slots'][key]
        if file_digest(file).hex()!=key:
            raise ValueError('Active application checksum failed')
        subprocess.Popen([str(file)],cwd=file.parent)
    return state


def gpu_wheels(engine,folder,files,install=False):
    """Install only explicitly selected wheels from a user-supplied offline wheelhouse."""
    from .desktop_prefs import authorized
    from .neural_runtime import python_path
    if engine not in ('kokoro','kitten','pocket','coqui','application'):
        raise ValueError('Unknown runtime')
    if engine=='application' and getattr(sys,'frozen',False):
        raise ValueError('For a frozen app, select a neural worker environment or install GPU wheels in a source installation')
    py=Path(sys.executable) if engine=='application' else python_path(engine)
    if not py.is_file():
        raise ValueError('Install the selected engine runtime first')
    directory=Path(folder).resolve(strict=True)
    authorized('folders',directory)
    wheels=[]
    for name in files:
        p=(directory/name).resolve(strict=True)
        if p.parent!=directory or p.suffix.lower()!='.whl':
            raise ValueError('Select wheel files from the chosen directory')
        wheels.append({'file':str(p),'sha256':file_digest(p).hex()})
    if not wheels:
        raise ValueError('Select at least one accelerator wheel')
    cmd=[str(py),'-m','pip','install','--no-index','--find-links',str(directory),'--upgrade',*[r['file'] for r in wheels]]
    if install:
        authorized('external_tools')
        subprocess.run(cmd,check=True,stdin=subprocess.DEVNULL)
    return {'interpreter':str(py),'wheels':wheels,'installed':install}
