"""Run with xvfb-run to check GUI widgets without downloading models."""
import inspect
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
from pathlib import Path
import openvoice.gui as gui

def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)

def exercise(root):
    app=inspect.currentframe().f_back.f_locals['app']
    app.installed_voices_only_var.set(True)
    with patch('openvoice.neural_models.is_downloaded', side_effect=lambda e,m,v: v == 'af_heart'):
        self_filtered=app._filter_downloaded_voices('kokoro',['af_heart','af_alloy','af_bella'])
        assert self_filtered == ['af_heart'], self_filtered
    app.installed_voices_only_var.set(False)
    assert app._filter_downloaded_voices('kokoro',['af_heart','af_alloy']) == ['af_heart','af_alloy']
    app.manage_sound_effects()
    root.update()
    windows=[w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and 'sound effects' in w.title().lower()]
    assert windows
    captions=[w.cget('text') for w in descendants(windows[0]) if isinstance(w,ttk.Button)]
    assert any('Import sounds' in x for x in captions), captions
    windows[0].destroy()
    app.close()
    print('GUI installed-only neural filter and sound importer smoke passed')

with tempfile.TemporaryDirectory() as home, patch.dict('os.environ',{'OPENMUKTI_NEURAL_HOME':home}),patch.object(tk.Tk,'mainloop',exercise):
    assert gui.main() == 0
