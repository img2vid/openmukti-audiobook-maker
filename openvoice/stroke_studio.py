"""Interactive Unicode Stroke Studio for authoring genuine pen trajectories.

The drawing canvas records pen movement rather than approximating font shapes.
Each template may represent any Unicode grapheme, conjunct or small unit. Saved
JSON remains editable outside the application and portable in .oamproj files.
Tkinter is imported only when the editor is explicitly opened.
"""
from __future__ import annotations

from pathlib import Path
from .stroke_library import StrokeLibrary, load_stroke_library


def open_stroke_studio(parent, filename: str = '', on_save=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    window=tk.Toplevel(parent)
    window.title('OpenMukti Stroke Studio — draw letters with a real pen path')
    from .windowing import fit_window
    fit_window(window,850,730,360,300)
    try: window.transient(parent)
    except tk.TclError: pass
    library=load_stroke_library(filename) if filename and Path(filename).is_file() else StrokeLibrary({})
    path=tk.StringVar(value=filename)
    label=tk.StringVar(value='ক')
    pressure=tk.DoubleVar(value=.8)
    strokes=[]
    active=None
    pen=[.5,.5]
    keyboard_drawing=[False]
    width,height=710,470
    pad=20
    top=ttk.Frame(window,padding=10)
    top.pack(fill='x')
    ttk.Label(top,text='Character / grapheme / conjunct:').pack(side='left')
    field=ttk.Entry(top,textvariable=label,width=14,font=('TkDefaultFont',15))
    field.pack(side='left',padx=(6,12))
    ttk.Label(top,text='Pressure').pack(side='left')
    ttk.Scale(top,from_=.1,to=1.0,variable=pressure,orient='horizontal',length=160).pack(side='left',padx=8)
    count=ttk.Label(top,text='0 strokes')
    count.pack(side='right')
    frame=ttk.Frame(window,padding=(10,0,10,0))
    frame.pack(fill='both',expand=True)
    board=tk.Canvas(frame,takefocus=True,background='#f8f3e7',highlightthickness=1,highlightbackground='#b7b2a9',cursor='pencil')
    board.pack(fill='both',expand=True)
    ttk.Label(window,text='Draw strokes in their intended order (mouse or tablet). Release between strokes. The saved trajectories are independent of fonts; pressure is captured from the slider.',wraplength=820).pack(fill='x',padx=12,pady=6)
    def area():
        return max(80,board.winfo_width()-2*pad),max(80,board.winfo_height()-2*pad)
    def point(x,y):
        w,h=area()
        return (max(0.0,min(1.0,(x-pad)/w)),max(0.0,min(1.0,(y-pad)/h)),float(pressure.get()))
    def screen(p):
        w,h=area()
        return (pad+p[0]*w,pad+p[1]*h)
    def paint():
        board.delete('all')
        w,h=area()
        board.create_line(pad,pad+h*.76,pad+w,pad+h*.76,fill='#ddd5c8',dash=(3,6))
        board.create_rectangle(pad,pad,pad+w,pad+h,outline='#ded8cc')
        for i,path_points in enumerate(strokes):
            coords=[screen(p) for p in path_points]
            if len(coords)==1:
                x,y=coords[0];board.create_oval(x-2,y-2,x+2,y+2,fill='#1d2c44',outline='')
            else:
                for a,b in zip(coords,coords[1:]):
                    board.create_line(*a,*b,width=2+2*path_points[0][2],fill='#253752',capstyle=tk.ROUND,smooth=False)
            if coords:
                x,y=coords[0]
                board.create_oval(x-3,y-3,x+3,y+3,fill='#a3572e',outline='')
                board.create_text(x+8,y-8,text=str(i+1),anchor='w',fill='#91543a',font=('TkDefaultFont',9))
        count.configure(text=f'{len(strokes)} strokes')
    def down(e):
        nonlocal active
        keyboard_drawing[0]=False
        if len(strokes)>=128:return
        active=[point(e.x,e.y)]
        strokes.append(active)
        paint()
    def motion(e):
        if active is None:return
        p=point(e.x,e.y)
        if len(active)>=4096:return
        if sum((p[j]-active[-1][j])**2 for j in (0,1)) > .000012:
            active.append(p)
            if len(active)%3==0:paint()
    def up(_e):
        nonlocal active
        if active:paint()
        active=None
    keyboard_status=tk.StringVar(value='Keyboard pen ready')
    ttk.Label(window,textvariable=keyboard_status,wraplength=700).pack(fill='x',padx=12)
    def redraw_cursor():
        paint()
        x,y=screen(pen)
        board.create_oval(x-4,y-4,x+4,y+4,outline='#a13c14',width=2)
        keyboard_status.set(f'Pen {"down" if keyboard_drawing[0] else "up"} · X {pen[0]:.2f}, Y {pen[1]:.2f}')
    def move_key(event,dx,dy):
        scale=.05 if event.state & 1 else .01
        pen[0]=max(0,min(1,round(pen[0]+dx*scale,3)))
        pen[1]=max(0,min(1,round(pen[1]+dy*scale,3)))
        if keyboard_drawing[0] and strokes and len(strokes[-1])<4096:
            strokes[-1].append((pen[0],pen[1],float(pressure.get())))
        redraw_cursor()
        return 'break'
    def toggle_pen(_event=None):
        if len(strokes)>=128 and not keyboard_drawing[0]:return 'break'
        keyboard_drawing[0]=not keyboard_drawing[0]
        if keyboard_drawing[0]:
            strokes.append([(pen[0],pen[1],float(pressure.get()))])
        redraw_cursor()
        return 'break'
    for key,(dx,dy) in {'Left':(-1,0),'Right':(1,0),'Up':(0,-1),'Down':(0,1)}.items():
        board.bind('<'+key+'>',lambda event,x=dx,y=dy:move_key(event,x,y))
    board.bind('<space>',toggle_pen)
    board.bind('<FocusIn>',lambda event:redraw_cursor())
    def coordinates():
        from .studio_windows import edit_json
        def accept(obj):
            curves=obj.get('strokes',[])
            if not curves or not isinstance(curves,list):
                raise ValueError('Supply at least one sequence of x, y and pressure values')
            StrokeLibrary({}).with_glyph(label.get(),curves)
            strokes[:]=[[tuple(point) for point in path] for path in curves]
            keyboard_drawing[0]=False
            paint()
        edit_json(window,'Edit stroke coordinates',{'strokes':strokes or [[[.15,.25,.7],[.8,.75,.8]]]},accept)
    board.bind('<ButtonPress-1>',down)
    board.bind('<B1-Motion>',motion)
    board.bind('<ButtonRelease-1>',up)
    board.bind('<Configure>',lambda _e:paint())
    def load_character(*_):
        keyboard_drawing[0]=False
        text=label.get()
        strokes.clear()
        if text in library.glyphs:
            strokes.extend([[tuple(p) for p in t.points] for t in library.glyphs[text]])
        paint()
    field.bind('<Return>',load_character)
    def store_character():
        nonlocal library
        text=label.get()
        if not text.strip() or not strokes:
            messagebox.showwarning('Stroke Studio','Enter a character and draw at least one stroke.',parent=window)
            return False
        try:library=library.with_glyph(text,strokes)
        except ValueError as exc:
            messagebox.showerror('Invalid drawing',str(exc),parent=window)
            return False
        return True
    def browse():
        nonlocal library
        found=filedialog.askopenfilename(parent=window,title='Open stroke library',filetypes=[('Stroke library JSON','*.json'),('All files','*.*')])
        if found:
            try:library=load_stroke_library(found)
            except (ValueError,OSError) as exc:
                messagebox.showerror('Stroke library',str(exc),parent=window);return
            path.set(found)
            load_character()
    def save():
        if not store_character():return
        destination=path.get().strip()
        if not destination:
            destination=filedialog.asksaveasfilename(parent=window,title='Save Unicode stroke library',defaultextension='.json',filetypes=[('OpenMukti stroke library','*.json')])
        if not destination:return
        try:library.save(destination)
        except OSError as exc:
            messagebox.showerror('Unable to save',str(exc),parent=window);return
        path.set(destination)
        if on_save:on_save(destination)
        messagebox.showinfo('Stroke Studio',f'Saved {len(library.glyphs)} drawing templates.\n\nUse the same library for handwriting and calligraphy.',parent=window)
    def remove_strokes(all_strokes=False):
        keyboard_drawing[0]=False
        if all_strokes:
            strokes.clear()
        elif strokes:
            strokes.pop()
        paint()
    from .studio_windows import line
    controls=line(window)
    ttk.Button(controls,text='Edit stroke coordinates',command=coordinates).pack(side='left',padx=3)
    ttk.Button(controls,text='Load character',command=load_character).pack(side='left',padx=3)
    ttk.Button(controls,text='Undo stroke',command=remove_strokes).pack(side='left',padx=3)
    ttk.Button(controls,text='Clear character',command=lambda:remove_strokes(True)).pack(side='left',padx=3)
    ttk.Button(controls,text='Open pack…',command=browse).pack(side='left',padx=3)
    ttk.Button(controls,text='Save drawing + pack…',command=save).pack(side='right',padx=3)
    ttk.Entry(window,textvariable=path).pack(fill='x',padx=12,pady=(0,10))
    ttk.Label(window,text='Keyboard pen: Tab to the canvas, use arrows to move, Shift+arrows for larger steps, and Space to lower or lift the pen.',wraplength=700).pack(fill='x',padx=12)
    load_character()
    return window
