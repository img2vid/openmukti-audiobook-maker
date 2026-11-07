"""Repair archived resources by hash and compare-and-save project tab revisions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path

from .project_archive import (MAX_EXTRACTED_BYTES, MAX_FILES, MAX_MANIFEST_BYTES,
                             load_project, save_project)
from .security_tools import file_digest, staged_file


def recover(source,folder,output):
    """Recover only the exact bytes declared in the archive, even after renaming."""
    source=Path(source).resolve(strict=True)
    folder=Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Select a search folder')
    found=[]
    with zipfile.ZipFile(source) as z, staged_file(output) as stage:
        desc=z.getinfo('project.json')
        if desc.file_size>MAX_MANIFEST_BYTES:
            raise ValueError('Oversized project manifest')
        raw=z.read(desc)
        data=json.loads(raw)
        if data.get('format')!='openmukti-project' or data.get('version') not in (1,2):
            raise ValueError('Unsupported project archive')
        resources=data.get('resources',{})
        if not isinstance(resources,dict) or len(resources)>MAX_FILES:
            raise ValueError('Invalid resource library')
        if any(not re.fullmatch(r'assets/[a-f0-9]{20}/[^/\\]+',name) or not re.fullmatch(r'[a-f0-9]{64}',str(info.get('sha256','')))
               or type(info.get('size'))!=int or info['size']<0 for name,info in resources.items()):
            raise ValueError('Invalid resource entry')
        if sum(v['size'] for v in resources.values())>MAX_EXTRACTED_BYTES:
            raise ValueError('Project is too large')
        sizes={v['size'] for v in resources.values()}
        candidates=None
        with zipfile.ZipFile(stage,'w',zipfile.ZIP_DEFLATED,allowZip64=True) as out, tempfile.TemporaryDirectory() as room:
            out.writestr('project.json',raw)
            for name,info in resources.items():
                good=False
                temp=Path(room)/'asset'
                if name in z.namelist() and z.getinfo(name).file_size==info['size']:
                    try:
                        import shutil
                        with z.open(name) as src,temp.open('wb') as dst:
                            shutil.copyfileobj(src,dst,1024**2)
                        good=file_digest(temp).hex()==info['sha256']
                    except (OSError,zipfile.BadZipFile):
                        good=False
                if not good:
                    if candidates is None:
                        candidates={}
                        for p in folder.rglob('*'):
                            if p.is_file() and not p.is_symlink() and p.stat().st_size in sizes:
                                candidates.setdefault(p.stat().st_size,[]).append(p)
                    match=next((p for p in candidates.get(info['size'],[]) if file_digest(p).hex()==info['sha256']),None)
                    if match is None:
                        raise ValueError('Could not locate matching bytes for '+name)
                    temp=match
                    found.append({'asset':name,'recovered_from':str(match)})
                out.write(temp,name)
        with tempfile.TemporaryDirectory() as room:
            load_project(stage,room)
    return found


def migrate(source,destination):
    """Validate the source and preserve every asset name, byte and unknown metadata field."""
    from .project_archive import FORMAT_VERSION
    source=Path(source).resolve(strict=True)
    if source==Path(destination).resolve():
        raise ValueError('Choose a separate migrated project file')
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        load_project(source,tmp)
    with staged_file(destination) as stage, zipfile.ZipFile(source) as old, zipfile.ZipFile(stage,'w',allowZip64=True) as new:
        for entry in old.infolist():
            if entry.filename=='project.json':
                data=json.loads(old.read(entry))
                data['version']=FORMAT_VERSION
                new.writestr(entry,json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())
            else:
                with old.open(entry) as src,new.open(entry,'w',force_zip64=True) as dst:
                    shutil.copyfileobj(src,dst,1024**2)
    return Path(destination)
