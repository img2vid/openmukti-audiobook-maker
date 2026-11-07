"""Enforce explicitly configured access rules at Python's application boundary.

Native programs are separate, trusted applications. The user can disable
their launch independently. The declarative extension runner has no OS APIs.
"""
from __future__ import annotations

import ipaddress
import os
import sys
import tempfile
import threading
from pathlib import Path

_installed=False
_state=None
_lock=threading.RLock()
_temp_paths=set()


def _real(value,dir_fd=None):
    if not isinstance(value,(str,bytes,os.PathLike)):
        return None
    p=Path(os.fsdecode(value)).expanduser()
    if not p.is_absolute() and isinstance(dir_fd,int) and dir_fd>=0:
        handle=Path('/proc/self/fd')/str(dir_fd)
        if not handle.is_symlink():
            raise PermissionError('Cannot resolve directory-relative access under the current folder policy')
        p=handle.resolve()/p
    return p.resolve(strict=False)


def _inside(p,roots):
    return any(p==r or r in p.parents for r in roots)


def _loopback(host):
    if host in ('localhost','::1',None):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_path(path,writing=False,dir_fd=None):
    state=_state
    if not state or not state['roots']:
        return
    real=_real(path,dir_fd)
    if real is None:
        return
    if _inside(real,state['roots']) or _inside(real,state['app_write']):
        return
    if not writing and _inside(real,state['app_read']):
        return
    with _lock:
        temporary=tuple(_temp_paths)
    if _inside(real,temporary):
        return
    raise PermissionError('Choose a folder allowed in Studio preferences: '+str(real))


def _audit(event,args):
    state=_state
    if not state:
        return
    if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn','os.startfile') and not state['external']:
        raise PermissionError('External tools are disabled in Studio preferences')
    if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','socket.gethostbyname') and not state['network']:
        address=args[0] if event.startswith(('socket.getaddrinfo','socket.gethostbyname')) else args[1]
        if isinstance(address,tuple):address=address[0]
        if not _loopback(address):
            raise PermissionError('Network access is disabled in Studio preferences')
    if not state['roots']:
        return
    if event in ('tempfile.mkdtemp','tempfile.mkstemp'):
        real=_real(args[0])
        if real is not None and state['temp'] in real.parents:
            with _lock:_temp_paths.add(real)
    elif event=='open':
        bits=args[2] if len(args)>2 and isinstance(args[2],int) else 0
        write=bool(bits & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
        _check_path(args[0],write)
    elif event in ('os.listdir','os.scandir'):
        _check_path(args[0] if args else '.')
    elif event in ('os.remove','os.rmdir'):
        _check_path(args[0],True,args[1] if len(args)>1 else None)
    elif event in ('os.mkdir','os.chmod'):
        _check_path(args[0],True,args[2] if len(args)>2 else None)
    elif event in ('os.rename','os.link'):
        _check_path(args[0],True,args[2] if len(args)>2 else None)
        _check_path(args[1],True,args[3] if len(args)>3 else None)
    elif event=='os.symlink':
        _check_path(args[1],True,args[2] if len(args)>2 else None)


def configure(prefs):
    global _state,_installed
    rules=prefs.get('permissions',{})
    if not isinstance(rules,dict):
        raise ValueError('Permissions must be an object')
    bindings=rules.get('folders',[])
    if not isinstance(bindings,list) or not all(isinstance(s,str) and s for s in bindings):
        raise ValueError('Allowed folders must be a list of paths')
    roots=tuple(Path(s).expanduser().resolve() for s in bindings)
    if not roots and rules.get('network',True) and rules.get('external_tools',True):
        _state=None
        return
    from .neural_runtime import cache_home
    from .piper_models import voice_directory
    from .desktop_prefs import path
    system_roots=[Path(sys.prefix)/'lib',Path(sys.base_prefix)/'lib',Path(sys.base_prefix)/'Lib',
                  Path(__file__).resolve().parent,Path(sys.executable).resolve().parent,
                  Path('/usr/share/fonts'),Path('/usr/share/fontconfig'),Path('/etc/fonts'),
                  Path('/System/Library/Fonts'),Path('/Library/Fonts')]
    if os.name=='nt':
        system_roots.extend([Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts',Path(sys.base_prefix)/'DLLs'])
    frozen=getattr(sys,'_MEIPASS',None)
    if frozen:system_roots.append(Path(frozen))
    system_roots.extend(Path(p) for p in sys.path if p and p.endswith(('.pyz','.zip','/site-packages','/dist-packages')))
    tmp=Path(tempfile.gettempdir()).resolve()
    _state={'roots':roots,'app_write':tuple(p.resolve() for p in (cache_home(),voice_directory(),path().parent)),
            'app_read':tuple(p.resolve() for p in system_roots),'temp':tmp,
            'network':rules.get('network',True),'external':rules.get('external_tools',True)}
    if not _installed:
        sys.addaudithook(_audit)
        _installed=True
