"""Accessible desktop editors for projects, chapters, artwork and multitrack sessions."""
from __future__ import annotations

import copy
import difflib
import json
import os
import queue
import re
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .windowing import fit_window
from .voice_library import _atomic_json


def guarded(parent,action):
    def run(*args):
        try:
            return action(*args)
        except Exception as exc:
            messagebox.showerror(parent.title(),str(exc),parent=parent)
    return run


def async_job(win,label,job,on_done=None):
    if getattr(win,'_studio_busy',False):
        raise ValueError('Another operation is running in this window. Wait for it to finish.')
    win._studio_busy=True
    label.set('Working…')
    results=queue.Queue()
    def run():
        try:
            results.put((True,job()))
        except Exception as exc:
            results.put((False,str(exc)))
    def poll():
        if not win.winfo_exists():
            return
        try:
            ok,value=results.get_nowait()
        except queue.Empty:
            win.after(100,poll)
            return
        win._studio_busy=False
        if ok:
            label.set('Finished')
            if on_done:
                guarded(win,on_done)(value)
        else:
            label.set('Failed')
            messagebox.showerror(win.title(),value,parent=win)
    threading.Thread(target=run,daemon=True).start()
    win.after(100,poll)


def button(frame,label,cmd):
    b=ttk.Button(frame,text=label,command=guarded(frame.winfo_toplevel(),cmd))
    b.pack(side='left',padx=2,pady=2)
    return b


def line(parent):
    """Wrap toolbar controls on narrow screens, keeping their keyboard creation order."""
    frame=ttk.Frame(parent)
    frame.pack(fill='x',padx=4,pady=2)
    last=[None]
    def wrap(_event=None):
        width=frame.winfo_width()
        if width<40:
            return
        children=frame.winfo_children()
        if not children:
            return
        sizes=[(c.winfo_reqwidth(),c.winfo_reqheight()) for c in children]
        if last[0]==(width,sizes):
            return
        last[0]=(width,sizes)
        x=y=row=0
        for child,(cw,ch) in zip(children,sizes):
            if x and x+cw+4>width:
                y+=row+4
                x=row=0
            if child.winfo_manager()=='pack':
                child.pack_forget()
            child.place(x=x+2,y=y+2,width=min(cw,width-4),height=ch)
            x+=cw+4
            row=max(row,ch)
        frame.configure(height=y+row+4)
    frame.bind('<Configure>',wrap,add='+')
    pending=frame.after_idle(wrap)
    def cleanup(event):
        if event.widget is frame:
            try:frame.after_cancel(pending)
            except tk.TclError:pass
    frame.bind('<Destroy>',cleanup,add='+')
    return frame


class DesignHistory:
    """Reversible snapshots for structured editing, kept within the current session."""
    def __init__(self):
        self.snapshots=[]
        self.position=-1

    def remember(self,data):
        snapshot=json.dumps(data,sort_keys=True,ensure_ascii=False)
        if self.position>=0 and self.snapshots[self.position]==snapshot:
            return
        self.snapshots[self.position+1:]=[snapshot]
        if len(self.snapshots)>100:
            self.snapshots.pop(0)
        self.position=len(self.snapshots)-1

    def move(self,delta):
        target=self.position+delta
        if not 0<=target<len(self.snapshots):
            raise ValueError('No more edit history in that direction')
        self.position=target
        return json.loads(self.snapshots[target])


def show_text(parent,title,body):
    w=tk.Toplevel(parent)
    w.title(title)
    fit_window(w,850,640,340,300)
    text=tk.Text(w,wrap='word',padx=8,pady=8)
    text.pack(fill='both',expand=True)
    text.insert('1.0',body)
    text.configure(state='disabled')
    ttk.Button(w,text='Close',command=w.destroy).pack()
    return w


def protect_widget(box):
    """Reject edits to marked passages, including keyboard, selection and paste replacements."""
    original=box._w+'_editable'
    box.tk.call('rename',box._w,original)
    def proxy(*args):
        op=args[0]
        try:
            if op in ('delete','insert','replace') and not getattr(box,'_loading',False):
                start=str(box.tk.call(original,'index',args[1]))
                if op=='insert':
                    stop=start
                elif len(args)>=3:
                    stop=str(box.tk.call(original,'index',args[2]))
                else:
                    stop=str(box.tk.call(original,'index',start+' +1 chars'))
                raw=box.tk.call(original,'tag','ranges','locked')
                marks=box.tk.splitlist(raw)
                for a,b in zip(marks[::2],marks[1::2]):
                    cmp=lambda x,rel,y:bool(int(box.tk.call(original,'compare',x,rel,y)))
                    if (op=='insert' and cmp(a,'<=',start) and cmp(start,'<',b)) or (op!='insert' and cmp(start,'<',b) and cmp(stop,'>',a)):
                        box.bell()
                        return ''
            return box.tk.call(original,*args)
        except tk.TclError:
            raise
    box.tk.createcommand(box._w,proxy)
    def cleanup(evt):
        if evt.widget is box:
            try:
                box.tk.deletecommand(box._w)
            except tk.TclError:
                pass
    box.bind('<Destroy>',cleanup,add='+')


class ProjectTabs:
    def __init__(self,app):
        from .project_archive import ProjectData
        self.app=app
        self.win=tk.Toplevel(app.root)
        self.win.title('Project workspace')
        fit_window(self.win,1100,740,420,340)
        self.data={}
        bar=line(self.win)
        button(bar,'New tab',lambda:self.tab(ProjectData()))
        button(bar,'Open project',self.open)
        button(bar,'Open read-only',lambda:self.open(True))
        button(bar,'Save',self.save)
        button(bar,'Save copy',lambda:self.save(True))
        button(bar,'Close tab',self.close_tab)
        bar=line(self.win)
        for name,method in [('Compare edits',self.compare),('Review corrections',self.review),('Transform preview',self.transform_preview),('Editorial rules',self.rules),
                            ('Protect selection',self.protect),('Activity',self.activity),('Chapters',self.chapters)]:
            button(bar,name,method)
        self.note=ttk.Notebook(self.win)
        self.note.pack(fill='both',expand=True,padx=4,pady=4)
        self.status=tk.StringVar(value='Ctrl+S saves the active tab. Protected passages are underlined.')
        ttk.Label(self.win,textvariable=self.status,wraplength=700).pack(fill='x',padx=6)
        self.win.bind('<Control-s>',lambda e:(guarded(self.win,self.save)(),'break')[1])
        self.win.protocol('WM_DELETE_WINDOW',self.close)
        self.tab(copy.deepcopy(app._project_snapshot()))

    def tab(self,project,path=None,readonly=False,room=None):
        page=ttk.Frame(self.note)
        self.note.add(page,text=('🔒 ' if readonly else '')+(Path(path).stem if path else 'Untitled'))
        box=tk.Text(page,undo=True,wrap='word',maxundo=-1,padx=8,pady=8)
        scroll=ttk.Scrollbar(page,command=box.yview)
        scroll.pack(side='right',fill='y')
        box.configure(yscrollcommand=scroll.set)
        box.pack(fill='both',expand=True)
        box.insert('1.0',project.text)
        protect_widget(box)
        box.tag_configure('locked',background='#d6e6f0',foreground='#172b3a',underline=True)
        box.tag_configure('speaker',foreground='#9d5320',underline=True)
        cfg=project.settings.setdefault('studio_editor',{})
        for a,b in cfg.get('protected_ranges',[]):
            box.tag_add('locked',f'1.0+{a}c',f'1.0+{b}c')
        item={'page':page,'box':box,'project':project,'path':Path(path) if path else None,'ro':readonly,
              'room':room,'stamp':Path(path).stat().st_mtime_ns if path else None,'baseline':project.text,'meta_dirty':False}
        self.data[str(page)]=item
        def highlight(_evt=None):
            box.tag_remove('speaker','1.0','end')
            for m in re.finditer(r'\[[^\[\]\n]{1,160}\]',box.get('1.0','end-1c')):
                box.tag_add('speaker',f'1.0+{m.start()}c',f'1.0+{m.end()}c')
        highlight()
        box.bind('<KeyRelease>',highlight,add='+')
        if readonly:
            box.configure(state='disabled')
        self.note.select(page)
        box.focus_set()
        return item

    def current(self):
        item=self.data.get(self.note.select())
        if not item:
            raise ValueError('Open a project tab')
        return item

    def edit(self):
        item=self.current()
        if item['ro']:
            raise ValueError('Open an editable copy of this read-only project')
        return item

    def open(self,readonly=False):
        from .project_archive import load_project
        path=filedialog.askopenfilename(parent=self.win,filetypes=[('Openmukti project','*.oamproj')])
        if not path:
            return
        room=tempfile.TemporaryDirectory(prefix='openmukti-tab-')
        try:
            project=load_project(path,room.name)
        except Exception:
            room.cleanup()
            raise
        self.tab(project,path,readonly,room)

    def save(self,copy_only=False):
        from .project_archive import save_project
        from .editorial_studio import record_revision,learn_edits
        item=self.current() if copy_only else self.edit()
        path=item['path']
        if copy_only or not path:
            name=filedialog.asksaveasfilename(parent=self.win,defaultextension='.oamproj',filetypes=[('Openmukti project','*.oamproj')])
            if not name:
                return
            path=Path(name)
            if item['ro'] and item['path'] and path.resolve()==item['path'].resolve():
                raise ValueError('Select a new filename')
        if path==item['path'] and path.stat().st_mtime_ns!=item['stamp']:
            raise ValueError('This project changed on disk. Save an independent copy.')
        box=item['box']
        project=copy.deepcopy(item['project'])
        data=project.settings.setdefault('studio_editor',{})
        project.text=box.get('1.0','end-1c')
        marks=[int(box.count('1.0',idx,'chars')[0]) if box.compare(idx,'>','1.0') else 0 for idx in box.tag_ranges('locked')]
        data['protected_ranges']=[list(pair) for pair in zip(marks[::2],marks[1::2])]
        record_revision(data,item['baseline'],project.text,'Saved manuscript')
        learn_edits(item['baseline'],project.text,data.setdefault('rules',{}))
        save_project(path,project)
        if not item['ro']:
            item.update(project=project,path=path,baseline=project.text,stamp=path.stat().st_mtime_ns,meta_dirty=False)
            self.note.tab(item['page'],text=path.stem)
        self.status.set('Saved '+str(path))

    def _dirty(self,item):
        return not item['ro'] and (item['meta_dirty'] or item['box'].get('1.0','end-1c')!=item['baseline'])

    def close_tab(self):
        item=self.current()
        if self._dirty(item) and not messagebox.askyesno('Close tab','Discard unsaved edits in this tab?',parent=self.win):
            return
        page=item['page']
        del self.data[str(page)]
        self.note.forget(page)
        page.destroy()
        if item['room']:
            item['room'].cleanup()

    def close(self):
        if any(self._dirty(v) for v in self.data.values()) and not messagebox.askyesno('Close workspace','Discard unsaved edits in the open tabs?',parent=self.win):
            return
        for item in self.data.values():
            if item['room']:
                item['room'].cleanup()
        self.win.destroy()

    def protect(self):
        item=self.edit()
        box=item['box']
        if not box.tag_ranges('sel'):
            raise ValueError('Select a passage first')
        a,b=box.tag_ranges('sel')
        if 'locked' in box.tag_names(a):
            box.tag_remove('locked',a,b)
        else:
            box.tag_add('locked',a,b)
        item['meta_dirty']=True
        # Tk native undo replays internal edits. Start a fresh undo group at the protection boundary.
        box.edit_reset()

    def rules(self):
        item=self.edit()
        cfg=item['project'].settings.setdefault('studio_editor',{})
        rules=cfg.setdefault('rules',{'terms':[],'protected':[],'style':{},'engines':['context','duplicates','agreement']})
        def apply_rules(value):
            speakers=value.get('speakers',{})
            if not isinstance(speakers,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in speakers.items()):
                raise ValueError('Speaker rules must map a phrase to a cast name')
            item['project'].voice_project.speaker_rules=dict(speakers)
            cfg.update(rules=value)
            item['meta_dirty']=True
        edit_json(self.win,'Project terminology, style and speaker rules',dict(rules,speakers=item['project'].voice_project.speaker_rules),apply_rules)

    def review(self):
        from .editorial_studio import suggestions
        item=self.edit()
        box=item['box']
        raw=box.get('1.0','end-1c')
        cfg=item['project'].settings['studio_editor']
        findings=suggestions(raw,cfg.get('rules'))
        if not findings:
            self.status.set('No suggestions from enabled rules')
            return
        win=tk.Toplevel(self.win)
        win.title('Review suggestions')
        fit_window(win,650,420,300,250)
        boxlist=tk.Listbox(win,exportselection=False)
        boxlist.pack(fill='both',expand=True)
        for f in findings:
            boxlist.insert('end',f'{f["original"]} → {f["replacement"]} ({f["reason"]})')
        def apply():
            if box.get('1.0','end-1c')!=raw:
                raise ValueError('The manuscript changed. Reopen the review.')
            selected=boxlist.curselection()
            if not selected:
                return
            f=findings[selected[0]]
            box.replace(f'1.0+{f["start"]}c',f'1.0+{f["end"]}c',f['replacement'])
            win.destroy()
        button(line(win),'Apply selected suggestion',apply)

    def transform_preview(self):
        from .texttools import TOOLS,transform
        from .editor_undo import replace_text
        item=self.edit()
        box=item['box']
        original=box.get('1.0','end-1c')
        if box.tag_ranges('locked'):
            raise ValueError('Unlock protected regions before transforming the whole manuscript')
        window=tk.Toplevel(self.win)
        window.title('Non-destructive transformation preview')
        fit_window(window,760,540,340,260)
        bar=line(window)
        operation=tk.StringVar(value=next(iter(TOOLS)))
        ttk.Combobox(bar,textvariable=operation,values=list(TOOLS),state='readonly').pack(side='left')
        preview=tk.Text(window,wrap='word',state='disabled')
        preview.pack(expand=True,fill='both')
        def generate():
            result=transform(original,[operation.get()])
            preview.configure(state='normal')
            preview.delete('1.0','end')
            preview.insert('1.0',result)
            preview.configure(state='disabled')
            return result
        def accept():
            if box.get('1.0','end-1c')!=original:
                raise ValueError('Manuscript changed since the preview opened')
            replace_text(box,generate())
            window.destroy()
        button(bar,'Preview change',generate)
        button(bar,'Apply',accept)
        button(bar,'Discard',window.destroy)
        generate()

    def compare(self):
        item=self.current()
        win=tk.Toplevel(self.win)
        win.title('Compare original and current manuscript')
        fit_window(win,1000,650,360,300)
        pane=ttk.Panedwindow(win,orient='horizontal')
        pane.pack(fill='both',expand=True)
        now=item['box'].get('1.0','end-1c')
        for label,body in [('Saved version',item['baseline']),('Current version',now)]:
            f=ttk.Frame(pane)
            pane.add(f,weight=1)
            ttk.Label(f,text=label).pack()
            b=tk.Text(f,wrap='word')
            b.pack(fill='both',expand=True)
            b.insert('1.0',body)
            b.configure(state='disabled')

    def activity(self):
        data=self.current()['project'].settings['studio_editor'].get('revisions',[])
        show_text(self.win,'Project activity and tracked changes','\n\n'.join(r['time']+' '+r['label']+'\n'+''.join(x for x in r['changes'] if x[:1] in ('+','-')) for r in data) or 'No saved revisions')

    def chapters(self):
        chapter_view(self.win,self.current()['box'],readonly=self.current()['ro'])


def edit_json(parent,title,data,save):
    # Keep the existing extension API while providing a typed visual editor.
    from .gui_forms import edit_settings
    return edit_settings(parent,title,data,save)


def chapter_view(parent,editor,readonly=False):
    from .book_structure import detect_chapters,detect_scene_breaks
    from .editorial_studio import section_kind
    raw=editor.get('1.0','end-1c')
    sections=detect_chapters(raw)
    if not sections:
        raise ValueError('Enter or import a manuscript first')
    win=tk.Toplevel(parent)
    win.title('Chapter navigator')
    fit_window(win,740,530,360,300)
    lb=tk.Listbox(win,exportselection=False)
    lb.pack(fill='both',expand=True)
    def update():
        lb.delete(0,'end')
        for s in sections:
            lb.insert('end',f'{s.title}  ·  {section_kind(s.title)}  ·  {s.words()} words')
    update()
    def chosen():
        return lb.curselection()[0] if lb.curselection() else 0
    def jump(event=None):
        s=sections[chosen()]
        needle=s.text[:48] if s.text else s.title
        idx=editor.search(needle,'1.0','end',exact=True)
        if idx:
            editor.see(idx)
            editor.mark_set('insert',idx)
            editor.focus_set()
    lb.bind('<Double-Button-1>',jump)
    lb.bind('<Return>',jump)
    drag={}
    lb.bind('<ButtonPress-1>',lambda e:drag.update(index=lb.nearest(e.y)))
    def move(i,j):
        if readonly or i==j or not 0<=j<len(sections):
            return
        sections.insert(j,sections.pop(i))
        update()
        lb.selection_set(j)
    lb.bind('<ButtonRelease-1>',lambda e:move(drag.get('index',lb.nearest(e.y)),lb.nearest(e.y)))
    bar=line(win)
    button(bar,'Jump to chapter',jump)
    def scene_list():
        s=sections[chosen()]
        from .gui_forms import show_report
        show_report(win,'Scene timeline',detect_scene_breaks(s.text))
    button(bar,'Scene timeline',scene_list)
    if not readonly:
        button(bar,'Move up',lambda:move(chosen(),chosen()-1))
        button(bar,'Move down',lambda:move(chosen(),chosen()+1))
        def apply():
            if editor.get('1.0','end-1c')!=raw:
                raise ValueError('Manuscript changed. Reopen chapter navigation.')
            if editor.tag_ranges('locked'):
                raise ValueError('Unlock protected passages before restructuring chapters')
            from .editor_undo import replace_text
            replace_text(editor,'\n\n'.join('#'*s.level+' '+s.title+'\n\n'+s.text for s in sections))
            win.destroy()
        button(bar,'Apply chapter order and headings',apply)


def register_structured_undo(window,change):
    """Route standard edit commands to the focused structured editor."""
    window.studio_history_change=change
    for key,direction in (('<Control-z>',-1),('<Control-y>',1),('<Control-Shift-Z>',1),
                          ('<Command-z>',-1),('<Command-Shift-Z>',1)):
        def dispatch(event,delta=direction):
            if event.widget.winfo_class() in ('Text','Entry','TEntry','TCombobox','Spinbox','TSpinbox'):
                return None
            try:
                change(delta)
            except ValueError:
                window.bell()
            return 'break'
        try:
            window.bind(key,dispatch,add='+')
        except tk.TclError:
            pass
