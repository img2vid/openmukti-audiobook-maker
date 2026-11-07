"""Apply reviewed cast edits to saved voice profiles and explicitly tagged passages."""
from __future__ import annotations
import copy
import re

from .character_voices import CharacterProfile,VoiceProject


def update(project,source,target,*,passages=None,remove=False):
    by={p.name.casefold():p for p in project.profiles}
    old=by.get(source.casefold())
    if old is None or source.casefold()==target.casefold():
        raise ValueError('Choose distinct source and destination characters')
    if remove and old.name.casefold()=='narrator':
        raise ValueError('The Narrator profile must be kept')
    voice=by.get(target.casefold())
    if not voice:
        if remove:
            raise ValueError('Select an existing destination to merge into')
        voice=copy.deepcopy(old)
        voice.name=CharacterProfile(target).name
        voice.aliases=[]
        project.profiles.append(voice)
    names={s.casefold() for s in (old.name,*old.aliases)}
    rx=re.compile(r'\[([^\[\]\n,]+)([^\[\]\n]*)\]')
    positions=[]
    selected=None if passages is None else set(passages)
    for m in rx.finditer(project.script):
        if m[1].strip().casefold() in names:
            positions.append(m)
    if selected is not None and (not selected or min(selected)<1 or max(selected)>len(positions)):
        raise ValueError('Choose valid one-based passage numbers')
    for idx,m in reversed(list(enumerate(positions,1))):
        if selected is None or idx in selected:
            project.script=project.script[:m.start()]+'['+voice.name+m[2]+']'+project.script[m.end():]
    if remove:
        voice.aliases=list(dict.fromkeys([*voice.aliases,old.name,*old.aliases]))
        project.profiles.remove(old)
    return project


def search(project,phrase):
    from dataclasses import asdict
    needle=phrase.casefold()
    return [asdict(p) for p in project.profiles if any(needle in str(v).casefold() for v in
            (p.name,p.engine,p.language,p.voice,p.gender,p.age,p.characteristics,*p.aliases))]
