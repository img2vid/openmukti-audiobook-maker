"""Interactive Tk surfaces exercised under a display in CI."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from openvoice import gui
from openvoice.media_windows import CanvasDesigner,SoundDesk,WaveEditor
from openvoice.studio_windows import ProjectTabs


def run():
    results=[]
    def exercise(root):
        # Resolve the actual desktop App through the bound Studio actions.
        studio=installed[0]
        app=studio.app
        for constructor in (CanvasDesigner,SoundDesk,WaveEditor,ProjectTabs):
            win=constructor(app)
            root.update_idletasks()
            assert win.win.winfo_exists()
            if isinstance(win,ProjectTabs):
                entry=win.current()
                box=entry['box']
                box.insert('1.0','Hello')
                box.tag_add('locked','1.0','1.5')
                box.delete('1.0','1.2')
                assert box.get('1.0','1.5')=='Hello'
            results.append(constructor.__name__)
            win.win.destroy()
        from openvoice.stroke_studio import open_stroke_studio
        from openvoice.access_bridge import ControlBridge
        stroke=open_stroke_studio(root)
        root.update()
        def children(w):
            for child in w.winfo_children():
                yield child
                yield from children(child)
        canvas=next(w for w in children(stroke) if isinstance(w,tk.Canvas))
        canvas.focus_force()
        root.update()
        canvas.event_generate('<space>')
        canvas.event_generate('<Right>')
        canvas.event_generate('<Down>')
        canvas.event_generate('<space>')
        root.update()
        counts=[w.cget('text') for w in children(stroke) if 'text' in w.keys()]
        assert any('1 stroke' in str(v) for v in counts),counts
        bridge=ControlBridge(root)
        rows=bridge.controls()
        assert any(r['label']=='Edit stroke coordinates' for r in rows)
        assert any(r['kind']=='action' and 'Project tabs' in r['label'] for r in rows)
        bridge.close()
        stroke.destroy()
        root.destroy()
    from openvoice.studio_desk import DesktopStudio
    installed=[]
    original=DesktopStudio.__init__
    def capture(studio,*args):
        original(studio,*args)
        installed.append(studio)
    with tempfile.TemporaryDirectory() as room,patch.dict(os.environ,{'OPENMUKTI_NEURAL_HOME':str(Path(room)/'engines'),'OPENMUKTI_GPU_MODE':'cpu'}),patch.object(DesktopStudio,'__init__',capture),patch.object(tk.Tk,'mainloop',exercise):
        assert gui.main()==0
    assert len(results)==4
    print('Desktop smoke passed:',', '.join(results))
if __name__=='__main__':
    run()
