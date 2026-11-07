"""Persist user-owned display, device and access policy preferences."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .voice_library import _atomic_json


def path():
    from .neural_runtime import cache_home
    return cache_home().parent/'desktop.json'


def read():
    try:
        data=json.loads(path().read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (ValueError,OSError):
        return {}


def replace_preferences(data):
    from .access_policy import configure
    previous=read()
    configure(data)
    try:
        _atomic_json(path(),data)
    except BaseException:
        configure(previous)
        raise
    return data


def write(**changes):
    return replace_preferences({**read(),**changes})


def authorized(action,filename=None):
    policy=read().get('permissions',{})
    if policy.get(action,True) is False:
        raise PermissionError(f'{action} access is disabled in Studio preferences')
    if filename is not None and policy.get('folders'):
        root=Path(filename).expanduser().resolve()
        if not any(root.is_relative_to(Path(f).expanduser().resolve()) for f in policy['folders']):
            raise PermissionError(f'Choose a file within a folder allowed by Studio preferences: {root.name}')


def activate():
    prefs=read()
    if prefs.get('cpu_profile') in ('low','balanced','fast'):
        from .hardware import apply_cpu_profile
        apply_cpu_profile(prefs['cpu_profile'])
    if prefs.get('gpu_mode') in ('auto','cpu'):
        os.environ.setdefault('OPENMUKTI_GPU_MODE',prefs['gpu_mode'])
    if prefs.get('render_cache'):
        os.environ.setdefault('OPENMUKTI_RENDER_CACHE',str(prefs['render_cache']))
    if prefs.get('model_lock'):
        os.environ.setdefault('OPENMUKTI_MODEL_LOCK',str(prefs['model_lock']))
    from .access_policy import configure
    configure(prefs)
    return prefs
