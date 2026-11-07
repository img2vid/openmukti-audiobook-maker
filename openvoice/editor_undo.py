"""Group a Text-widget delete plus insert into one undoable replacement."""
from contextlib import contextmanager


@contextmanager
def undo_group(editor):
    automatic = editor.cget('autoseparators')
    editor.edit_separator()
    editor.configure(autoseparators=False)
    try:
        yield
    finally:
        # Explicit separators alone do not prevent Tk inserting a boundary
        # between a delete and the following insert. Restore the prior setting
        # after closing the manually grouped transaction.
        editor.edit_separator()
        editor.configure(autoseparators=automatic)


def replace_text(editor, text, start='1.0', end='end'):
    with undo_group(editor):
        editor.delete(start, end)
        editor.insert(start, text)
