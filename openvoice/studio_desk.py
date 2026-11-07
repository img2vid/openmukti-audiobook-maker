"""Production menus and workspace preferences for the existing Openmukti desktop."""
from __future__ import annotations
import json
import os
import queue
import re
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog

from . import desktop_prefs
from .studio_windows import ProjectTabs,async_job,button,line,edit_json,guarded,show_text
from .media_windows import CanvasDesigner,SoundDesk,WaveEditor
from .windowing import fit_window

COMMANDS=('Project tabs','Cover designer','Sound timeline','Waveform editor','Subtitle editor','Read along','Stop playback','Open document','Export audio','Preferences','Help')
BN={'File':'ফাইল','Edit':'সম্পাদনা','View':'দৃশ্য','Tools':'সরঞ্জাম','Voices':'কণ্ঠস্বর','Help':'সাহায্য','Studio':'স্টুডিও',
    'Project tabs':'প্রকল্পের ট্যাব','Cover designer':'প্রচ্ছদ নকশা','Sound timeline':'অডিও টাইমলাইন','Waveform editor':'তরঙ্গরূপ সম্পাদক',
    'Subtitle editor':'সাবটাইটেল সম্পাদক','Read along':'শুনে পড়ুন','Stop playback':'প্লেব্যাক বন্ধ','Speak':'বলুন','Stop':'বন্ধ করুন',
    'Open document':'নথি খুলুন','Save text':'লেখা সংরক্ষণ','Export audio':'অডিও রপ্তানি','Preferences':'পছন্দসমূহ','Video':'ভিডিও',
    'Open':'খুলুন','Save':'সংরক্ষণ','Close':'বন্ধ','Undo':'পূর্বাবস্থা','Redo':'পুনরায় করুন','Cut':'কাট','Copy':'কপি','Paste':'পেস্ট',
    'Start setup':'প্রাথমিক সেটআপ','Guided tutorial':'নির্দেশিকা','Developer center':'ডেভেলপার সহায়তা','Import and OCR':'আমদানি ও ওসিআর',
    'Production':'প্রযোজনা','Current project':'বর্তমান প্রকল্প','Run tests':'পরীক্ষা চালান','Save preferences':'পছন্দ সংরক্ষণ'}
ES={'File':'Archivo','Edit':'Editar','View':'Vista','Tools':'Herramientas','Voices':'Voces','Help':'Ayuda','Studio':'Estudio',
    'Project tabs':'Pestañas de proyecto','Cover designer':'Diseñar portada','Sound timeline':'Pistas de audio','Waveform editor':'Editor de onda',
    'Subtitle editor':'Editor de subtítulos','Read along':'Lectura sincronizada','Stop playback':'Detener reproducción','Speak':'Hablar','Stop':'Detener',
    'Open document':'Abrir documento','Save text':'Guardar texto','Export audio':'Exportar audio','Preferences':'Preferencias','Video':'Vídeo',
    'Open':'Abrir','Save':'Guardar','Close':'Cerrar','Undo':'Deshacer','Redo':'Rehacer','Cut':'Cortar','Copy':'Copiar','Paste':'Pegar',
    'Start setup':'Configuración inicial','Guided tutorial':'Tutorial guiado','Developer center':'Centro de desarrollo','Import and OCR':'Importación y OCR',
    'Production':'Producción','Current project':'Proyecto actual','Run tests':'Ejecutar pruebas','Save preferences':'Guardar preferencias'}


class DesktopStudio:
    def __init__(self,app,menu):
        self.app=app
        self.root=app.root
        self.menu=menu
        self.status=app.status_var
        self.prefs=desktop_prefs.read()
        self.playing=None
        self.bindings={}
        self.actions=dict(zip(COMMANDS,(lambda:ProjectTabs(app),lambda:CanvasDesigner(app),lambda:SoundDesk(app),lambda:WaveEditor(app),
                                       self.cues,self.read_along,self.stop,app.open_file,app.export,self.preferences,self.help)))
        m=tk.Menu(menu,tearoff=False)
        menu.add_cascade(label='Studio',menu=m)
        for label in COMMANDS[:7]:
            m.add_command(label=label,command=guarded(self.root,self.actions[label]))
        imports=tk.Menu(m,tearoff=False)
        m.add_cascade(label='Import and OCR',menu=imports)
        for label,action in [('Import several documents',self.import_many),('Import web article',self.article),('Watch document folder',self.inbox),
                             ('Aligned OCR page review',self.ocr),('Recover project assets',self.recovery)]:
            imports.add_command(label=label,command=guarded(self.root,action))
        production=tk.Menu(m,tearoff=False)
        m.add_cascade(label='Production',menu=production)
        for label,action in [('Cast and dialogue timeline',self.cast),('Caption design',self.caption_design),('Split manuscript and preview',self.split_preview),('Preview chapter openings',lambda:self.read_along(chapters=True)),
                             ('Speech directions and emotions',self.emphasis_editor),('Narration planner',self.score),('Voice auditions',self.auditions),('Production queue',self.jobs),
                             ('Reusable audio folder',self.cache),('Install accelerator support from files',self.wheels),
                             ('Local voice command',self.microphone),('Export diagnostic bundle',self.diagnostics),('Check the app',self.tests)]:
            production.add_command(label=label,command=guarded(self.root,action))
        for label,action in [('Preferences',self.preferences),('Start setup',self.setup),('Guided tutorial',self.tutorial),('User guide',self.help)]:
            m.add_command(label=label,command=guarded(self.root,action))
        m.add_command(label='Accessible manuscript and playback workspace',command=guarded(self.root,self.accessible))
        from .gui_utilities import utility_actions
        self.utilities=utility_actions(app,self)
        extras=tk.Menu(m,tearoff=False)
        m.add_cascade(label='Additional production tools',menu=extras)
        for title,description,category,action in self.utilities:
            extras.add_command(label=title,command=guarded(self.root,action))
        m.add_command(label='Focus writing mode',command=guarded(self.root,self.focus))
        from .studio_windows import DesignHistory
        self.preference_history=DesignHistory()
        self.preference_history.remember(dict(self.prefs))
        self.servers=[]
        self.scale_timer=None
        self.root.bind('<Configure>',self.display_changed,add='+')
        self.shortbar=ttk.Frame(self.root)
        from .interface_language import WindowTranslations
        self.translator=WindowTranslations(self.root)
        self.apply_prefs()
        self.drop()
        self.welcome()
        self.home_window=None
        menu.insert_command(0,label='Start creating',command=guarded(self.root,self.home))
        self.root.bind('<Control-k>',lambda e:self.home(),add='+')
        self.root.bind('<Control-Shift-P>',lambda e:self.home(),add='+')
        # Text widgets otherwise consume Ctrl+K as delete-to-end-of-line.
        self.app.editor.bind('<Control-k>',lambda e:(self.home(),'break')[1],add='+')
        if self.prefs.get('show_home_on_start',True):
            self.root.after(450,self.home)
        self.root.bind_all('<F1>',lambda e:self.context_help(e.widget),add='+')

    def home(self):
        if self.home_window is not None and self.home_window.winfo_exists():
            self.home_window.lift()
            return self.home_window
        from .gui_workflows import TaskHub
        self.home_window=TaskHub(self).win
        return self.home_window

    def focus(self):
        panel=self.app.studio_settings_side
        if panel.winfo_manager()=='grid':
            panel.grid_remove()
        else:
            panel.grid()
        self.app.editor.focus_set()

    def display_changed(self,event):
        if event.widget is not self.root:return
        if self.scale_timer:self.root.after_cancel(self.scale_timer)
        def update():
            from .windowing import apply_display_scale
            self.scale_timer=None
            apply_display_scale(self.root,self.prefs.get('interface_scale',100))
        self.scale_timer=self.root.after(180,update)

    def accessible(self):
        import webbrowser
        from .accessible_workspace import start_workspace
        from .engines import get_engine,SpeechSettings
        from .service import JobOptions
        v=self.app
        settings=SpeechSettings(voice=v.voice_var.get(),model=v.model_var.get(),rate=v.rate_var.get(),pitch=v.pitch_var.get(),volume=v.volume_var.get(),language=v.tts_language_var.get())
        if not v._confirm_piper_downloads(v.engine_var.get(),settings,script=v._get_text(),parent=self.root):
            return
        engine_name=v.engine_var.get()
        def engine():return get_engine(engine_name,settings.model,settings.voice)
        from .access_bridge import ControlBridge
        bridge=ControlBridge(self.root)
        server,url=start_workspace(v._get_text(),engine,settings,JobOptions(),bridge=bridge,locale=self.prefs.get('language','en'))
        self.servers.append(server)
        w=tk.Toplevel(self.root)
        w.title('Accessible workspace is running')
        ttk.Label(w,text='Open this private, local address to edit a manuscript and use accessible playback controls.',wraplength=480).pack(padx=10,pady=8)
        entry=ttk.Entry(w,width=64)
        entry.insert(0,url)
        entry.pack(padx=6)
        def stop():
            bridge.close()
            server.shutdown()
            server.server_close()
            if server in self.servers:
                self.servers.remove(server)
            w.destroy()
        button(line(w),'Stop workspace',stop)
        w.protocol('WM_DELETE_WINDOW',stop)
        webbrowser.open(url)

    def welcome(self):
        if self.prefs.get('welcome_seen'):
            return
        frame=ttk.Frame(self.root)
        frame.pack(side='bottom',fill='x')
        ttk.Label(frame,text='New to Openmukti? Choose your voice setup and production defaults.').pack(side='left')
        def dismiss():
            desktop_prefs.write(welcome_seen=True)
            frame.destroy()
        button(frame,'Start setup',lambda:(dismiss(),self.setup()))
        button(frame,'Dismiss',dismiss)

    def history(self,direction):
        widget=self.root.focus_get()
        if widget:
            window=widget.winfo_toplevel()
            if hasattr(window,'studio_history_change'):
                try:window.studio_history_change(direction)
                except ValueError:window.bell()
                return
            if widget.winfo_class()=='Text':
                widget.event_generate('<<Undo>>' if direction<0 else '<<Redo>>')
                return
        try:
            data=self.preference_history.move(direction)
            self.prefs=desktop_prefs.replace_preferences(data)
            self.apply_prefs()
        except ValueError:
            self.app.editor.event_generate('<<Undo>>' if direction<0 else '<<Redo>>')

    def drop(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.app.editor.drop_target_register(DND_FILES)
            def receive(evt):
                names=self.root.tk.splitlist(evt.data)
                self.import_many(names)
                return 'copy'
            self.app.editor.dnd_bind('<<Drop>>',guarded(self.root,receive))
        except (ImportError,AttributeError,tk.TclError):
            pass

    def import_many(self,names=None):
        from .import_studio import batch_read
        names=names or filedialog.askopenfilenames(parent=self.root,title='Add documents to manuscript')
        if not names:
            return
        preset=self.prefs.get('import_preset',{})
        def add(text):
            self.app.editor.insert('end-1c','\n\n'+text if self.app._get_text().strip() else text)
            self.app.update_stats()
        async_job(self.root,self.status,lambda:batch_read(names,preset),add)

    def article(self):
        from .import_studio import read_article
        url=simpledialog.askstring('Web article','Enter the URL of an article you are permitted to use.',parent=self.root)
        if url:
            async_job(self.root,self.status,lambda:read_article(url),lambda text:(self.app.editor.insert('insert',text),self.app.update_stats()))

    def inbox(self):
        from .import_studio import FolderInbox
        folder=filedialog.askdirectory(parent=self.root,title='Watch folder for stable new documents')
        if not folder:
            return
        watch=FolderInbox(folder)
        win=tk.Toplevel(self.root)
        win.title('Document inbox')
        fit_window(win,650,420,360,300)
        ttk.Label(win,text=folder,wraplength=550).pack(fill='x')
        lb=tk.Listbox(win,selectmode='extended')
        lb.pack(fill='both',expand=True)
        def refresh():
            if not win.winfo_exists():
                return
            try:
                for p in watch.poll():
                    lb.insert('end',str(p))
            except OSError as exc:
                self.status.set(str(exc))
            win.after(2000,refresh)
        def add():
            ids=list(lb.curselection())
            if ids:
                self.import_many([lb.get(i) for i in ids])
        button(line(win),'Import selected',add)
        refresh()

    def ocr(self):
        from .page_layout import write_review
        source=filedialog.askopenfilename(parent=self.root,title='Select a scanned page image')
        if not source:
            return
        out=filedialog.asksaveasfilename(parent=self.root,title='Save searchable review page',defaultextension='.html')
        if out:
            async_job(self.root,self.status,lambda:write_review(source,out),lambda p:self.status.set('Saved review '+str(p)))

    def recovery(self):
        from .project_tools import recover
        source=filedialog.askopenfilename(parent=self.root,title='Project with missing or damaged files')
        if not source:
            return
        folder=filedialog.askdirectory(parent=self.root,title='Search for relocated resources')
        if not folder:
            return
        output=filedialog.asksaveasfilename(parent=self.root,title='Recovered project',defaultextension='.oamproj')
        if output:
            async_job(self.root,self.status,lambda:recover(source,folder,output),lambda rows:self.status.set(f'Recovered {len(rows)} files'))

    def cast(self):
        from .editorial_studio import script_report
        text=self.app._get_text()
        names=[p.name for p in self.app.voice_project.profiles]
        async_job(self.root,self.status,lambda:script_report(text,names),lambda r:self.app._show_json_report('Cast and dialogue timeline',r))
    def emphasis_editor(self):
        return self.score()

    def score(self):
        from .gui_workflows import NarrationDesk
        return NarrationDesk(self.app)

    def auditions(self):
        from .gui_workflows import auditions
        return auditions(self.app)

    def caption_design(self):
        from .gui_workflows import caption_designer
        return caption_designer(self)

    def split_preview(self):
        from PIL import Image,ImageTk
        from .audio_analysis import waveform
        from .storyboard import Storyboard
        w=tk.Toplevel(self.root)
        w.title('Manuscript, audio and video preview')
        fit_window(w,1060,640,420,340)
        pane=ttk.Panedwindow(w,orient='horizontal')
        pane.pack(expand=True,fill='both')
        box=tk.Text(pane,undo=True,wrap='word')
        text=self.app._get_text()
        box.insert('1.0',text)
        pane.add(box,weight=1)
        frame=ttk.Frame(pane)
        pane.add(frame,weight=1)
        preview=tk.Canvas(frame,bg='#142839',takefocus=True)
        preview.pack(fill='both',expand=True)
        state={'audio':None,'board':None,'photo':None}
        value=tk.DoubleVar(value=0)
        stat=tk.StringVar(value='Load a soundtrack or storyboard. The slider scrubs both views.')
        def display(*_):
            width=max(64,preview.winfo_width())
            height=max(64,preview.winfo_height())
            part=value.get()/100
            preview.delete('all')
            sig=state['audio']
            d=sig['seconds'] if sig else 10
            if state['board']:
                im=state['board'].preview(part*d,d,size=(width,max(32,int(height*.65))))
                state['photo']=ImageTk.PhotoImage(im,master=w)
                preview.create_image(0,0,anchor='nw',image=state['photo'])
            if sig:
                for t,r,p in sig['points']:
                    x=width*t/d
                    preview.create_line(x,height*(.82-.14*p),x,height*(.82+.14*p),fill='#8de4c1')
            preview.create_line(part*width,0,part*width,height,fill='#ffdf88')
        def audio():
            name=filedialog.askopenfilename(parent=w)
            if name:
                async_job(w,stat,lambda:waveform(name,600),lambda s:(state.update(audio=s),display()))
        def board():
            name=filedialog.askopenfilename(parent=w,filetypes=[('Storyboard','*.json')])
            if name:
                state['board']=Storyboard.load(name)
                display()
        def apply():
            if self.app._get_text()!=text:
                raise ValueError('Main manuscript changed. Open a fresh split view before applying edits.')
            self.app._replace_text(box.get('1.0','end-1c'))
            w.destroy()
        bar=line(w)
        button(bar,'Open audio',audio)
        button(bar,'Open design',board)
        button(bar,'Apply manuscript edits',apply)
        ttk.Scale(frame,from_=0,to=100,variable=value,command=display).pack(fill='x')
        preview.bind('<Configure>',display)
        ttk.Label(w,textvariable=stat).pack(fill='x')

    def cues(self):
        from .subtitle_tools import export_cues
        from .animated_video import load_cues
        from dataclasses import asdict
        win=tk.Toplevel(self.root)
        win.title('Subtitle timing editor')
        fit_window(win,820,550,360,300)
        rows=[]
        listing=tk.Listbox(win,exportselection=False)
        listing.pack(fill='both',expand=True)
        def update():
            listing.delete(0,'end')
            for cue in rows:
                listing.insert('end',f'{cue["start"]:.3f} → {cue["end"]:.3f}   {cue["text"]}')
        def load():
            path=filedialog.askopenfilename(parent=win,filetypes=[('Timing files','*.srt *.vtt *.json')])
            if path:
                rows[:]=[asdict(c) for c in load_cues(path,2_592_000)]
                update()
        def edit(new=False):
            if not new and not listing.curselection():
                return
            i=len(rows) if new else listing.curselection()[0]
            last=rows[-1]['end'] if rows else 0
            start,end,text=(last,last+2,'') if new else (rows[i]['start'],rows[i]['end'],rows[i]['text'])
            def change(d):
                if not isinstance(d.get('text'),str) or not 0<=float(d['start'])<float(d['end']):
                    raise ValueError('Enter valid times and text')
                d.update(start=float(d['start']),end=float(d['end']))
                if new:
                    rows.append(d)
                else:
                    rows[i]=d
                update()
            edit_json(win,'Cue start, end and text',dict(start=start,end=end,text=text),change)
        def save():
            path=filedialog.asksaveasfilename(parent=win,defaultextension='.srt',filetypes=[('SubRip','*.srt'),('WebVTT','*.vtt'),('Saved timing data','*.json')])
            if path:
                export_cues(rows,path)
                self.app.video_options['timing_file']=path
        bar=line(win)
        button(bar,'Open',load)
        button(bar,'Add cue',lambda:edit(True))
        button(bar,'Edit selected',edit)
        button(bar,'Remove',lambda:(rows.pop(listing.curselection()[0]),update()) if listing.curselection() else None)
        button(bar,'Save and use timings',save)

    def read_along(self,chapters=False):
        from .book_structure import detect_chapters
        from .engines import get_engine,RunControl,SpeechSettings
        from .engines.builtin import play_wav
        from .piper_models import speaker_id_from_label
        from .service import JobOptions,render_text
        from .engines.base import Cancelled
        if self.playing:
            raise ValueError('Stop current playback before starting another reading')
        text=self.app._get_text()
        box=self.app.editor
        matches=[(m.start(),m.end(),m[0]) for m in re.finditer(r'[^.!?。！？\n]+(?:[.!?。！？]+|(?=\n|$))',text) if m[0].strip()]
        if chapters:
            sections=detect_chapters(text)
            matches=[]
            pos=0
            for s in sections:
                passage=' '.join(s.text.split()[:45])
                first=s.text[:max(1,len(s.text)//50)]
                idx=text.find(first,pos)
                if idx>=0 and passage:
                    matches.append((idx,idx+min(len(s.text),len(passage)),passage))
                    pos=idx+len(s.text)
        if not matches:
            raise ValueError('Enter narration text first')
        eng=self.app.engine_var.get()
        settings=SpeechSettings(voice=self.app.voice_var.get(),model=self.app.model_var.get(),language=self.app.tts_language_var.get(),rate=self.app.rate_var.get(),pitch=self.app.pitch_var.get(),volume=self.app.volume_var.get(),speaker_id=speaker_id_from_label(self.app.speaker_var.get()))
        if not self.app._confirm_piper_downloads(eng,settings,script=text,parent=self.root):
            return
        backend=get_engine(eng,settings.model,settings.voice)
        control=RunControl()
        self.playing=control
        events=queue.Queue()
        box.tag_configure('read_along',underline=True,background='#f7d176',foreground='#101820')
        def job():
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    path=Path(tmp)/'line.wav'
                    for a,b,passage in matches:
                        control.check()
                        render_text(passage,path,backend,settings,JobOptions(),control)
                        events.put(('mark',(a,b)))
                        play_wav(path,control)
            except Cancelled:
                pass
            except Exception as exc:
                events.put(('error',str(exc)))
            finally:
                events.put(('done',None))
        def poll():
            while True:
                try:
                    kind,value=events.get_nowait()
                except queue.Empty:
                    break
                if kind=='mark':
                    if box.get('1.0','end-1c')!=text:
                        control.stop()
                        continue
                    a,b=value
                    box.tag_remove('read_along','1.0','end')
                    box.tag_add('read_along',f'1.0+{a}c',f'1.0+{b}c')
                    box.see(f'1.0+{a}c')
                elif kind=='error':
                    self.status.set(value)
                else:
                    box.tag_remove('read_along','1.0','end')
                    self.playing=None
                    return
            self.root.after(40,poll)
        threading.Thread(target=job,daemon=True).start()
        poll()
    def stop(self):
        if self.playing:
            self.playing.stop()
        else:
            self.app.stop()

    def jobs(self):
        import datetime
        from .job_queue import enqueue,jobs,worker,modify
        from .gui_workflows import friendly_job,queue_job
        from .neural_runtime import cache_home
        db=cache_home().parent/'production-queue.sqlite3'
        w=tk.Toplevel(self.root)
        w.title('Production queue')
        fit_window(w,820,500,360,300)
        box=tk.Listbox(w,exportselection=False)
        box.pack(fill='both',expand=True)
        data=[]
        stat=tk.StringVar(value='Pending jobs run in priority order when a worker is active.')
        def refresh():
            data[:]=jobs(db)
            known=box.curselection()
            box.delete(0,'end')
            for r in data:
                box.insert('end',f'#{r["id"]}  {r["state"]}  priority {r["priority"]}  {friendly_job(r)}')
            if known and known[0]<len(data):
                box.selection_set(known[0])
        def add():
            def save(arguments,priority,at):
                enqueue(db,arguments,priority,at)
                refresh()
            queue_job(w,self.app,save)
        def action(name):
            if box.curselection():
                modify(db,data[box.curselection()[0]]['id'],name)
                refresh()
        bar=line(w)
        button(bar,'Add render',add)
        button(bar,'Run ready jobs',lambda:async_job(w,stat,lambda:worker(db),lambda v:refresh()))
        button(bar,'Refresh',refresh)
        button(bar,'Cancel selected',lambda:action('cancel'))
        button(bar,'Retry selected',lambda:action('retry'))
        ttk.Label(w,textvariable=stat).pack(fill='x')
        refresh()

    def cache(self):
        name=filedialog.askdirectory(parent=self.root,title='Persistent speech chunk cache')
        if name:
            desktop_prefs.write(render_cache=name)
            os.environ['OPENMUKTI_RENDER_CACHE']=name
            self.status.set('Chunk reuse enabled')
    def wheels(self):
        from .gui_forms import FormEditor,Field,choices
        from .platform_tools import gpu_wheels
        def apply(d):
            names=filedialog.askopenfilenames(parent=self.root,title='Choose local accelerator packages',filetypes=[('Accelerator packages','*.whl')])
            if not names:return
            folder=Path(names[0]).parent
            plan=gpu_wheels(d['engine'],folder,names)
            if messagebox.askyesno('Install accelerator support','Install the selected local packages?\n\n'+'\n'.join(Path(n).name for n in names),parent=self.root):
                async_job(self.root,self.status,lambda:gpu_wheels(d['engine'],folder,names,True))
        return FormEditor(self.root,'Local accelerator support',{'engine':'application'},apply,
            fields={'engine':Field('Install for',choices=choices('application','kitten','pocket','kokoro','coqui'))},apply_label='Choose packages')

    def microphone(self):
        from .integrations import microphone_command
        folder=filedialog.askdirectory(parent=self.root,title='Choose a local Vosk model to listen for one command')
        if folder:
            allowed={'open document':'Open document','stop playback':'Stop playback','read along':'Read along','help':'Help','preferences':'Preferences'}
            async_job(self.root,self.status,lambda:microphone_command(folder,allowed),lambda cmd:self.actions[allowed[cmd]]() if cmd else self.status.set('No matching voice command'))
    def diagnostics(self):
        from .inspection import support_bundle
        path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.zip')
        if path:
            async_job(self.root,self.status,lambda:support_bundle(path))
    def tests(self):
        from .gui_forms import FormEditor,Field,choices
        from .studio_selftest import selftest
        def apply(d):
            async_job(self.root,self.status,lambda:selftest(d['suite']),lambda r:self.app._show_json_report('App check results',r))
        return FormEditor(self.root,'Check the app',{'suite':'render'},apply,
            fields={'suite':Field('What would you like to check?',choices=choices('render','accessibility','languages','portable','source'))},apply_label='Run check')

    def preferences(self):
        cfg={**{'language':'en','translate_missing':False,'high_contrast':False,'touch':False,'left_handed':False,'reduced_motion':False,'font':self.app.ui_font,
                'font_size':12,'interface_scale':100,'toolbar':['Project tabs','Cover designer','Sound timeline'],'shortcuts':{'<F6>':'Read along'},
                'permissions':{'network':True,'microphone':True,'external_tools':True,'native_plugins':True,'folders':[]},
                'import_preset':{'footnotes':'inline','tables':'describe','headings':True},'gpu_mode':'auto',
                'cpu_profile':'balanced','audio_format':'wav','render_cache':'','show_home_on_start':True,'translation_file':''},
             **desktop_prefs.read()}
        def apply(d):
            if d['language'] not in ('en','bn','es') and not d.get('translation_file') and not d.get('translate_missing'):
                raise ValueError('Choose en, bn, es or supply a translation_file')
            if not 7<=int(d['font_size'])<=48:
                raise ValueError('Choose an editor font size from 7 to 48')
            if any(v not in self.actions for v in d['toolbar']+list(d['shortcuts'].values())):
                raise ValueError('Unknown toolbar or shortcut action')
            if d.get('translate_missing') and d.get('language')!='en':
                from .interface_language import LocalTranslator
                LocalTranslator(d['language'])
            self.prefs=desktop_prefs.write(**d)
            self.preference_history.remember(self.prefs)
            self.apply_prefs()
            from .hardware import gpu_preference
            enabled=d.get('gpu_mode')!='cpu'
            gpu_preference(enabled)
            self.app.gpu_var.set(enabled)
            from .hardware import apply_cpu_profile
            apply_cpu_profile(d.get('cpu_profile','balanced'))
            self.app.cpu_profile_var.set(d.get('cpu_profile','balanced'))
            self.app.book_export_settings['audio_format']=d.get('audio_format','wav')
            if d.get('render_cache'):
                os.environ['OPENMUKTI_RENDER_CACHE']=d['render_cache']
            else:
                os.environ.pop('OPENMUKTI_RENDER_CACHE',None)
        from .gui_workflows import preferences
        return preferences(self.root,cfg,apply)

    def apply_prefs(self):
        p=self.prefs
        app=self.app
        if p.get('audio_format'):
            app.book_export_settings.setdefault('audio_format',p['audio_format'])
        if p.get('cpu_profile'):
            app.cpu_profile_var.set(p['cpu_profile'])
        from .windowing import apply_display_scale
        apply_display_scale(self.root,p.get('interface_scale',100))
        if p.get('font') or p.get('font_size'):
            app.font_size=int(p.get('font_size',12))
            app.editor.configure(font=(p.get('font',app.ui_font),app.font_size))
        if not hasattr(self,'original_colors'):
            self.original_colors=(app.BG,app.CARD,app.FIELD,app.FG,app.ACCENT)
        if p.get('high_contrast'):
            app.BG,app.CARD,app.FIELD,app.FG,app.ACCENT=('#000000','#111111','#000000','#ffffff','#ffff00')
        else:
            app.BG,app.CARD,app.FIELD,app.FG,app.ACCENT=self.original_colors
        app._styles()
        app.editor.configure(bg=app.FIELD,fg=app.FG,insertbackground=app.FG)
        app.root.configure(bg=app.BG)
        if p.get('touch'):
            ttk.Style(self.root).configure('TButton',padding=(12,9))
        if hasattr(app,'studio_editor_side'):
            left=app.studio_editor_side
            right=app.studio_settings_side
            work=left.master
            flipped=bool(p.get('left_handed'))
            left.grid_configure(column=int(flipped))
            right.grid_configure(column=int(not flipped))
            work.columnconfigure(int(flipped),weight=1,minsize=0)
            work.columnconfigure(int(not flipped),weight=0,minsize=220)
        os.environ['OPENMUKTI_REDUCED_MOTION']='1' if p.get('reduced_motion') else '0'
        for key,bid in self.bindings.items():
            self.root.unbind(key,bid)
        self.bindings={}
        for key,action in p.get('shortcuts',{}).items():
            if action in self.actions and re.fullmatch(r'<[A-Za-z0-9_-]{1,50}>',key):
                self.bindings[key]=self.root.bind(key,lambda e,a=action:(guarded(self.root,self.actions[a])(),'break')[1],add='+')
        for child in self.shortbar.winfo_children():
            child.destroy()
        actions=p.get('toolbar',[])
        if actions:
            self.shortbar.pack(side='bottom',fill='x')
            for name in actions:
                if name in self.actions:
                    button(self.shortbar,name,self.actions[name])
        else:
            self.shortbar.pack_forget()
        translations={'en':{},'bn':BN,'es':ES}.get(p.get('language','en'),{})
        if p.get('translation_file'):
            translations={**translations,**json.loads(Path(p['translation_file']).read_text(encoding='utf-8'))}
        from .interface_language import static_catalog
        base=static_catalog(p.get('language','en'))
        self.translator.update({**base,**translations},p.get('language','en'),bool(p.get('translate_missing')))

    def setup(self):
        from .gui_workflows import setup
        return setup(self)

    def tutorial(self):
        w=tk.Toplevel(self.root)
        w.title('Guided production tutorial')
        fit_window(w,600,340,340,250)
        steps=[('Start a project','Open a manuscript or create a project tab.','Project tabs'),
               ('Review narration','Hear the active passage highlighted in the text.','Read along'),
               ('Design the cover','Place the title and creator credit, then export a cover.','Cover designer'),
               ('Mix the sound','Add narration and optional ambience, then export a mix.','Sound timeline')]
        page=[0]
        title=tk.StringVar()
        detail=tk.StringVar()
        ttk.Label(w,textvariable=title,font=('TkDefaultFont',16)).pack(pady=12)
        ttk.Label(w,textvariable=detail,wraplength=400).pack()
        def change(n):
            page[0]=max(0,min(len(steps)-1,page[0]+n))
            t,d,_=steps[page[0]]
            title.set(f'{page[0]+1}. {t}')
            detail.set(d)
        bar=line(w)
        button(bar,'Previous',lambda:change(-1))
        button(bar,'Try this step',lambda:self.actions[steps[page[0]][2]]())
        button(bar,'Next',lambda:change(1))
        change(0)
    def context_help(self,widget):
        try:
            title=widget.winfo_toplevel().title().lower()
        except tk.TclError:
            title=''
        topics={'waveform':'SOUND AND AUDIO','sound':'SOUND AND AUDIO','subtitle':'CAPTIONS AND VIDEO',
                'cover':'ARTWORK AND COMIC PANELS','chapter':'CREATING A PROJECT','project':'CREATING A PROJECT',
                'voice':'VOICES AND PRONUNCIATIONS','queue':'PRODUCTION QUEUE','ocr':'CREATING A PROJECT'}
        section=next((v for k,v in topics.items() if k in title),None)
        if section:
            from importlib import resources
            text=resources.files('openvoice').joinpath('resources','GUI_GUIDE.txt').read_text(encoding='utf-8')
            start=text.find('\n'+section+'\n')
            end=re.search(r'\n[A-Z][A-Z ,]+\n',text[start+len(section)+2:]) if start>=0 else None
            if start>=0:
                last=start+len(section)+2+end.start() if end else len(text)
                show_text(widget.winfo_toplevel(),section.title(),text[start:last].strip())
                return 'break'
        self.help()
        return 'break'

    def help(self):
        self.app._show_document('Audiobook production guide','GUI_GUIDE.txt')
