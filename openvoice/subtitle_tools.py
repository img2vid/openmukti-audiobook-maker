"""Edit actual timed subtitles and test caption, title and illustration bounds."""
from pathlib import Path
import json
from .animated_video import load_cues
from .video import _srt_time
from .security_tools import staged_file
from .sound_studio import number


def export_cues(rows,output):
    target=Path(output)
    normalized=[]
    last=0.
    for r in rows:
        start=number(r['start'],last,2592000,'subtitle start')
        end=number(r['end'],start,2592000,'subtitle end')
        if end<=start or not str(r['text']).strip():
            raise ValueError('Each cue requires text and a positive, nonoverlapping interval')
        normalized.append({'start':start,'end':end,'text':str(r['text'])})
        last=end
    if not normalized:
        raise ValueError('Add at least one cue')
    ext=target.suffix.lower()
    if ext=='.json':
        text=json.dumps(normalized,ensure_ascii=False,indent=2)
    elif ext in ('.vtt','.srt'):
        text='WEBVTT\n\n' if ext=='.vtt' else ''
        for i,r in enumerate(normalized,1):
            stamp=_srt_time(r['start'])+' --> '+_srt_time(r['end'])
            text+=('' if ext=='.vtt' else str(i)+'\n')+(stamp.replace(',','.') if ext=='.vtt' else stamp)+'\n'+r['text']+'\n\n'
    else:
        raise ValueError('Save subtitles as SRT, WebVTT or JSON')
    with staged_file(target) as tmp:
        tmp.write_text(text,encoding='utf-8')
    return target


def layout_check(board,caption_box=None):
    margin=number(board.get('safe_margin',.08),0,.4,'safe margin')
    issues=[]
    labels=[(i,l) for i,l in enumerate(board.get('layers',[]),1) if l.get('type')=='text']
    if caption_box:
        labels.append(('captions',{'box':caption_box,'type':'text'}))
    for n,(i,a) in enumerate(labels):
        left,top,right,bottom=a.get('box',[0,0,1,1])
        if not margin<=left<right<=1-margin or not margin<=top<bottom<=1-margin:
            issues.append({'layer':i,'issue':'outside safe area'})
        for j,b in labels[n+1:]:
            if max(a.get('start',0),b.get('start',0))>=min(a.get('end',1e9),b.get('end',1e9)):
                continue
            x,y,xx,yy=b.get('box',[0,0,1,1])
            if max(left,x)<min(right,xx) and max(top,y)<min(bottom,yy):
                issues.append({'layers':[i,j],'issue':'overlapping text areas'})
    return issues
