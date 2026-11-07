"""OCR word boxes, alternate readings, geometric review and aligned page review."""
from __future__ import annotations

import csv
import difflib
import html
import io
import json
import re
import tempfile
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .ocr import OCRSettings, OCRError, _run, _tool_args, find_tesseract, preprocess_image, select_page_area


def interpret(tsv,width,height):
    words=[]
    lines=defaultdict(list)
    for r in csv.DictReader(io.StringIO(tsv),delimiter='\t',quoting=csv.QUOTE_NONE):
        if r.get('level')!='5' or not (r.get('text') or '').strip():
            continue
        x,y,w,h=(int(r[k]) for k in ('left','top','width','height'))
        key=tuple(int(r[k]) for k in ('block_num','par_num','line_num'))
        word={'text':r['text'].strip(),'box':[x,y,x+w,y+h],'confidence':round(float(r['conf']),2),'line':list(key)}
        lines[key].append(word)
        words.append(word)
    heights=sorted(w['box'][3]-w['box'][1] for w in words)
    median=heights[len(heights)//2] if heights else 1
    records=[]
    for key,group in lines.items():
        txt=' '.join(w['text'] for w in group)
        x0=min(w['box'][0] for w in group)
        x1=max(w['box'][2] for w in group)
        y0=min(w['box'][1] for w in group)
        y1=max(w['box'][3] for w in group)
        kind='heading' if y1-y0>median*1.4 else 'text'
        if x1<width*.19 or x0>width*.81:
            kind='marginal note'
        if re.search(r'[∑∫√≈≠≤≥]|\w\s*[=±×÷]\s*[-+\w(]',txt):
            kind='formula candidate'
        cells=[]
        for w in group:
            if not cells or w['box'][0]-cells[-1][-1]['box'][2]>median*2:
                cells.append([])
            cells[-1].append(w)
        records.append({'id':list(key),'kind':kind,'text':txt,'box':[x0,y0,x1,y1],
                        'cells':[' '.join(w['text'] for w in c) for c in cells],
                        'cell_left':[c[0]['box'][0] for c in cells]})
    for first,second in zip(records,records[1:]):
        if (len(first['cells'])>1 and len(first['cells'])==len(second['cells'])
            and abs(second['box'][1]-first['box'][1])<=median*4
            and all(abs(a-b)<median*2 for a,b in zip(first['cell_left'],second['cell_left']))):
            first['kind']=second['kind']='table row'
    return {'width':width,'height':height,'words':words,'lines':records,
            'text':'\n'.join(r['text'] for r in records)}


def analyze_page(source,settings,*,compare_psm=None,margin_boxes=(),margin_language=None):
    from PIL import Image
    from .ocr import _safe_image_frames
    settings.validate()
    if compare_psm is not None:
        replace(settings,psm=compare_psm).validate()
    binary=find_tesseract()
    if not binary:
        raise OCRError('Install Tesseract to produce an aligned page')
    frames=_safe_image_frames(source)
    try:
        image,_=next(frames)
    finally:
        frames.close()
    image=preprocess_image(select_page_area(image,settings),settings)
    if margin_language:
        replace(settings,language=margin_language).validate()
    with tempfile.TemporaryDirectory() as root:
        scan=Path(root)/'scan.png'
        image.save(scan)
        def recognize(psm):
            code,out,err=_run([binary,scan,'stdout','--psm',str(psm),'-l',settings.language,
                               '--dpi',str(settings.dpi),*_tool_args(binary),'-c','tessedit_create_tsv=1'],
                              timeout=settings.timeout)
            if code:
                raise OCRError(err[-1200:])
            return interpret(out,*image.size)
        report=recognize(settings.psm)
        from .advanced_ocr import order_lines,HocrStyles
        ordered,cols=order_lines(report['lines'],image,any(lang in ('ara','heb','fas','urd') for lang in settings.language.split('+')))
        from .advanced_ocr import ruled_table
        report['table_cells']=ruled_table(image,report['words'])
        report['lines']=ordered
        report['columns']=cols
        report['text']='\n'.join(r['text'] for r in ordered)
        code,out,_=_run([binary,scan,'stdout','--psm',str(settings.psm),'-l',settings.language,*_tool_args(binary),
                         '-c','tessedit_create_hocr=1','-c','hocr_font_info=1'],timeout=settings.timeout)
        if code==0:
            parser=HocrStyles()
            parser.feed(out)
            report['typography']=parser.words
            report['regions']=parser.regions
        from .advanced_ocr import sharpen_if_blurred
        _,report['sharpness_score'],report['blur_detected']=sharpen_if_blurred(image)
        if compare_psm is not None:
            other=recognize(compare_psm)
            report['comparison']={'psm':compare_psm,'text':other['text'],
                                  'diff':list(difflib.unified_diff(report['text'].splitlines(),other['text'].splitlines(),lineterm=''))}
        # Margins can be transcribed separately using a locally installed
        # historical or handwriting-trained Tesseract model.
        boxes=list(margin_boxes) or [r['box'] for r in report['lines'] if r['kind']=='marginal note']
        if len(boxes)>128:
            raise ValueError('Choose at most 128 marginal note regions')
        notes=[]
        for index,box in enumerate(boxes):
            l,t,r,b=box
            if not all(type(n)==int for n in box) or not 0<=l<r<=image.width or not 0<=t<b<=image.height:
                raise ValueError('Margin boxes must lie inside the processed scan')
            if margin_boxes or margin_language:
                snippet=Path(root)/f'margin-{index}.png'
                image.crop(tuple(box)).save(snippet)
                code,mtext,err=_run([binary,snippet,'stdout','-l',margin_language or settings.language,'--psm','6',
                                     '--dpi',str(settings.dpi),*_tool_args(binary)],timeout=settings.timeout)
                if code:raise OCRError('Margin recognition failed: '+err[-500:])
                mtext=mtext.strip()
            else:
                mtext=' '.join(w['text'] for w in report['words']
                    if l<=(w['box'][0]+w['box'][2])/2<=r and t<=(w['box'][1]+w['box'][3])/2<=b)
            notes.append({'box':list(box),'text':mtext,'language':margin_language or settings.language})
        report['marginal_notes']=notes
        body=[]
        by_line=defaultdict(list)
        for word in report['words']:
            by_line[tuple(word['line'])].append(word)
        for line in report['lines']:
            group=by_line[tuple(line['id'])]
            retained=[w['text'] for w in group if not any(
                l<=(w['box'][0]+w['box'][2])/2<=r and t<=(w['box'][1]+w['box'][3])/2<=b for l,t,r,b in boxes)]
            if retained:body.append(' '.join(retained))
        report['body_text']='\n'.join(body)
    return report,image


def write_review(source,dest,settings=OCRSettings(),compare_psm=6,*,margin_boxes=(),margin_language=None):
    import base64
    report,image=analyze_page(source,settings,compare_psm=compare_psm,margin_boxes=margin_boxes,margin_language=margin_language)
    dest=Path(dest)
    if dest.suffix.lower()=='.json':
        dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return dest
    if dest.suffix.lower() not in ('.html','.htm'):
        raise ValueError('Choose HTML for visual review or JSON for coordinates')
    raw=io.BytesIO()
    image.save(raw,'PNG')
    png=base64.b64encode(raw.getvalue()).decode()
    rects=[]
    for w in report['words']:
        x,y,right,bottom=w['box']
        label=html.escape(w['text'],quote=True)
        rects.append(f'<rect tabindex="0" role="img" aria-label="{label}" x="{x}" y="{y}" width="{right-x}" height="{bottom-y}" fill="transparent" stroke="{("#be3535" if w["confidence"]<75 else "#2d8186")}" stroke-width="2"><title>{label} ({w["confidence"]:.0f}%)</title></rect>')
    lines=[]
    for r in report['lines']:
        words=html.escape(' | '.join(r['cells']) if r['kind']=='table row' else r['text'])
        lines.append(f'<p><small>{r["kind"]}</small><br>{words}</p>')
    notes=''.join('<p>'+html.escape(n['text'])+'</p>' for n in report['marginal_notes']) or '<p>No marginal text was detected.</p>'
    page=f'''<!doctype html><meta charset="utf-8"><title>Aligned OCR review</title>
<style>body{{font:18px system-ui;margin:1em;color:#172b3a}}main{{display:grid;grid-template-columns:1fr 1fr;gap:1em}}svg{{width:100%;position:sticky;top:0;max-height:94vh}}small{{color:#516675}}textarea{{width:100%;min-height:18em}}@media(max-width:700px){{main{{display:block}}}}</style>
<h1>Aligned OCR review</h1><main><svg viewBox="0 0 {image.width} {image.height}" aria-label="Preprocessed scan and recognized word boxes"><image href="data:image/png;base64,{png}" width="{image.width}" height="{image.height}"/>{''.join(rects)}</svg>
<section><h2>Recognized layout</h2>{''.join(lines)}<h2>Marginal notes</h2>{notes}<h2>Body text</h2><textarea aria-label="Corrected body text">{html.escape(report['body_text'])}</textarea>
<button onclick="let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([document.querySelector('textarea').value],{{type:'text/plain'}}));a.download='corrected.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)">Save corrected text</button>
<h2>Alternate layout differences</h2><pre>{html.escape(chr(10).join(report.get('comparison',{}).get('diff',[])))}</pre></section></main>'''
    dest.write_text(page,encoding='utf-8')
    return dest
