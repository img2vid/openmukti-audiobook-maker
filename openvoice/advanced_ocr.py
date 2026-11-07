"""Page sharpness, historical print normalization and local hOCR typography."""
import re
import unicodedata
from html.parser import HTMLParser


def sharpen_if_blurred(image):
    import numpy as np
    from PIL import Image,ImageFilter
    sample=image.convert('L')
    sample.thumbnail((1000,1000))
    a=np.asarray(sample,dtype=np.float32)
    if min(a.shape)<3:
        return image,0.,False
    lap=a[:-2,1:-1]+a[2:,1:-1]+a[1:-1,:-2]+a[1:-1,2:]-4*a[1:-1,1:-1]
    # Evaluate only text-bearing tiles so large white margins do not mimic blur.
    scores=[]
    for y in range(0,a.shape[0]-2,64):
        for x in range(0,a.shape[1]-2,64):
            block=a[y:y+64,x:x+64]
            if block.max()-block.min()>45:
                scores.append(float(lap[y:y+64,x:x+64].var()))
    score=float(np.median(scores)) if scores else 0.
    blurred=bool(scores) and score<130
    return (image.filter(ImageFilter.UnsharpMask(radius=1.8,percent=175,threshold=3)) if blurred else image,round(score,2),blurred)


def historical(text):
    return text.translate(str.maketrans({'ſ':'s','ﬀ':'ff','ﬁ':'fi','ﬂ':'fl','ﬃ':'ffi','ﬄ':'ffl','ﬅ':'st','ﬆ':'st'}))


class HocrStyles(HTMLParser):
    def __init__(self):
        super().__init__()
        self.words=[]
        self.regions=[]
        self.stack=[]
        self.active=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        classes=attrs.get('class','').split()
        for name,kind in [('ocr_photo','illustration'),('ocr_image','illustration'),('ocr_separator','separator'),
                          ('ocr_par','paragraph'),('ocr_carea','content block'),('ocr_header','heading')]:
            if name in classes:
                bounds=re.search(r'\bbbox (\d+) (\d+) (\d+) (\d+)',attrs.get('title',''))
                if bounds:
                    self.regions.append({'kind':kind,'box':list(map(int,bounds.groups()))})
        if 'ocrx_word' in classes:
            title=attrs.get('title','')
            box=re.search(r'\bbbox (\d+) (\d+) (\d+) (\d+)',title)
            self.active={'box':list(map(int,box.groups())) if box else [],'text':'','bold':False,'italic':False,
                         'font':(re.search(r'x_font ([^;]+)',title)[1] if re.search(r'x_font ([^;]+)',title) else '')}
            self.stack=[tag]
        elif self.active is not None:
            if tag in ('strong','b'):
                self.active['bold']=True
            if tag in ('em','i'):
                self.active['italic']=True
            if tag not in ('br','img','meta','link','input','hr'):
                self.stack.append(tag)
    def handle_endtag(self,tag):
        if self.active is None:
            return
        if self.stack and self.stack[-1]==tag:
            self.stack.pop()
        if not self.stack:
            self.words.append(self.active)
            self.active=None
    def handle_data(self,data):
        if self.active is not None:
            self.active['text']+=data


def columns(image):
    """Find wide vertical gutters with ink on both sides, inside the body of the page."""
    import numpy as np
    a=np.asarray(image.convert('L'))
    h,w=a.shape
    if w<140 or h<160:
        return [(0,w)]
    activity=(a[int(.12*h):int(.89*h)]<140).mean(axis=0)
    gaps=[]
    start=None
    import itertools
    for blank,items in itertools.groupby(enumerate(activity),lambda p:p[1]<.007):
        span=[x for x,v in items]
        if blank and len(span)>=max(15,w*.032) and .16*w<span[0]<span[-1]<.84*w:
            gaps.append((span[0]+span[-1])//2)
    edges=[0]
    for mid in gaps:
        if mid-edges[-1]>=w*.18 and w-mid>=w*.18 and activity[edges[-1]:mid].mean()>.018:
            edges.append(mid)
    edges.append(w)
    return list(zip(edges,edges[1:]))


def order_lines(lines,image,rtl=False):
    cols=columns(image)
    if len(cols)<=1:
        return lines,cols
    # Full-width headings split the page into bands before column ordering.
    splits=[c[1] for c in cols[:-1]]
    spanning=lambda line:any(line['box'][0]<x-10 and line['box'][2]>x+10 for x in splits)
    headings=sorted((r for r in lines if spanning(r)),key=lambda r:r['box'][1])
    others=[r for r in lines if not spanning(r)]
    output=[]
    def band(rows):
        for left,right in (reversed(cols) if rtl else cols):
            output.extend(sorted([r for r in rows if left<=(r['box'][0]+r['box'][2])/2<right],key=lambda r:(r['box'][1],r['box'][0])))
    for head in headings:
        y=head['box'][1]
        band([r for r in others if r['box'][1]<y])
        others=[r for r in others if r['box'][1]>=y]
        output.append(head)
    band(others)
    return output,cols


def ruled_table(image,words):
    """Recover ruled cell boundaries, including empty cells, from their scanned grid."""
    import itertools
    import numpy as np
    a=np.asarray(image.convert('L'))<110
    h,w=a.shape
    def runs(mask):
        result=[]
        for hit,g in itertools.groupby(enumerate(mask),lambda v:bool(v[1])):
            group=list(g)
            if hit:
                result.append((group[0][0]+group[-1][0])//2)
        return result
    ys=runs(a.sum(axis=1)>.38*w)
    if len(ys)<2:
        return []
    xs=runs(a[ys[0]:ys[-1]+1].mean(axis=0)>.66)
    if not 2<=len(xs)<=100 or len(ys)>300:
        return []
    cells=[]
    for row,(top,bottom) in enumerate(zip(ys,ys[1:])):
        for col,(left,right) in enumerate(zip(xs,xs[1:])):
            if bottom-top<4 or right-left<4:
                continue
            inside=[word['text'] for word in words if left<=(word['box'][0]+word['box'][2])/2<right and top<=(word['box'][1]+word['box'][3])/2<bottom]
            cells.append({'row':row+1,'column':col+1,'box':[left,top,right,bottom],'text':' '.join(inside)})
    return cells
