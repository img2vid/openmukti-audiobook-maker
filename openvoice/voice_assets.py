"""Local model inventories, duration-limited auditions, content locks and portable packs."""
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from .security_tools import file_digest, staged_file

WEIGHTS={'.onnx','.safetensors','.pth','.pt','.tflite','.bin','.npz','.ckpt','.gguf','.mlmodel','.ort'}
PACK_LIMIT=24*1024**3


def scan(root):
    root=Path(root).resolve(strict=True)
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root):
            yield path


def inventory(root,weights_only=False):
    base=Path(root).resolve(strict=True)
    files=[]
    for p in scan(base):
        if weights_only and p.suffix.lower() not in WEIGHTS:
            continue
        files.append({'path':p.relative_to(base).as_posix(),'size':p.stat().st_size,'sha256':file_digest(p).hex()})
    return files


def check_lock(root,entries):
    base=Path(root).resolve(strict=True)
    errors=[]
    for row in entries:
        p=(base/row['path']).resolve()
        if not p.is_relative_to(base):
            raise ValueError('Invalid path in model lock')
        if not p.is_file():
            errors.append({'path':row['path'],'error':'missing'})
            continue
        if p.stat().st_size!=row['size'] or file_digest(p).hex()!=row['sha256']:
            errors.append({'path':row['path'],'error':'modified'})
    return errors


def pack(root,destination):
    root=Path(root).resolve(strict=True)
    if Path(destination).resolve().is_relative_to(root):
        raise ValueError('Save voice pack outside its source folder')
    entries=inventory(root)
    if not entries or len(entries)>30000 or sum(r['size'] for r in entries)>PACK_LIMIT:
        raise ValueError('Voice pack is empty or exceeds the size limit')
    with staged_file(destination) as tmp, zipfile.ZipFile(tmp,'w',allowZip64=True) as z:
        z.writestr('voices.json',json.dumps({'format':'openmukti-asset-pack','files':entries}),compress_type=zipfile.ZIP_DEFLATED)
        for row in entries:
            z.write(root/row['path'],'models/'+row['path'])
    return Path(destination)


def unpack(source,destination):
    root=Path(destination).resolve()
    root.parent.mkdir(parents=True,exist_ok=True)
    if root.exists():
        raise ValueError('Choose a new folder for the extracted voice pack')
    with tempfile.TemporaryDirectory(dir=root.parent) as tmp, zipfile.ZipFile(source) as z:
        stage=Path(tmp)/'payload'
        stage.mkdir()
        infos=z.infolist()
        if len(infos)>30001 or sum(i.file_size for i in infos)>PACK_LIMIT or z.getinfo('voices.json').file_size>16*1024**2:
            raise ValueError('Voice pack exceeds limits')
        manifest=json.loads(z.read('voices.json'))
        if manifest.get('format')!='openmukti-asset-pack':
            raise ValueError('Unsupported model pack')
        rows=manifest['files']
        if len(rows)+1!=len(infos) or len({i.filename.casefold() for i in infos})!=len(infos):
            raise ValueError('Conflicting voice pack entries')
        for row in rows:
            name=row['path']
            parts=PurePosixPath(name).parts
            if any(v in ('','.','..','/') or re.search(r'[\\:\x00-\x1f]',v) or v.rstrip(' .')!=v or
                   v.split('.')[0].upper() in ('CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))) for v in parts):
                raise ValueError('Unsafe model pack path')
            target=stage.joinpath(*parts)
            if not target.resolve().is_relative_to(stage):
                raise ValueError('Unsafe model pack path')
            ent=z.getinfo('models/'+name)
            if ent.file_size!=row['size'] or (ent.external_attr>>16)&0o170000==0o120000:
                raise ValueError('Invalid model entry')
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(ent) as src,target.open('xb') as dst:
                shutil.copyfileobj(src,dst,1024**2)
            if file_digest(target).hex()!=row['sha256']:
                raise ValueError('Model checksum mismatch: '+name)
        os.rename(stage,root)
    return root


def duplicate_files(root):
    by_size={}
    for p in scan(root):
        if p.suffix.lower() in WEIGHTS:
            by_size.setdefault(p.stat().st_size,[]).append(p)
    result=[]
    for group in by_size.values():
        if len(group)<2:
            continue
        by_digest={}
        for p in group:
            by_digest.setdefault(file_digest(p).hex(),[]).append(str(p))
        result.extend(paths for paths in by_digest.values() if len(paths)>1)
    return result


def convert_model(source,output):
    if Path(source).suffix.lower()!='.onnx' or Path(output).suffix.lower()!='.ort':
        raise ValueError('Supported conversion is an ONNX graph to ONNX Runtime format (.ort)')
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError('Install onnxruntime to convert an ONNX graph') from exc
    with staged_file(output) as tmp:
        op=ort.SessionOptions()
        op.optimized_model_filepath=str(tmp)
        op.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        op.add_session_config_entry('session.save_model_format','ORT')
        ort.InferenceSession(str(source),sess_options=op,providers=['CPUExecutionProvider'])
        ort.InferenceSession(str(tmp),providers=['CPUExecutionProvider'])
    return Path(output)


def voice_records():
    from .piper_models import discover_voices
    from .voice_catalog import cached_catalog
    from .neural_models import marker_path
    from .neural_runtime import cache_home
    rows=[]
    catalog={v.key:v for v in cached_catalog()}
    for voice in discover_voices():
        info=catalog.get(voice.name)
        rows.append({'id':'piper/'+voice.name,'engine':'piper','voice':voice.name,
                     'language':info.language if info else voice.name.split('-')[0].replace('_','-'),
                     'accent':info.region if info else '', 'file':str(voice.model)})
    base=cache_home()/'approved-models'
    if base.is_dir():
        for p in sorted(base.glob('*/*.json')):
            try:
                row=json.loads(p.read_text(encoding='utf-8'))
            except (ValueError,OSError):
                continue
            if not all(isinstance(row.get(k),str) for k in ('engine','voice','model')):
                continue
            rows.append(dict(row,id='/'.join([row['engine'],row['model'],row['voice']]),file=str(p)))
    return rows


def registry_file():
    from .neural_runtime import cache_home
    return cache_home().parent/'cast-library.sqlite3'


def registry(action,name='',value='',*,tag='',accent='',favorites=False):
    import sqlite3
    from contextlib import closing
    db=registry_file()
    db.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(db,timeout=20)) as conn,conn:
        conn.execute('CREATE TABLE IF NOT EXISTS attributes (id TEXT PRIMARY KEY, properties TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS collections (name TEXT PRIMARY KEY, members TEXT)')
        if action=='collection':
            members=json.loads(value)
            if not name or not isinstance(members,list) or not all(isinstance(s,str) for s in members):
                raise ValueError('Supply a named JSON list of voice IDs')
            conn.execute('INSERT OR REPLACE INTO collections VALUES (?,?)',(name,json.dumps(members)))
            return members
        if action=='collections':
            return {k:json.loads(v) for k,v in conn.execute('SELECT name,members FROM collections')}
        attrs={k:json.loads(v) for k,v in conn.execute('SELECT id,properties FROM attributes')}
        if action=='set':
            fields=json.loads(value)
            if not name or not isinstance(fields,dict):
                raise ValueError('Provide a voice ID and metadata')
            if set(fields)-{'license','license_url','permitted_uses','language','accent','favorite','tags','notes'}:
                raise ValueError('Unsupported voice metadata field')
            if 'tags' in fields and (not isinstance(fields['tags'],list) or not all(isinstance(s,str) for s in fields['tags'])):
                raise ValueError('Tags must be a list of words')
            if 'favorite' in fields and type(fields['favorite'])!=bool:
                raise ValueError('Favorite must be true or false')
            row={**attrs.get(name,{}),**fields}
            conn.execute('INSERT OR REPLACE INTO attributes VALUES (?,?)',(name,json.dumps(row)))
            return row
        rows=voice_records()
        ids={r['id'] for r in rows}
        rows.extend({'id':k,'engine':k.split('/')[0],'voice':k.rsplit('/',1)[-1]} for k in attrs if k not in ids)
        result=[]
        for row in rows:
            row.update(attrs.get(row['id'],{}))
            row.setdefault('license','Unknown')
            if tag and tag.casefold() not in {s.casefold() for s in row.get('tags',[])}:
                continue
            if accent and accent.casefold() not in str(row.get('accent','')).casefold():
                continue
            if favorites and not row.get('favorite'):
                continue
            result.append(row)
        return result


def repair_from_lock(lock,approved_folder):
    """Restore damaged registered model files from a matching approved local backup."""
    from .security_tools import staged_file
    lock=Path(lock).resolve(strict=True)
    spec=json.loads(lock.read_text(encoding='utf-8'))
    root=(lock.parent/spec['root']).resolve(strict=True)
    trusted=Path(approved_folder).resolve(strict=True)
    changes=check_lock(root,spec['files'])
    rows={r['path']:r for r in spec['files']}
    replacements=[]
    for issue in changes:
        rel=issue['path']
        r=rows[rel]
        candidate=(trusted/rel).resolve(strict=True)
        if not candidate.is_relative_to(trusted) or file_digest(candidate).hex()!=r['sha256']:
            raise ValueError('Approved folder lacks the locked version of '+rel)
        replacements.append((candidate,root/rel,r['sha256']))
    for candidate,target,expected in replacements:
        with staged_file(target) as tmp:
            shutil.copyfile(candidate,tmp)
            if file_digest(tmp).hex()!=expected:
                raise ValueError('Backup file changed during repair')
    return changes
