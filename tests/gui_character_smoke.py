import inspect
import time
import threading
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import openvoice.gui as gui

errors = []
messages = []


def descendants(widget):
    out = []
    for child in widget.winfo_children():
        out.append(child)
        out.extend(descendants(child))
    return out


def exercise(root):
    app = inspect.currentframe().f_back.f_locals["app"]
    root.report_callback_exception = lambda *e: errors.append(str(e))
    app._replace_text(
        'Alice, a 14-year-old girl, whispered slowly, "Hello." "Stay," said the old man. The old man was named Elias.'
    )
    app.character_voice_studio()
    root.update()
    studio = next(
        w
        for w in root.winfo_children()
        if isinstance(w, tk.Toplevel) and w.title().startswith("Character Voices")
    )
    widgets = descendants(studio)
    tree = next(w for w in widgets if isinstance(w, ttk.Treeview))
    editor = next(w for w in widgets if isinstance(w, tk.Text))
    buttons = {w.cget("text"): w for w in widgets if isinstance(w, ttk.Button)}

    def pump(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(0.01)
        raise AssertionError("GUI operation timed out")

    buttons["Find Characters"].invoke()
    pump(
        lambda: (
            {tree.item(i, "text") for i in tree.get_children()}
            == {"Narrator", "Alice", "Elias"}
        )
    )
    alice = next(i for i in tree.get_children() if tree.item(i, "text") == "Alice")
    tree.selection_set(alice)
    root.update()
    spinboxes = [w for w in widgets if isinstance(w, ttk.Spinbox)]
    assert [w.get() for w in spinboxes] == ["-2", "82", "0"], [
        w.get() for w in spinboxes
    ]
    spinboxes[1].delete(0, "end")
    spinboxes[1].insert(0, "76")
    buttons["Save / Add Profile"].invoke()
    root.update()
    p = next(p for p in app.voice_project.profiles if p.name == "Alice")
    assert p.volume == 76 and "volume" in p.locked_fields
    buttons["Find Characters"].invoke()
    pump(
        lambda: (
            not any(
                w
                for w in descendants(studio)
                if isinstance(w, ttk.Progressbar)
                and str(w.cget("mode")) == "indeterminate"
                and w["value"] != 0
            )
        )
    )
    # Pump until worker has been applied, then inspect evidence.
    for _ in range(20):
        root.update()
        time.sleep(0.01)
    assert next(p for p in app.voice_project.profiles if p.name == "Alice").volume == 76
    buttons["Review Characters / Quotes"].invoke()
    root.update()
    report = next(
        w
        for w in root.winfo_children()
        if isinstance(w, tk.Toplevel) and w.title() == "Character and quote evidence"
    )
    text = next(w for w in descendants(report) if isinstance(w, tk.Text)).get(
        "1.0", "end"
    )
    assert "manual setting" in text and "QUOTATION ATTRIBUTION" in text
    report.destroy()
    # Invalid user input is reported without crashing a Tk variable trace.
    spinboxes[2].delete(0, "end")
    spinboxes[2].insert(0, "invalid")
    buttons["Save / Add Profile"].invoke()
    root.update()
    assert messages, "No validation message for invalid spinbox"
    spinboxes[2].delete(0, "end")
    spinboxes[2].insert(0, "0")
    # The asynchronous worker must never replace text edited during its scan.
    gate = threading.Event()
    actual = gui.auto_profiles

    def delayed(*args, **kwargs):
        assert gate.wait(5)
        return actual(*args, **kwargs)

    with patch.object(gui, "auto_profiles", delayed):
        buttons["Find Characters"].invoke()
        editor.insert("end", " The editor changed during analysis.")
        changed = editor.get("1.0", "end-1c")
        gate.set()
        labels = [
            w for w in widgets if isinstance(w, ttk.Label) and w.cget("textvariable")
        ]
        pump(
            lambda: any(
                "Script changed during analysis"
                in str(root.getvar(w.cget("textvariable")))
                for w in labels
            )
        )
        assert editor.get("1.0", "end-1c") == changed
    assert not errors, errors
    print(
        "GUI smoke passed: detection, aliases, every visible profile field, repeated scan, evidence, manual overrides, invalid numeric entry, stale worker result rejection."
    )
    app.close()


with (
    patch.object(tk.Tk, "mainloop", exercise),
    patch(
        "tkinter.messagebox.showerror", side_effect=lambda *a, **k: messages.append(a)
    ),
):
    assert gui.main() == 0
