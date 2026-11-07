"""A timed, layered canvas for covers, opening cards, scene artwork and video overlays."""
from __future__ import annotations

import bisect
import json
import math
import textwrap
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

from .sound_studio import number

PALETTES = {'midnight':['#10243a','#e9f4fc','#65d3d4'], 'paper':['#fff7df','#362f28','#9d492a'],
            'chalk':['#193c36','#f9faf4','#f7d176'], 'contrast':['#000000','#ffffff','#ffff00']}
TEMPLATES = ('paperback','lecture','comic','notebook','chapter card','music')
EASING = ('linear','ease-in','ease-out','smooth')


def ease(value, style):
    t=max(0.,min(1.,value))
    if style=='ease-in':
        return t*t
    if style=='ease-out':
        return 1-(1-t)**2
    if style=='smooth':
        return t*t*(3-2*t)
    if style!='linear':
        raise ValueError('Unknown easing curve')
    return t


def template(style, title, byline='', palette='midnight'):
    bg,fg,accent=PALETTES[palette]
    if style not in TEMPLATES:
        raise ValueError('Unknown design template')
    layers=[{'type':'rectangle','box':[.08,.105,.24,.124],'color':accent},
            {'type':'text','box':[.08,.30,.92,.62],'text':title,'size':.085,'color':fg},
            {'type':'text','box':[.08,.75,.92,.89],'text':byline,'size':.043,'color':accent}]
    if style=='notebook':
        layers.insert(0,{'type':'notebook','color':accent})
    if style=='comic':
        layers.insert(0,{'type':'rectangle','box':[.03,.03,.97,.97],'outline':accent,'width':6})
    if style=='lecture':
        layers.append({'type':'progress','box':[0,.97,1,1],'color':accent})
    if style=='chapter card':
        layers[1]['fade_in']=.8
    if style=='music':
        layers.append({'type':'waveform','box':[.08,.63,.92,.75],'color':accent})
    return {'version':1,'size':[1200,1800] if style in ('paperback','comic') else [1280,720],
            'background':bg,'palette':palette,'safe_margin':.08,'layers':layers}


@lru_cache(maxsize=8)
def read_image(filename, mtime):
    with Image.open(filename) as src:
        return ImageOps.exif_transpose(src).convert('RGBA')


def focus_point(image):
    """Area of highest local edge density, biased toward the center."""
    from PIL import ImageFilter, ImageStat
    sample=image.convert('L').resize((80,80)).filter(ImageFilter.FIND_EDGES)
    scores=[]
    for y in range(1,7):
        for x in range(1,7):
            value=ImageStat.Stat(sample.crop((x*10-4,y*10-4,x*10+14,y*10+14))).mean[0]
            scores.append((value/(1+.035*(abs(4-x)+abs(4-y))), (x+.5)/8, (y+.5)/8))
    return max(scores)[1:]


def peak_envelope(path, bins=640):
    if not path:
        return []
    from .audio_analysis import waveform
    return [r[2] for r in waveform(path,bins)['points']]


class Storyboard:
    def __init__(self, data, folder='.', audio=None):
        if not isinstance(data,dict) or data.get('version',1)!=1:
            raise ValueError('Unsupported storyboard format')
        self.data=data
        self.folder=Path(folder)
        self.layers=data.get('layers',[])
        if not isinstance(self.layers,list) or len(self.layers)>128:
            raise ValueError('A storyboard supports up to 128 layers')
        self.wave=peak_envelope(audio) if audio and any(r.get('type')=='waveform' for r in self.layers) else []
        self.correction_cache={}
        self.focus_cache={}
        self.font_cache={}

    @classmethod
    def load(cls,path,audio=None):
        path=Path(path)
        return cls(json.loads(path.read_text(encoding='utf-8')),path.parent,audio)

    def _font(self, row, size, words):
        key=(row.get('font',''),size,words)
        if key not in self.font_cache:
            from .animated_video import pick_font
            self.font_cache[key]=pick_font(words,size,str(self.folder/row['font']) if row.get('font') else '')
        return self.font_cache[key]

    def layout(self, row, placed):
        box=row.get('box',[0,0,1,1])
        if not (row.get('safe') or row.get('avoid_overlap') or self.data.get('auto_layout') and row.get('type') in ('text','correction')):
            return box
        m=number(self.data.get('safe_margin',.08),0,.4,'safe margin')
        l,t,r,b=box
        w,h=min(1-2*m,r-l),min(1-2*m,b-t)
        l=max(m,min(l,1-m-w))
        t=max(m,min(t,1-m-h))
        hits=lambda v:any(max(v,top)<min(v+h,bottom) and max(l,left)<min(l+w,right) for left,top,right,bottom in placed)
        if (row.get('avoid_overlap') or self.data.get('auto_layout')) and hits(t):
            options=[m,1-m-h]+[p[3]+.008 for p in placed]+[p[1]-.008-h for p in placed]
            options=[v for v in options if m<=v<=1-m-h+.000001 and not hits(v)]
            if not options:
                raise ValueError('Text layers cannot fit the safe area together. Reduce a box or adjust its timing.')
            t=min(options,key=lambda v:abs(v-t))
        placed.append((l,t,l+w,t+h))
        return placed[-1]

    def paint(self, image, time, duration, *, foreground=False, guides=False):
        from .animated_video import _measure, _direction, ScriptFont
        from .text_layout import draw_text
        from .animated_video import graphemes
        width,height=image.size
        base=image.convert('RGBA')
        placed=[]
        for i,r in enumerate(self.layers):
            if bool(r.get('overlay',False))!=foreground:
                continue
            begin=number(r.get('start',0),0,2592000,'layer start')
            end=number(r.get('end',duration),0,2592000,'layer end')
            if time<begin or (time>=end and time!=duration) or end<=begin:
                continue
            phase=ease((time-begin)/(end-begin),r.get('ease','linear'))
            box=self.layout(r,placed)
            if len(box)!=4:
                raise ValueError('Layer boxes need four normalized coordinates')
            x,y,x1,y1=[round(number(v,0,1,'layer coordinate')*d) for v,d in zip(box,(width,height,width,height))]
            w,h=x1-x,y1-y
            if min(w,h)<1:
                continue
            layer=Image.new('RGBA',(w,h))
            d=ImageDraw.Draw(layer)
            color=r.get('color','#ffffff')
            kind=r.get('type')
            if kind=='rectangle':
                d.rectangle((0,0,w-1,h-1),fill=r.get('color') if r.get('outline') else color,
                            outline=r.get('outline'),width=int(number(r.get('width',1),1,128,'line width')))
            elif kind=='image':
                file=(self.folder/r['file']).resolve(strict=True)
                src=read_image(str(file),file.stat().st_mtime_ns)
                if r.get('crop'):
                    left,top,right,bottom=[number(v,0,1,'crop') for v in r['crop']]
                    if not left<right or not top<bottom:
                        raise ValueError('Crop needs positive dimensions')
                    src=src.crop((int(left*src.width),int(top*src.height),max(int(left*src.width)+1,int(right*src.width)),max(int(top*src.height)+1,int(bottom*src.height))))
                focus=r.get('focus',[.5,.5])
                if focus=='auto':
                    if i not in self.focus_cache:
                        self.focus_cache[i]=focus_point(src)
                    focus=self.focus_cache[i]
                fx,fy=(number(v,0,1,'focus') for v in focus)
                zoom=1+(number(r.get('zoom',1),1,4,'end zoom')-1)*phase
                pan=number(r.get('pan',0),-1,1,'parallax offset')
                centered=max(0,min(1,fx+pan*(phase-.5)))
                # Crop at source resolution before scaling, so zoom retains detail.
                target_ratio=w/h
                cw=min(src.width,src.height*target_ratio)/zoom
                ch=cw/target_ratio
                sx=(src.width-cw)*centered
                sy=(src.height-ch)*fy
                layer=src.resize((w,h),Image.Resampling.LANCZOS,box=(sx,sy,min(src.width,sx+cw),min(src.height,sy+ch)))
            elif kind=='text':
                words=str(r.get('text',''))
                size=max(8,round(number(r.get('size',.06),.005,1,'font size')*min(width,height)))
                font=self._font(r,size,words)
                yy=0
                for para in words.split('\n'):
                    line=''
                    for unit in graphemes(para):
                        if line and _measure(font,line+unit,_direction(line+unit))>w:
                            self._draw_line(d,line,font,yy,w,color,r)
                            yy+=round(size*1.4)
                            line=''
                        line+=unit
                    self._draw_line(d,line,font,yy,w,color,r)
                    yy+=round(size*1.4)
            elif kind=='correction':
                old=str(r.get('original',''))
                new=str(r.get('text',''))
                fs=max(8,round(number(r.get('size',.06),.005,1,'font size')*min(width,height)))
                font=self._font(r,fs,old+new)
                if phase<.64:
                    self._draw_line(d,old,font,0,w,color,r)
                    if phase>=.22:
                        extent=min(w,round(_measure(font,old,_direction(old))))
                        d.line((0,fs*.67,extent*min(1,(phase-.22)/.18),fs*.59),fill=r.get('strike_color','#c92728'),width=max(1,fs//16))
                    if phase>.42:
                        erased=round(w*(phase-.42)/.22)
                        layer.paste((0,0,0,0),(0,0,erased,h))
                else:
                    from .ink_engine import prepare_step,stylize_step,draw_step
                    key=(i,w,h,fs,color,new)
                    if key not in self.correction_cache:
                        self._draw_line(d,new,font,0,w,color,r)
                        step=prepare_step(layer,0,w,0,h,0,1,_direction(new),cluster=new)
                        if step:
                            stylize_step(step,calligraphy=False,font_size=fs,color=ImageColor.getrgb(color))
                        self.correction_cache[key]=step
                    layer=Image.new('RGBA',(w,h))
                    step=self.correction_cache[key]
                    if step:
                        fragment,_=draw_step(step,(phase-.64)/.36,calligraphy=False,font_size=fs)
                        if fragment:
                            layer.alpha_composite(fragment,(step.left,step.top))
            elif kind=='notebook':
                step=max(6,round(height*number(r.get('spacing',.055),.005,.5,'line spacing')))
                for yy in range(step,h,step):
                    d.line((0,yy,w,yy),fill=color,width=1)
            elif kind=='progress':
                d.rectangle((0,0,round(w*phase),h),fill=color)
            elif kind=='waveform':
                if self.wave:
                    sample=round(phase*(len(self.wave)-1))
                    for j in range(min(w,180)):
                        n=min(len(self.wave)-1,max(0,sample+j-90))
                        ht=round(self.wave[n]*h*.47)
                        xx=j*w/min(w,180)
                        d.line((xx,h//2-ht,xx,h//2+ht),fill=color,width=max(1,w//180-1))
            else:
                raise ValueError('Unknown storyboard layer type: '+str(kind))
            alpha=number(r.get('opacity',1),0,1,'opacity')
            for key,elapsed in [('fade_in',time-begin),('fade_out',end-time)]:
                if r.get(key):
                    alpha*=min(1,elapsed/number(r[key],.001,2592000,key))
            transition=r.get('transition','fade')
            if transition not in ('fade','wipe-left','wipe-right','dissolve'):
                raise ValueError('Unknown layer transition')
            if transition!='fade' and alpha<1:
                from PIL import ImageChops
                import numpy as np
                if transition=='dissolve':
                    yy,xx=np.ogrid[:h,:w]
                    mask=(((xx*73856093 ^ yy*19349663) % 256)<round(256*alpha)).astype('uint8')*255
                    layer.putalpha(ImageChops.multiply(layer.getchannel('A'),Image.fromarray(mask)))
                elif transition=='wipe-left':
                    layer.paste((0,0,0,0),(0,0,round((1-alpha)*w),h))
                else:
                    layer.paste((0,0,0,0),(round(alpha*w),0,w,h))
            elif alpha<1:
                layer.putalpha(layer.getchannel('A').point(lambda v:round(v*alpha)))
            from .compute import composite
            composite(base,layer,(x,y))
        if guides and foreground:
            d=ImageDraw.Draw(base)
            margin=number(self.data.get('safe_margin',.08),0,.4,'safe margin')
            d.rectangle((width*margin,height*margin,width*(1-margin),height*(1-margin)),outline='#ff8b32',width=2)
            for f in (1/3,2/3):
                d.line((width*f,0,width*f,height),fill='#7e8992')
                d.line((0,height*f,width,height*f),fill='#7e8992')
        return base.convert('RGB')

    @staticmethod
    def _draw_line(draw,text,font,y,width,color,row):
        from .animated_video import _direction, _measure, ScriptFont
        from .text_layout import draw_text
        direction=_direction(text)
        extra=width-_measure(font,text,direction)
        align=row.get('align','right' if direction=='rtl' else 'left')
        x=max(0,round(extra/2 if align=='center' else extra if align=='right' else 0))
        if isinstance(font,ScriptFont):
            font.draw_text(draw,(x,y),text,fill=color,direction=direction)
        else:
            draw_text(draw,(x,y),text,font,color,direction)

    def export_cover(self,out,time=0,duration=10,guides=False):
        target=Path(out)
        canvas=self.preview(time,duration,guides=guides)
        alt='\n'.join(str(r['alt']) for r in self.layers if r.get('alt') and r.get('start',0)<=time<=r.get('end',duration))
        from .security_tools import staged_file
        with staged_file(target) as tmp:
            if target.suffix.lower()=='.png' and alt:
                from PIL.PngImagePlugin import PngInfo
                metadata=PngInfo()
                metadata.add_itxt('Description',alt)
                canvas.save(tmp,'PNG',pnginfo=metadata)
            else:
                canvas.save(tmp)
        return target

    def preview(self,time=0,duration=10,size=None,guides=False):
        dims=size or self.data.get('size',[1280,720])
        if len(dims)!=2 or any(type(x)!=int or not 16<=x<=7680 for x in dims):
            raise ValueError('Canvas dimensions must be 16–7680 pixels')
        base=Image.new('RGB',tuple(dims),self.data.get('background','#101820'))
        import os
        if os.environ.get('OPENMUKTI_REDUCED_MOTION')=='1':
            # Keep the selected scene visible while suppressing pan, zoom, fades and wipes in previews.
            import copy
            still=copy.copy(self)
            still.layers=[dict(r,zoom=1,pan=0,fade_in=0,fade_out=0,transition='fade') for r in self.layers]
            return still.paint(still.paint(base,time,duration),time,duration,foreground=True,guides=guides)
        return self.paint(self.paint(base,time,duration),time,duration,foreground=True,guides=guides)
