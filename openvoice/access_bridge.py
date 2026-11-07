"""Expose the visible native desktop controls to an opt-in local HTML accessibility view."""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import ttk


class ControlBridge:
    def __init__(self,root):
        self.root=root
        self.pending=queue.Queue(maxsize=64)
        self.registry={}
        self.closed=False
        self.timer=root.after(60,self._poll)

    def close(self):
        self.closed=True
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer=None

    def request(self,method,data=None):
        if self.closed:
            raise RuntimeError('The desktop view is closed')
        results=queue.Queue(maxsize=1)
        try:
            self.pending.put_nowait((method,data,results))
            ok,result=results.get(timeout=8)
        except (queue.Empty,queue.Full) as exc:
            raise RuntimeError('The desktop is busy. Complete any native file dialog, then refresh.') from exc
        if not ok:
            raise ValueError(result)
        return result

    def _poll(self):
        if self.closed:return
        while True:
            try:method,data,result=self.pending.get_nowait()
            except queue.Empty:break
            try:
                if method=='list':value=self.controls()
                else:value=self.activate(data)
                result.put((True,value))
            except Exception as exc:
                result.put((False,str(exc)))
        self.timer=self.root.after(60,self._poll)

    @staticmethod
    def _label(w):
        options=w.keys()
        if 'text' in options and w.cget('text'):
            return str(w.cget('text'))
        if 'textvariable' in options and w.cget('textvariable') and isinstance(w,(ttk.Button,ttk.Label,tk.Button,tk.Label)):
            return str(w.getvar(w.cget('textvariable')))
        for other in reversed(w.master.winfo_children()[:w.master.winfo_children().index(w)]):
            if isinstance(other,(tk.Label,ttk.Label,ttk.Labelframe)):
                value=str(other.cget('text'))
                if value:return value
        return w.winfo_toplevel().title()+' '+w.winfo_class()

    def controls(self):
        rows=[];registry={}
        def add(w,kind,label,sub=None,**details):
            name=str(w)+'|'+kind+'|'+str(sub or '')
            registry[name]=(w,kind,sub)
            top=w.winfo_toplevel()
            title=top.title() if hasattr(top,'title') else self.root.title()
            rows.append(dict(id=name,kind=kind,label=label,window=title,**details))
        def menus(menu,path=()):
            for i in range((menu.index('end') or 0)+1):
                try:
                    kind=menu.type(i)
                    if kind in ('separator','tearoff') or menu.entrycget(i,'state')=='disabled':continue
                    label=menu.entrycget(i,'label')
                    if kind=='cascade':
                        menus(menu.nametowidget(menu.entrycget(i,'menu')),path+(label,))
                    else:add(menu,'action',' → '.join((*path,label)),i)
                except tk.TclError:continue
        def walk(w):
            if isinstance(w,tk.Menu):return
            visible=w.winfo_viewable()
            if visible:
                cls=w.winfo_class()
                disabled='state' in w.keys() and str(w.cget('state'))=='disabled'
                if not disabled and isinstance(w,(tk.Button,ttk.Button,ttk.Checkbutton,ttk.Radiobutton,tk.Checkbutton,tk.Radiobutton)):
                    add(w,'action',self._label(w))
                elif not disabled and isinstance(w,ttk.Combobox):
                    add(w,'choice',self._label(w),choices=list(w.cget('values')),value=w.get())
                elif not disabled and isinstance(w,(tk.Entry,ttk.Entry,ttk.Spinbox,tk.Spinbox)):
                    # Masked secrets stay exclusively in the native dialog.
                    if 'show' not in w.keys() or not w.cget('show'):
                        add(w,'entry',self._label(w),value=str(w.get())[:16000])
                elif isinstance(w,tk.Text):
                    if not disabled:
                        add(w,'text',self._label(w),value=w.get('1.0','end-1c')[:65536],length=int(w.index('end-1c').split('.')[0]))
                elif isinstance(w,(ttk.Scale,tk.Scale)):
                    add(w,'number',self._label(w),value=w.get(),low=float(w.cget('from')),high=float(w.cget('to')))
                elif isinstance(w,ttk.Notebook):
                    for t in w.tabs():add(w,'tab',w.tab(t,'text'),t)
                elif isinstance(w,tk.Listbox) and w.size():
                    choices=[str(w.get(i)) for i in range(min(5000,w.size()))]
                    add(w,'list',self._label(w),choices=choices,value=w.curselection()[0] if w.curselection() else -1)
                elif isinstance(w,ttk.Treeview):
                    visible_rows=list(w.get_children(''))
                    for item in visible_rows[:1000]:
                        if w.item(item,'open'):visible_rows.extend(w.get_children(item))
                    for item in visible_rows[:1000]:
                        d=w.item(item);label=str(d['text'])+' '+' '.join(map(str,d['values'] or []))
                        add(w,'row',label.strip() or 'Select row',item)
            for child in w.winfo_children():
                if visible or isinstance(child,tk.Toplevel):walk(child)
        name=self.root.cget('menu')
        if name:menus(self.root.nametowidget(name))
        walk(self.root)
        self.registry=registry
        return rows

    def activate(self,data):
        key=data.get('id')
        if key not in self.registry:raise ValueError('Refresh to load the current visible controls')
        w,kind,sub=self.registry[key];value=data.get('value','')
        if not w.winfo_exists():raise ValueError('This window was closed')
        if kind=='action':
            if isinstance(w,tk.Menu):
                if w.entrycget(sub,'state')=='disabled':raise ValueError('This control is disabled')
                self.root.after_idle(lambda:w.invoke(sub))
            elif w.winfo_viewable() and str(w.cget('state'))!='disabled':
                self.root.after_idle(w.invoke)
        elif kind=='tab':w.select(sub)
        elif kind=='row':w.selection_set(sub);w.focus(sub);w.see(sub)
        elif kind=='list':
            i=int(value)
            if not 0<=i<w.size():raise ValueError('Select an existing item')
            w.selection_clear(0,'end');w.selection_set(i);w.see(i);w.event_generate('<<ListboxSelect>>')
        elif kind=='number':
            v=float(value);lo,hi=sorted((float(w.cget('from')),float(w.cget('to'))))
            if not lo<=v<=hi:raise ValueError('Value is outside the control range')
            w.set(v)
        elif kind=='choice':
            if str(w.cget('state'))=='readonly' and value not in w.cget('values'):raise ValueError('Choose a listed value')
            w.set(str(value));w.event_generate('<<ComboboxSelected>>')
        elif kind=='entry':
            w.delete(0,'end');w.insert(0,str(value));w.event_generate('<KeyRelease>')
        elif kind=='text':
            if len(str(value))>65536 or len(w.get('1.0','end-1c'))>65536:
                raise ValueError('Use the manuscript editor to edit a longer document')
            if 'locked' in w.tag_names() and w.tag_ranges('locked'):raise ValueError('This manuscript includes protected text')
            from .editor_undo import replace_text
            replace_text(w,str(value));w.event_generate('<KeyRelease>')
        return {'accepted':True}


CONTROLS_HTML='''<section aria-labelledby="desktop-title"><h2 id="desktop-title">Desktop controls</h2>
<p>Use the same commands, fields, tabs and selections as the desktop. Refresh after a window opens or closes.</p>
<button id="refresh-controls">Refresh controls</button>
<label for="filter-controls">Find a control</label><input id="filter-controls" type="search">
<div id="native-controls"></div></section>
<script>
(() => {const get=id=>document.getElementById(id), status=get('status');let rows=[];
const note=t=>status.textContent=t;
async function load(){try {const r=await fetch(location.pathname+'controls');if(!r.ok)throw Error(await r.text());rows=await r.json();display();note('Desktop controls refreshed');}catch(e){note(e.message);}}
async function act(id,val){try {const r=await fetch(location.pathname+'control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,value:val})});if(!r.ok)throw Error(await r.text());note('Command accepted. Refresh after the desktop changes.');}catch(e){note(e.message);}}
function display(){const parent=get('native-controls');parent.replaceChildren();let section='',index=0;const search=get('filter-controls').value.toLowerCase();
for(const item of rows){if(search && !(item.window+' '+item.label).toLowerCase().includes(search))continue;
if(section!==item.window){section=item.window;const heading=document.createElement('h3');heading.textContent=section;parent.append(heading);}
const row=document.createElement('div');parent.append(row);
if(['action','row','tab'].includes(item.kind)){const b=document.createElement('button');b.textContent=item.label;b.onclick=()=>act(item.id,'');row.append(b);continue;}
let f;if(['list','choice'].includes(item.kind)){f=document.createElement('select');item.choices.forEach((v,i)=>{const op=document.createElement('option');op.textContent=v;op.value=item.kind==='list'?i:v;f.append(op);});}
else if(item.kind==='text'){f=document.createElement('textarea');}else{f=document.createElement('input');if(item.kind==='number'){f.type='number';f.min=item.low;f.max=item.high;f.step='any';}}
f.id='native-'+(++index);f.value=item.value;const l=document.createElement('label');l.htmlFor=f.id;l.textContent=item.label;row.append(l,f);
const b=document.createElement('button');b.textContent='Apply '+item.label;b.onclick=()=>act(item.id,f.value);row.append(b);}}
get('refresh-controls').onclick=load;get('filter-controls').oninput=display;
})();</script>'''
