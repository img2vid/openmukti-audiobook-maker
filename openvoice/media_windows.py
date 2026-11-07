"""Layer editor, waveform selection and multitrack timeline for the desktop application."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser

from .studio_windows import async_job,button,line,guarded,edit_json,DesignHistory,register_structured_undo
from .windowing import fit_window
from .voice_library import _atomic_json


class CanvasDesigner:
    def __init__(self,app):
        from .storyboard import template,TEMPLATES,PALETTES
        self.app=app
        self.win=tk.Toplevel(app.root)
        self.win.title('Cover and video designer')
        fit_window(self.win,930,710,420,370)
        self.history=DesignHistory()
        register_structured_undo(self.win,self.undo)
        self.path=None
        self.folder=Path.cwd()
        self.data=template('paperback','Book title','Author')
        self.style=tk.StringVar(value='paperback')
        self.palette=tk.StringVar(value='midnight')
        self.time=tk.DoubleVar(value=0)
        self.duration=tk.DoubleVar(value=12)
        self.guides=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='Choose a layer to move it on the canvas.')
        bar=line(self.win)
        ttk.Combobox(bar,textvariable=self.style,values=TEMPLATES,width=13,state='readonly').pack(side='left')
        ttk.Combobox(bar,textvariable=self.palette,values=list(PALETTES),width=10,state='readonly').pack(side='left')
        button(bar,'New design',self.new)
        button(bar,'Open',self.open)
        button(bar,'Save',self.save)
        button(bar,'Export cover',self.export)
        button(bar,'Use in video',self.use)
        button(bar,'Undo',lambda:self.undo(-1))
        button(bar,'Redo',lambda:self.undo(1))
        bar=line(self.win)
        for text,method in [('Add artwork',self.add_image),('Add text',self.add_text),('Watermark',self.watermark),('Panel tour',self.panels),
                            ('Layer properties',self.edit),('Remove',self.remove),('Choose color',self.color)]:
            button(bar,text,method)
        pane=ttk.Panedwindow(self.win,orient='horizontal')
        pane.pack(expand=True,fill='both')
        left=ttk.Frame(pane)
        pane.add(left,weight=1)
        self.layers=tk.Listbox(left,exportselection=False,width=20)
        self.layers.pack(fill='both',expand=True)
        self.layers.bind('<Double-Button-1>',lambda e:guarded(self.win,self.edit)())
        self.layers.bind('<<ListboxSelect>>',lambda e:self.draw())
        self.canvas=tk.Canvas(pane,bg='#18242e',highlightthickness=0,takefocus=True)
        pane.add(self.canvas,weight=4)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.drag_start)
        self.canvas.bind('<ButtonRelease-1>',guarded(self.win,self.drag_end))
        self.anchor=None
        self.photo=None
        self.visual=None
        controls=line(self.win)
        ttk.Label(controls,text='Preview time').pack(side='left')
        ttk.Scale(controls,from_=0,to=60,variable=self.time,command=lambda _:self.draw()).pack(fill='x',expand=True,side='left')
        ttk.Checkbutton(controls,text='Show grid and safe area',variable=self.guides,command=self.draw).pack(side='left')
        ttk.Label(self.win,textvariable=self.status,wraplength=650).pack(fill='x')
        self.refresh()

    def undo(self,delta):
        self.data=self.history.move(delta)
        self.refresh()

    def refresh(self,index=None):
        self.history.remember(self.data)
        from .storyboard import Storyboard
        self.visual=Storyboard(self.data,self.folder)
        self.layers.delete(0,'end')
        for row in self.data['layers']:
            label=row.get('text') or row.get('alt') or Path(row.get('file','')).name
            self.layers.insert('end',row['type']+'  '+str(label)[:45])
        if index is not None and self.data['layers']:
            self.layers.selection_set(min(index,len(self.data['layers'])-1))
        self.draw()

    def current(self):
        sel=self.layers.curselection()
        if not sel:
            raise ValueError('Select a layer')
        return sel[0]

    def bounds(self):
        w,h=self.data.get('size',[1280,720])
        ratio=min(max(16,self.canvas.winfo_width()-16)/w,max(16,self.canvas.winfo_height()-16)/h,1.4)
        dims=(max(16,round(w*ratio)),max(16,round(h*ratio)))
        return (self.canvas.winfo_width()-dims[0])//2,(self.canvas.winfo_height()-dims[1])//2,dims

    def draw(self):
        if self.canvas.winfo_width()<20 or not self.visual:
            return
        from PIL import ImageTk
        try:
            x,y,size=self.bounds()
            im=self.visual.preview(self.time.get(),max(self.duration.get(),self.time.get()+.001),size,self.guides.get())
            self.photo=ImageTk.PhotoImage(im,master=self.win)
            self.canvas.delete('all')
            self.canvas.create_image(x,y,image=self.photo,anchor='nw')
            if self.layers.curselection():
                r=self.data['layers'][self.current()].get('box',[0,0,1,1])
                self.canvas.create_rectangle(x+r[0]*size[0],y+r[1]*size[1],x+r[2]*size[0],y+r[3]*size[1],outline='#f85a36',width=2,dash=(4,2))
            self.status.set(f'Preview at {self.time.get():.2f} seconds')
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            self.status.set(str(exc))

    def drag_start(self,e):
        self.anchor=(e.x,e.y)
    def drag_end(self,e):
        if not self.anchor or not self.layers.curselection():
            return
        _,_,dims=self.bounds()
        row=self.data['layers'][self.current()]
        a,b,c,d=row.get('box',[0,0,1,1])
        dx=max(-a,min(1-c,(e.x-self.anchor[0])/dims[0]))
        dy=max(-b,min(1-d,(e.y-self.anchor[1])/dims[1]))
        row['box']=[a+dx,b+dy,c+dx,d+dy]
        self.draw()

    def new(self):
        from .storyboard import template
        title=simpledialog.askstring('New design','Book or chapter title',parent=self.win)
        if title is None:
            return
        self.history=DesignHistory()
        self.data=template(self.style.get(),title,'',self.palette.get())
        self.path=None
        self.refresh()

    def open(self):
        name=filedialog.askopenfilename(parent=self.win,filetypes=[('Storyboard','*.json')])
        if not name:
            return
        from .storyboard import Storyboard
        visual=Storyboard.load(name)
        self.history=DesignHistory()
        self.path=Path(name)
        self.folder=self.path.parent
        self.data=visual.data
        self.refresh()

    def save(self):
        name=filedialog.asksaveasfilename(parent=self.win,initialfile=self.path.name if self.path else 'cover.json',defaultextension='.json')
        if not name:
            return
        path=Path(name).resolve()
        for row in self.data['layers']:
            for key in ('file','font'):
                if row.get(key):
                    src=(self.folder/row[key]).resolve()
                    try:
                        row[key]=os.path.relpath(src,path.parent)
                    except ValueError:
                        row[key]=str(src)
        self.history=DesignHistory() if path.parent!=self.folder else self.history
        self.path=path
        self.folder=path.parent
        _atomic_json(path,self.data)
        self.refresh()
        return path

    def export(self):
        path=filedialog.asksaveasfilename(parent=self.win,defaultextension='.png',filetypes=[('PNG cover','*.png')])
        if path:
            self.visual.export_cover(path,self.time.get(),max(self.duration.get(),self.time.get()+.001))

    def use(self):
        path=self.save()
        if path:
            self.app.video_options.update(storyboard=str(path))
            self.status.set('Design assigned to the current project video')

    def add_image(self):
        name=filedialog.askopenfilename(parent=self.win,filetypes=[('Artwork','*.png *.jpg *.jpeg *.webp *.bmp *.tif')])
        if not name:
            return
        alt=simpledialog.askstring('Illustration','Alternative text or description',parent=self.win)
        self.data['layers'].append({'type':'image','file':str(Path(name).resolve()),'alt':alt or '', 'box':[.12,.13,.88,.67],'focus':'auto','zoom':1})
        self.refresh(len(self.data['layers'])-1)

    def add_text(self,watermark=False):
        t=simpledialog.askstring('Text layer','Text to display',parent=self.win)
        if t:
            self.data['layers'].append({'type':'text','text':t,'box':[.5,.88,.97,.99] if watermark else [.1,.4,.9,.65],
                                        'size':.035 if watermark else .07,'color':'#ffffff','opacity':.58 if watermark else 1,'overlay':watermark})
            self.refresh(len(self.data['layers'])-1)

    def panels(self):
        from .visual_tools import panel_tour
        name=filedialog.askopenfilename(parent=self.win,title='Select a comic page')
        if not name:
            return
        def apply(d):
            layers=panel_tour(str(Path(name).resolve()),d['panels'],d.get('seconds',3))
            self.data['layers'].extend(layers)
            self.refresh(len(self.data['layers'])-1)
        from .gui_workflows import PanelTour
        return PanelTour(self.win,name,apply)

    def watermark(self):
        self.add_text(True)
    def remove(self):
        i=self.current()
        self.data['layers'].pop(i)
        self.refresh(i)
    def edit(self):
        i=self.current()
        def change(row):
            self.data['layers'][i]=row
            self.refresh(i)
        row=dict(self.data['layers'][i])
        defaults={'box':[0.0,0.0,1.0,1.0],'opacity':1.0,'start':0.0,'fade_in':0.0,'fade_out':0.0,'ease':'linear','safe':False,'avoid_overlap':False}
        defaults['end']=max(float(row.get('start',0))+.1,float(self.duration.get()))
        if row.get('type')=='image':defaults.update(crop=[0.0,0.0,1.0,1.0],zoom=1.0)
        for k,v in defaults.items():row.setdefault(k,v)
        edit_json(self.win,'Layer position, timing, crop, easing and color',row,change)
    def color(self):
        i=self.current()
        c=colorchooser.askcolor(parent=self.win)[1]
        if c:
            self.data['layers'][i]['color']=c
            self.refresh(i)


class SoundDesk:
    def __init__(self,app):
        self.app=app
        self.win=tk.Toplevel(app.root)
        self.win.title('Multitrack sound timeline')
        fit_window(self.win,970,650,420,350)
        self.history=DesignHistory()
        register_structured_undo(self.win,self.undo)
        self.path=None
        self.data={'tracks':[],'markers':[],'duck_music':True}
        self.base=Path.cwd()
        self.status=tk.StringVar(value='Add narration, music, effects or room tone.')
        bar=line(self.win)
        for text,cmd in [('Open session',self.open),('Save template',self.save),('Add clips',self.add),('Edit clip',self.edit),
                         ('Remove',self.remove),('Add marker',self.marker),('Find cut points',self.cut_points),('Mix options',self.options),('Undo',lambda:self.undo(-1)),('Redo',lambda:self.undo(1))]:
            button(bar,text,cmd)
        self.tree=ttk.Treeview(self.win,columns=('role','start','duration','gain','name'),show='headings',selectmode='browse',height=8)
        for key,size in [('role',100),('start',72),('duration',85),('gain',65),('name',260)]:
            self.tree.heading(key,text=key.title())
            self.tree.column(key,width=size)
        self.tree.pack(fill='x',padx=6)
        self.tree.bind('<Double-Button-1>',lambda e:guarded(self.win,self.edit)())
        self.canvas=tk.Canvas(self.win,bg='#152536',takefocus=True)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.refresh_timeline())
        self.canvas.bind('<Button-1>',self.select_clip)
        self.canvas.bind('<ButtonRelease-1>',guarded(self.win,self.move_clip))
        self.drag=None
        bar=line(self.win)
        for text,cmd in [('Preview first 10 s',lambda:self.render(True)),('Export mix',self.render),('Export stems',self.stems),
                         ('Preview clip',self.preview_selected),('Waveform editor',lambda:WaveEditor(self.app))]:
            button(bar,text,cmd)
        ttk.Label(self.win,textvariable=self.status).pack(fill='x')
        self.refresh()

    def undo(self,delta):
        self.data=self.history.move(delta)
        self.refresh()

    def refresh(self):
        self.history.remember(self.data)
        self.tree.delete(*self.tree.get_children())
        for i,r in enumerate(self.data['tracks']):
            self.tree.insert('','end',iid=str(i),values=(r.get('role','effects'),r.get('start',0),r.get('duration','Full clip'),r.get('gain',1),Path(r['file']).name))
        self.refresh_timeline()

    def refresh_timeline(self):
        from .sound_studio import ROLES
        self.canvas.delete('all')
        w=max(280,self.canvas.winfo_width())
        h=max(100,self.canvas.winfo_height())
        total=max((r.get('start',0)+r.get('duration',r.get('source_seconds',2)) for r in self.data['tracks']),default=10)
        self.unit=(w-105)/max(1,total)
        self.rects=[]
        for i,role in enumerate(ROLES):
            y=12+i*h/5
            self.canvas.create_text(5,y+10,anchor='w',text=role,fill='white')
        for i,r in enumerate(self.data['tracks']):
            y=12+ROLES.index(r.get('role','effects'))*h/5
            x=98+self.unit*r.get('start',0)
            end=x+self.unit*r.get('duration',r.get('source_seconds',2))
            self.canvas.create_rectangle(x,y,end,y+26,fill='#227681',outline='#e2f3ef')
            self.canvas.create_text(x+4,y+13,anchor='w',text=Path(r['file']).stem[:20],fill='white')
            self.rects.append((x,y,end,y+26,i))
        for m in self.data.get('markers',[]):
            x=98+m['time']*self.unit
            self.canvas.create_line(x,0,x,h,fill='#efd080',dash=(3,2))
            self.canvas.create_text(x+2,h-12,anchor='w',text=m.get('label',''),fill='#efd080')

    def select_clip(self,e):
        self.drag=None
        for x,y,xx,yy,i in reversed(self.rects):
            if x<=e.x<=xx and y<=e.y<=yy:
                self.tree.selection_set(str(i))
                self.drag=(i,e.x)
                break
    def move_clip(self,e):
        if self.drag:
            i,x=self.drag
            row=self.data['tracks'][i]
            row['start']=max(0,round(row.get('start',0)+(e.x-x)/self.unit,3))
            self.drag=None
            self.refresh()

    def selected(self):
        if not self.tree.selection():
            raise ValueError('Select an audio clip')
        return int(self.tree.selection()[0])

    def open(self):
        name=filedialog.askopenfilename(parent=self.win,filetypes=[('Sound session','*.json')])
        if not name:
            return
        from .sound_studio import read_session
        data,_=read_session(name)
        self.history=DesignHistory()
        self.path=Path(name).resolve()
        self.base=self.path.parent
        self.data=data
        self.refresh()
    def save(self):
        name=filedialog.asksaveasfilename(parent=self.win,defaultextension='.json',initialfile=self.path.name if self.path else 'mix.json')
        if not name:
            return
        p=Path(name).resolve()
        for row in self.data['tracks']:
            for key in ('file','impulse'):
                if row.get(key):
                    file=(self.base/row[key]).resolve()
                    try:
                        row[key]=os.path.relpath(file,p.parent)
                    except ValueError:
                        row[key]=str(file)
        _atomic_json(p,self.data)
        self.history=DesignHistory() if p.parent!=self.base else self.history
        self.path=p
        self.base=p.parent
        self.history.remember(self.data)
        return p

    def add(self):
        from .video import audio_duration
        names=filedialog.askopenfilenames(parent=self.win,title='Select local recordings or sound effects')
        if not names:
            return
        from .gui_forms import edit_settings
        def apply(d):
            added=[{'file':str(Path(n).resolve()),'role':d['role'],'start':0.0,'gain':1.0,
                    'source_seconds':audio_duration(n),'license':'','credit':''} for n in names]
            self.data['tracks'].extend(added)
            self.refresh()
        edit_settings(self.win,'Add sound clips',{'role':'narration'},apply)
    def edit(self):
        i=self.selected()
        def apply(row):
            self.data['tracks'][i]=row
            self.refresh()
        row=dict(self.data['tracks'][i])
        defaults={'start':0.0,'gain':1.0,'offset':0.0,'pan':0.0,'fade_in':0.0,'fade_out':0.0,'loop':False,'loop_crossfade':0.0,'muted':False,'space':'dry','curve':[],'credit':'','license':''}
        if 'duration' not in row:
            from .video import audio_duration
            src=(self.base/row['file']).resolve()
            row['duration']=max(.0001,row.get('source_seconds') or audio_duration(src))-row.get('offset',0)
        for k,v in defaults.items():row.setdefault(k,v)
        edit_json(self.win,'Clip, gain, fades, automation curve and acoustic space',row,apply)
    def remove(self):
        self.data['tracks'].pop(self.selected())
        self.refresh()
    def marker(self):
        def apply(d):
            self.data.setdefault('markers',[]).append(d)
            self.refresh()
        edit_json(self.win,'Add sound marker',{'time':0.0,'label':'Marker'},apply)
    def options(self):
        data={k:v for k,v in self.data.items() if k!='tracks'}
        edit_json(self.win,'Mix preferences and markers',data,lambda d:(self.data.update(d),self.refresh()))
    def _with_session(self,fn):
        import copy
        data=copy.deepcopy(self.data)
        for r in data['tracks']:
            for k in ('file','impulse'):
                if r.get(k):
                    r[k]=str((self.base/r[k]).resolve())
        def job():
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'session.json'
                _atomic_json(p,data)
                return fn(p,Path(tmp))
        async_job(self.win,self.status,job)
    def render(self,preview=False):
        from .sound_studio import mix_session
        out=None if preview else filedialog.asksaveasfilename(parent=self.win,defaultextension='.wav')
        if not preview and not out:
            return
        def job(p,tmp):
            dest=mix_session(p,tmp/'preview.wav' if preview else out,preview=10 if preview else 0)
            if preview:
                from .engines.builtin import play_wav
                play_wav(dest)
        self._with_session(job)
    def cut_points(self):
        from .sound_studio import transition_markers
        row=self.data['tracks'][self.selected()]
        def apply(markers):
            offset=row.get('offset',0)
            start=row.get('start',0)
            duration=row.get('duration',float('inf'))
            self.data.setdefault('markers',[]).extend(dict(m,time=m['time']-offset+start) for m in markers if 0<=m['time']-offset<=duration)
            self.refresh()
        async_job(self.win,self.status,lambda:transition_markers(self.base/row['file']),apply)

    def preview_selected(self):
        from .sound_studio import mix_session
        from .engines.builtin import play_wav
        import copy
        r=copy.deepcopy(self.data['tracks'][self.selected()])
        r.update(start=0,muted=False)
        for k in ('file','impulse'):
            if r.get(k):
                r[k]=str((self.base/r[k]).resolve())
        def job():
            with tempfile.TemporaryDirectory() as tmp:
                src=Path(tmp)/'clip.json'
                _atomic_json(src,{'tracks':[r]})
                play_wav(mix_session(src,Path(tmp)/'preview.wav',preview=8))
        async_job(self.win,self.status,job)

    def stems(self):
        from .sound_studio import export_stems
        folder=filedialog.askdirectory(parent=self.win)
        if folder:
            self._with_session(lambda p,_:export_stems(p,folder))


class WaveEditor:
    def __init__(self,app):
        self.win=tk.Toplevel(app.root)
        self.win.title('Waveform and passage editor')
        fit_window(self.win,950,560,380,310)
        self.path=None
        self.result=None
        self.anchor=None
        self.span=[0,0]
        self.status=tk.StringVar(value='Open audio, then drag to select a passage or enter its times.')
        bar=line(self.win)
        button(bar,'Open audio',self.open)
        button(bar,'Spectrogram',self.spectrum)
        button(bar,'Enter selection',self.select_times)
        button(bar,'Play selection',lambda:self.extract(True))
        button(bar,'Save selection',self.extract)
        self.canvas=tk.Canvas(self.win,bg='#101f2b',takefocus=True)
        self.canvas.pack(fill='both',expand=True,padx=4)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.press)
        self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',self.drag)
        ttk.Label(self.win,textvariable=self.status).pack(fill='x')
    def open(self):
        path=filedialog.askopenfilename(parent=self.win); 
        if not path:
            return
        from .audio_analysis import waveform
        def done(r):
            self.path=Path(path)
            self.result=r
            self.span=[0,r['seconds']]
            self.draw()
        async_job(self.win,self.status,lambda:waveform(path,1200),done)
    def draw(self):
        if not self.result:
            return
        w=max(1,self.canvas.winfo_width())
        h=max(40,self.canvas.winfo_height())
        d=self.result['seconds']
        self.canvas.delete('all')
        a,b=self.span
        self.canvas.create_rectangle(w*a/d,0,w*b/d,h,fill='#284b63',outline='')
        coords=[]
        for t,rms,peak in self.result['points']:
            x=t/d*w
            coords.extend((x,h/2-peak*h*.46,x,h/2+peak*h*.46))
        if len(coords)>=4:
            self.canvas.create_line(*coords,fill='#6cd7bf')
        self.status.set(f'{self.path.name} · selection {a:.3f} to {b:.3f} seconds · analyzed on {self.result["analysis_device"]}')
    def second(self,x):
        return round(max(0,min(1,x/max(1,self.canvas.winfo_width())))*self.result['seconds'],3)
    def press(self,e):
        if self.result:
            self.anchor=self.second(e.x)
    def drag(self,e):
        if self.anchor is not None:
            self.span=sorted([self.anchor,self.second(e.x)])
            self.draw()
    def select_times(self):
        if not self.result:
            raise ValueError('Open audio first')
        a=simpledialog.askfloat('Start','Seconds',minvalue=0,maxvalue=self.result['seconds'],parent=self.win)
        if a is None:
            return
        b=simpledialog.askfloat('End','Seconds',minvalue=a,maxvalue=self.result['seconds'],parent=self.win)
        if b is not None:
            self.span=[a,b]
            self.draw()
    def extract(self,preview=False):
        if not self.path or self.span[1]<=self.span[0]:
            raise ValueError('Select a nonempty audio passage')
        from .fftools import find_binary
        from .video import _run
        from .security_tools import staged_file
        output=None if preview else filedialog.asksaveasfilename(parent=self.win,defaultextension='.wav')
        if not preview and not output:
            return
        if output and Path(output).resolve()==self.path.resolve():
            raise ValueError('Save the selected audio to a separate file')
        source=self.path
        a,b=self.span
        def job():
            with tempfile.TemporaryDirectory() as tmp:
                target=Path(tmp)/'preview.wav' if preview else Path(output)
                with staged_file(target) as stage:
                    _run([find_binary('ffmpeg'),'-y','-loglevel','error','-ss',str(a),'-i',str(source),'-t',str(b-a),'-vn',str(stage)])
                if preview:
                    from .engines.builtin import play_wav
                    play_wav(target)
        async_job(self.win,self.status,job)
    def spectrum(self):
        if not self.path:
            raise ValueError('Open audio first')
        from .sound_studio import audio_picture
        from PIL import Image,ImageTk
        def job():
            with tempfile.TemporaryDirectory() as td:
                png=audio_picture(self.path,Path(td)/'spectrum.png','spectrogram',960,400)
                with Image.open(png) as im:
                    return im.copy()
        def done(im):
            win=tk.Toplevel(self.win)
            win.title('Audio spectrogram')
            photo=ImageTk.PhotoImage(im,master=win)
            label=ttk.Label(win,image=photo)
            label.image=photo
            label.pack()
        async_job(self.win,self.status,job,done)
