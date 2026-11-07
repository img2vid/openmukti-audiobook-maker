"""Run under xvfb-run. Opening and switching engines must never fetch files."""
import inspect
import tempfile
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import patch

import openvoice.gui as gui


def descendants(parent):
    for item in parent.winfo_children():
        yield item
        yield from descendants(item)


def exercise(root):
    app = inspect.currentframe().f_back.f_locals['app']
    errors = []
    root.report_callback_exception = lambda *exc: errors.append(exc)
    app.engine_var.set('kokoro')
    with patch('openvoice.engines.neural.download_neural_voice', side_effect=AssertionError('Unapproved download')):
        app.neural_voice_downloader()
        root.update()
        win = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and 'Manual Model Manager' in w.title())
        widgets = list(descendants(win))
        tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
        boxes = [w for w in widgets if isinstance(w, ttk.Combobox)]
        assert len(tree.get_children()) == 54
        assert 'Not downloaded' in str(tree.item(tree.get_children()[0], 'values'))
        boxes[0].set('kitten')
        boxes[0].event_generate('<<ComboboxSelected>>')
        root.update()
        assert len(tree.get_children()) == 8
        boxes[0].set('pocket')
        boxes[0].event_generate('<<ComboboxSelected>>')
        root.update()
        assert len(tree.get_children()) >= 20
        boxes[0].set('coqui')
        boxes[0].event_generate('<<ComboboxSelected>>')
        root.update()
        assert len(tree.get_children()) == 1
    assert not errors, errors
    print('GUI manual download manager smoke passed; no download on opening or switching engines.')
    app.close()

with tempfile.TemporaryDirectory() as home, \
     patch.dict('os.environ', {'OPENMUKTI_NEURAL_HOME': home}), \
     patch.object(tk.Tk, 'mainloop', exercise):
    assert gui.main() == 0
