"""Project-scoped editorial rules, revision records and speaker/scene reporting."""
from __future__ import annotations

import difflib
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .voice_library import _atomic_json

CONTEXT_RULES = ((r'\bwould of\b','would have'),(r'\bcould of\b','could have'),
                 (r'\bshould of\b','should have'),(r'\btheir is\b','there is'),
                 (r'\bit(?:\x27|’)s (own|way|place)\b',None),
                 (r'\bbetween you and I\b','between you and me'))
MATTER=re.compile(r"^(?:(preface|foreword|dedication|introduction|acknowledg(?:e)?ments?)|(appendix|glossary|bibliography|index|afterword)|(author[’']?s? note))\b",re.I)


def section_kind(title):
    m=MATTER.search(title.strip().lstrip('# '))
    return ('front matter' if m[1] else 'back matter' if m[2] else "author's note") if m else 'chapter'


def suggestions(text,rules=None):
    rules=rules or {}
    issues=[]
    protected=[(m.start(),m.end()) for term in [*rules.get('protected',[]),*rules.get('terms',[])] if term
               for m in re.finditer(re.escape(term),text)]
    def offer(a,b,new,reason):
        if not any(a<y and x<b for x,y in protected):
            issues.append({'start':a,'end':b,'original':text[a:b],'replacement':new,'reason':reason})
    if 'context' in rules.get('engines',['context','duplicates','agreement']):
        for pattern,new in CONTEXT_RULES:
            for m in re.finditer(pattern,text,re.I):
                replacement=new or 'its '+m[1]
                offer(*m.span(),replacement.capitalize() if m[0][0].isupper() else replacement,'context')
    if 'duplicates' in rules.get('engines',['duplicates']):
        for m in re.finditer(r'\b([^\W\d_]+)([ \t]+)\1\b',text,re.I):
            offer(*m.span(),m[1],'repeated word')
    if 'agreement' in rules.get('engines',['agreement']):
        for m in re.finditer(r'\b(he|she|it) (are|have|do)\b|\b(they|we) (is|has|does)\b',text,re.I):
            subject=m[1] or m[3]
            verb={'are':'is','have':'has','do':'does','is':'are','has':'have','does':'do'}[(m[2] or m[4]).lower()]
            offer(*m.span(),subject+' '+verb,'subject–verb agreement')
    for category in ('style','learned'):
        for a,b in rules.get(category,{}).items():
            if a and isinstance(b,str):
                for m in re.finditer(r'(?<!\w)'+re.escape(a)+r'(?!\w)',text):
                    offer(*m.span(),b,category)
    if rules.get('languagetool'):
        for issue in grammar_service(text,rules['languagetool']):
            offer(*issue)
    return sorted(issues,key=lambda r:(r['start'],r['end']))


def learn_edits(original,corrected,rules):
    a,b=re.findall(r"[\w’'-]+",original),re.findall(r"[\w’'-]+",corrected)
    counts=rules.setdefault('observations',{})
    for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if tag=='replace' and j==i+1 and l==k+1 and a[i]!=b[k]:
            choices=counts.setdefault(a[i],{})
            choices[b[k]]=choices.get(b[k],0)+1
            if choices[b[k]]>=2 and len(choices)==1:
                rules.setdefault('learned',{})[a[i]]=b[k]
            elif len(choices)>1:
                rules.setdefault('learned',{}).pop(a[i],None)
    return rules


def apply_suggestions(text,issues):
    cursor=0
    output=[]
    for issue in sorted(issues,key=lambda x:x['start']):
        a,b=issue['start'],issue['end']
        if a<cursor:
            continue
        if text[a:b]!=issue['original']:
            raise ValueError('The reviewed manuscript has changed')
        output.extend((text[cursor:a],issue['replacement']))
        cursor=b
    return ''.join(output)+text[cursor:]


def compare_html(a,b,out):
    doc=difflib.HtmlDiff(wrapcolumn=75).make_file(a.splitlines(),b.splitlines(),
                                             fromdesc='Original',todesc='Edited',context=False)
    Path(out).write_text(doc,encoding='utf-8')


def record_revision(settings,original,updated,label):
    if original==updated:
        return
    record={'time':datetime.now(timezone.utc).isoformat(timespec='seconds'),'label':label,
            'changes':list(difflib.ndiff(original.splitlines(keepends=True),updated.splitlines(keepends=True)))}
    settings.setdefault('revisions',[]).append(record)


def script_report(text, known=(), rules=None):
    from .dialogue_analysis import analyze_dialogue
    from .book_structure import detect_scene_breaks
    from .character_voices import detect_language
    analysis=analyze_dialogue(text,known_names=known)
    events=[]
    speaker_rules=(rules or {}).get('speakers',{})
    for q in analysis.quotations:
        passage=text[q.start:q.end]
        around=text[max(0,q.start-65):q.start]+' '+text[q.end:q.end+65]
        thought=bool(re.search(r'\b(thought|wondered|thought to (?:himself|herself|themselves))\b',around,re.I))
        speaker=next((name for match,name in speaker_rules.items() if match and match in passage),q.speaker)
        events.append({'start':q.start,'end':q.end,'kind':'thought' if thought else 'dialogue','speaker':speaker,
                       'words':len(passage.split()),'text':passage,'language':detect_language(passage)[0]})
    quoted=[(e['start'],e['end']) for e in events]
    for m in re.finditer(r"\b([A-Z][\w’-]+|[Hh]e|[Ss]he|[Tt]hey)\s+(said|told|explained|thought|wondered|remembered)\s+(?:that\s+|whether\s+|if\s+)([^.!?\n]+)",text):
        if any(a<=m.start()<b for a,b in quoted):
            continue
        events.append({'start':m.start(),'end':m.end(),'kind':'thought' if m[2] in ('thought','wondered','remembered') else 'reported speech',
                       'speaker':m[1],'words':len(m[0].split()),'text':m[0]})
    events.sort(key=lambda e:e['start'])
    mentions={name:[m.start() for m in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',text,re.I)]
              for name in dict.fromkeys([*known,*analysis.characters])}
    counts=Counter()
    for e in events:
        if e['kind']=='dialogue':
            counts[e['speaker']]+=e['words']
    from .dialogue_analysis import SCENE
    import bisect,itertools
    boundaries=[m.end() for m in SCENE.finditer(text)]
    casts=defaultdict(set)
    for name,offsets in mentions.items():
        for pos in offsets:
            casts[bisect.bisect_right(boundaries,pos)].add(name)
    pairs=Counter(pair for cast in casts.values() for pair in itertools.combinations(sorted(cast),2))
    return {'events':events,'dialogue_words':dict(counts),'mentions':mentions,
            'relationships':[{'first':a,'second':b,'shared_scenes':n} for (a,b),n in pairs.items()],
            'scene_boundaries':boundaries}


def write_script_view(report,path):
    import math
    names=list(report['mentions'])
    width=720
    height=max(420,len(names)*21)
    positions={name:(width/2+width*.33*math.cos(2*math.pi*i/max(1,len(names))),
                     height/2+height*.38*math.sin(2*math.pi*i/max(1,len(names)))) for i,name in enumerate(names)}
    svg=[]
    for edge in report['relationships']:
        x,y=positions[edge['first']]
        u,v=positions[edge['second']]
        svg.append(f'<line x1="{x}" y1="{y}" x2="{u}" y2="{v}" stroke="#69a5ad" stroke-width="{min(8,edge["shared_scenes"]+1)}"><title>{edge["shared_scenes"]} shared scenes</title></line>')
    for name,(x,y) in positions.items():
        svg.append(f'<circle cx="{x}" cy="{y}" r="7" fill="#27566b"/><text x="{x}" y="{y-12}" text-anchor="middle">{html.escape(name)}</text>')
    rows=''.join('<tr>'+''.join('<td>'+html.escape(str(e.get(k,'')))+'</td>' for k in ('start','kind','speaker','text'))+'</tr>' for e in report['events'])
    content=f'<!doctype html><meta charset="utf-8"><title>Cast and dialogue</title><style>body{{font:16px system-ui;max-width:72em;margin:auto}}table{{border-collapse:collapse}}td,th{{padding:.4em;border:1px solid #b6ced3}}svg{{width:100%;max-height:60vh}}</style><h1>Cast and dialogue</h1><h2>Characters who share scenes</h2><svg viewBox="0 0 {width} {height}">{"".join(svg)}</svg><h2>Attribution timeline</h2><table><tr><th>Offset</th><th>Type</th><th>Speaker</th><th>Passage</th></tr>{rows}</table>'
    Path(path).write_text(content,encoding='utf-8')


def grammar_service(text,settings):
    """Optional local LanguageTool server. Only a user-selected loopback port is contacted."""
    import http.client,urllib.parse
    from .desktop_prefs import authorized
    authorized('network')
    port=int(settings.get('port',8081))
    if not 1<=port<=65535:
        raise ValueError('Choose a valid local LanguageTool port')
    conn=http.client.HTTPConnection('127.0.0.1',port,timeout=30)
    try:
        conn.request('POST','/v2/check',urllib.parse.urlencode({'text':text,'language':settings.get('language','auto')}),
                     {'Content-Type':'application/x-www-form-urlencoded'})
        response=conn.getresponse()
        if response.status!=200:
            raise RuntimeError('LanguageTool returned HTTP '+str(response.status))
        raw=response.read(8*1024**2+1)
        if len(raw)>8*1024**2:
            raise ValueError('Grammar service response exceeds size limit')
        result=json.loads(raw)
    finally:
        conn.close()
    # Java offsets index UTF-16 code units, including surrogate pairs.
    offsets={0:0}
    n=0
    for i,c in enumerate(text,1):
        n+=2 if ord(c)>0xffff else 1
        offsets[n]=i
    issues=[]
    for m in result.get('matches',[]):
        a=offsets.get(m['offset'])
        b=offsets.get(m['offset']+m['length'])
        alternatives=m.get('replacements',[])
        if a is None or b is None or not alternatives:
            continue
        issues.append((a,b,alternatives[0]['value'],m.get('message','grammar')))
    return issues


def emphasis_advice(text):
    rules=[(r'\b(?:only|never|always|especially|must|finally)\b','contrast or focus'),
           (r'\b[A-Z]{2,}\b','capitalized emphasis'),
           (r"\b[\w’-]+(?=[!?])",'emphatic punctuation')]
    return [{'start':m.start(),'end':m.end(),'word':m[0],'reason':why} for pattern,why in rules for m in re.finditer(pattern,text)]
