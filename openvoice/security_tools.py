"""Authenticated backups, detached signatures and permission-limited text extensions."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tempfile
from contextlib import contextmanager
from pathlib import Path

MAGIC=b'OPENMUKTI-BACKUP\x01'
CHUNK=1<<20


@contextmanager
def staged_file(target):
    target=Path(target).expanduser().resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    fd,path=tempfile.mkstemp(prefix='.openmukti-',dir=target.parent,suffix=target.suffix)
    os.close(fd)
    try:
        yield Path(path)
        os.replace(path,target)
    finally:
        Path(path).unlink(missing_ok=True)


def crypto_modules():
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        from cryptography.exceptions import InvalidTag, InvalidSignature
    except ImportError as exc:
        raise RuntimeError('Install the security extra with python -m pip install ".[security]"') from exc
    return Cipher,algorithms,modes,ed25519,serialization,InvalidTag,InvalidSignature


def backup(source,destination,password,*,decrypt=False):
    Cipher,algorithms,modes,_,_,InvalidTag,_=crypto_modules()
    source=Path(source).expanduser().resolve(strict=True)
    if source==Path(destination).expanduser().resolve() or not password:
        raise ValueError('Choose a distinct destination and a nonempty passphrase')
    with source.open('rb') as src, staged_file(destination) as staged, staged.open('wb') as out:
        if decrypt:
            header=src.read(len(MAGIC)+28)
            if len(header)!=len(MAGIC)+28 or not header.startswith(MAGIC):
                raise ValueError('Unrecognized encrypted backup')
            remaining=source.stat().st_size-len(header)-16
            if remaining<0:
                raise ValueError('Incomplete encrypted backup')
            src.seek(-16,2)
            tag=src.read(16)
            src.seek(len(header))
        else:
            header=MAGIC+os.urandom(16)+os.urandom(12)
            out.write(header)
            remaining=source.stat().st_size
        key=hashlib.scrypt(password.encode('utf-8'),salt=header[-28:-12],n=2**15,r=8,p=1,
                           dklen=32,maxmem=96*1024**2)
        cipher=Cipher(algorithms.AES(key),modes.GCM(header[-12:],tag if decrypt else None))
        operation=cipher.decryptor() if decrypt else cipher.encryptor()
        operation.authenticate_additional_data(header)
        while remaining:
            block=src.read(min(CHUNK,remaining))
            if not block:
                raise ValueError('Source changed during backup')
            remaining-=len(block)
            out.write(operation.update(block))
        try:
            out.write(operation.finalize())
        except InvalidTag as exc:
            raise ValueError('Authentication failed. Check the passphrase and backup integrity') from exc
        if not decrypt:
            out.write(operation.tag)
    return Path(destination)


def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(CHUNK),b''):
            digest.update(block)
    return digest.digest()


def generate_key(private_path, public_path):
    _,_,_,keys,ser,_,_=crypto_modules()
    a,b=Path(private_path),Path(public_path)
    if a.resolve()==b.resolve() or a.exists() or b.exists():
        raise ValueError('Choose separate unused filenames for the private and public keys')
    private=keys.Ed25519PrivateKey.generate()
    with open(a,'xb',opener=lambda p,f:os.open(p,f,0o600)) as f:
        f.write(private.private_bytes(ser.Encoding.PEM,ser.PrivateFormat.PKCS8,ser.NoEncryption()))
    with b.open('xb') as f:
        f.write(private.public_key().public_bytes(ser.Encoding.PEM,ser.PublicFormat.SubjectPublicKeyInfo))


def signature(file,key_path,signature_path,*,verify=False):
    _,_,_,keys,ser,_,InvalidSignature=crypto_modules()
    key=Path(key_path).read_bytes()
    message=b'Openmukti SHA256 signature v1\0'+file_digest(file)
    if verify:
        public=ser.load_pem_public_key(key)
        if not isinstance(public,keys.Ed25519PublicKey):
            raise ValueError('An Ed25519 public key is required')
        try:
            public.verify(base64.b64decode(Path(signature_path).read_bytes().strip(),validate=True),message)
        except InvalidSignature as exc:
            raise ValueError('Signature does not match the file and trusted key') from exc
    else:
        if Path(signature_path).resolve() in (Path(key_path).resolve(),Path(file).resolve()):
            raise ValueError('Choose a separate signature file')
        private=ser.load_pem_private_key(key,password=None)
        if not isinstance(private,keys.Ed25519PrivateKey):
            raise ValueError('An Ed25519 private key is required')
        with staged_file(signature_path) as tmp:
            tmp.write_bytes(base64.b64encode(private.sign(message))+b'\n')
    return True


def run_extension(manifest,text,*,trusted_key,signature_file,permissions=()):
    """Declarative text plugins have no file, network, microphone or process primitives."""
    if Path(manifest).stat().st_size>1024*1024 or len(text)>16*1024**2:
        raise ValueError('Extension input exceeds size limit')
    # Verify and parse exactly the same bytes even if the source is concurrently replaced.
    raw=Path(manifest).read_bytes()
    _,_,_,keys,ser,_,InvalidSignature=crypto_modules()
    key=ser.load_pem_public_key(Path(trusted_key).read_bytes())
    if not isinstance(key,keys.Ed25519PublicKey):
        raise ValueError('An Ed25519 public key is required')
    try:
        key.verify(base64.b64decode(Path(signature_file).read_bytes().strip(),validate=True),
                   b'Openmukti SHA256 signature v1\0'+hashlib.sha256(raw).digest())
    except InvalidSignature as exc:
        raise ValueError('Extension signature verification failed') from exc
    data=json.loads(raw)
    ops=data.get('operations')
    if data.get('version')!=1 or not isinstance(ops,list) or not 1<=len(ops)<=64:
        raise ValueError('Unsupported extension manifest')
    allowed=set(permissions)
    for spec in ops:
        act=spec.get('action')
        if act not in ('replace','normalize','case','trim') or act not in allowed:
            raise ValueError('Extension operation denied: '+str(act))
        if act=='replace':
            old,new=spec.get('from'),spec.get('to')
            if not isinstance(old,str) or not old or not isinstance(new,str):
                raise ValueError('Invalid replacement')
            if len(text)+max(0,len(new)-len(old))*text.count(old)>16*1024**2:
                raise ValueError('Extension output would exceed size limit')
            text=text.replace(old,new)
        elif act=='normalize':
            import unicodedata
            text=unicodedata.normalize(spec.get('form','NFC'),text)
        elif act=='case':
            methods={'upper':str.upper,'lower':str.lower,'fold':str.casefold}
            if spec.get('mode') not in methods:
                raise ValueError('Unknown case transformation')
            text=methods[spec['mode']](text)
        else:
            text=text.strip()
        if len(text)>16*1024**2:
            raise ValueError('Extension output exceeds size limit')
    return text
