"""Tk OCR import and spelling review. All widget access stays on the UI thread."""
from __future__ import annotations

import queue
import bisect
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from .ocr import OCRCancelled, OCRResult, OCRSettings, import_ocr, natural_key
from .spelling import EnglishSpeller, apply_corrections
from .editor_undo import undo_group, replace_text


class SpellingController:
    def __init__(self, root, editor, status, *, changed=None):
        self.root, self.editor, self.status = root, editor, status
        self.changed = changed or (lambda: None)
        self.personal = set()
        self.enabled = True
        self.ocr = True
        self.check_names = False
        self.issues, self.snapshot = [], ''
        self.generation = 0
        self.pending = None
        self.cancel = threading.Event()
        self.results = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='openmukti-spelling')
        self.popup = None
        self._click_origin = None
        self._popup_after = None
        self.closed = False
        self.checker = None
        self._astral = []
        self._utf16_indices = int(root.tk.call('string', 'length', '\U0001f338')) == 2
        import tkinter as tk
        try:
            self.editor.tag_configure('ocr_spelling', underline=True, underlinefg='#ff7272')
        except tk.TclError:
            # Older Tk builds lack independent underline colors.
            self.editor.tag_configure('ocr_spelling', underline=True, foreground='#ff7272')
        self.editor.tag_configure('ocr_word', background='#594329')
        # Ordinary clicks belong to Text: caret placement, word selection and
        # dragging must never open a spelling popup or consume the event.
        self.editor.bind('<ButtonPress-1>', self._start_click, add='+')
        self.editor.bind('<Control-ButtonPress-1>', self._start_click, add='+')
        self.editor.bind('<Control-ButtonRelease-1>', self.show_at_click, add='+')
        self.editor.bind('<Button-3>', self.show_at_context, add='+')
        if root.tk.call('tk', 'windowingsystem') == 'aqua':
            self.editor.bind('<Button-2>', self.show_at_context, add='+')
        self.editor.bind('<Control-period>', self.show_at_cursor, add='+')
        self.editor.bind('<Shift-F10>', self.show_at_cursor, add='+')
        self.editor.bind('<KeyPress-Menu>', self.show_at_cursor, add='+')
        self.editor.bind('<Escape>', self.dismiss_popup, add='+')
        self.editor.bind('<<Modified>>', self._modified, add='+')
        self.editor.edit_modified(False)
        self.poll_id = self.root.after(100, self._poll)

    def text(self):
        return self.editor.get('1.0', 'end-1c')

    def _modified(self, _event=None):
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        self.changed()
        self.hide_popup()
        self.schedule()

    def schedule(self):
        if self.closed:
            return
        self.generation += 1
        self.cancel.set()
        if self.pending:
            self.root.after_cancel(self.pending)
        if self.enabled:
            self.pending = self.root.after(700, self.check)

    def check(self, *, correct=False, safe_only=False):
        if self.closed:
            return
        if self.pending:
            self.root.after_cancel(self.pending)
            self.pending = None
        self.generation += 1
        generation = self.generation
        self.cancel.set()
        cancel = self.cancel = threading.Event()
        snapshot, personal = self.text(), tuple(self.personal)
        ocr, check_names = self.ocr, self.check_names
        if correct:
            self.status.set('Checking English and applying OCR corrections…')
        def work():
            if cancel.is_set():
                return
            try:
                if self.checker is None:
                    self.checker = EnglishSpeller()
                self.checker.personal.update(w.casefold() for w in personal)
                issues = self.checker.check(snapshot, ocr=ocr, check_names=check_names, cancel=cancel)
                if not cancel.is_set():
                    fixed = apply_corrections(snapshot, issues, safe_only=safe_only) if correct else None
                    self.results.put((generation, snapshot, issues, fixed, None))
            except Exception as exc:
                self.results.put((generation, snapshot, [], None, str(exc)))
        self.executor.submit(work)

    def correct_all(self, *, safe_only=False):
        self.check(correct=True, safe_only=safe_only)

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                generation, text, issues, fixed, error = self.results.get_nowait()
                if generation != self.generation or self.text() != text:
                    continue
                if error:
                    self.status.set('Spelling check failed: ' + error)
                    continue
                if fixed is not None:
                    if fixed[1]:
                        self.apply_text(fixed[0])
                    self.status.set(f'Applied {fixed[1]} OCR/spelling corrections. Undo with Ctrl+Z; review remaining underlined words.')
                    if not fixed[1]:
                        self._mark(text, issues)
                else:
                    self._mark(text, issues)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self._poll)

    def _mark(self, text, issues):
        self.snapshot, self.issues = text, issues
        self._astral = [m.start() for m in re.finditer('[\U00010000-\U0010ffff]', text)] if self._utf16_indices else []
        self.editor.tag_remove('ocr_spelling', '1.0', 'end')
        # Batch Tcl commands keep long books responsive.
        pairs = []
        for issue in issues:
            pairs.extend((self._index(issue.start), self._index(issue.end)))
        for start in range(0, len(pairs), 600):
            self.editor.tag_add('ocr_spelling', *pairs[start:start + 600])

    def _index(self, offset):
        return f'1.0+{offset + bisect.bisect_left(self._astral, offset)}c'

    def apply_text(self, text):
        view = self.editor.yview()
        replace_text(self.editor, text)
        if view:
            self.editor.yview_moveto(view[0])
        self.changed()
        self.schedule()

    def hide_popup(self):
        if self._popup_after is not None:
            self.root.after_cancel(self._popup_after)
            self._popup_after = None
        if self.popup:
            self.popup.destroy()
            self.popup = None
        self.editor.tag_remove('ocr_word', '1.0', 'end')

    def _start_click(self, event):
        self._click_origin = (event.x, event.y)
        self.hide_popup()

    def dismiss_popup(self, _event=None):
        was_open = self.popup is not None
        self.hide_popup()
        if was_open:
            self.editor.focus_set()
            return 'break'

    def show_at_context(self, event):
        self._click_origin = None
        return self.show_at_click(event)

    def show_at_click(self, event):
        origin, self._click_origin = self._click_origin, None
        if origin and (abs(event.x - origin[0]) > 4 or abs(event.y - origin[1]) > 4):
            return  # Keep drag selection working normally.
        index = self.editor.index(f'@{event.x},{event.y}')
        bounds = self.editor.bbox(index)
        if not bounds or not (bounds[0] <= event.x < bounds[0] + bounds[2]
                              and bounds[1] <= event.y < bounds[1] + bounds[3]):
            self.hide_popup()
            return  # Tk otherwise maps clicks in blank space to the last word.
        self.hide_popup()
        if self.text() != self.snapshot:
            self.schedule()
            return
        offset = len(self.editor.get('1.0', index))
        if not any(issue.start <= offset < issue.end for issue in self.issues):
            return  # Preserve the platform's context behavior on correct text.
        def open_popup():
            self._popup_after = None
            if self.closed or not self.editor.winfo_exists():
                return
            import tkinter as tk
            try:
                self.show_issue(index)
            except tk.TclError as exc:
                self.hide_popup()
                self.status.set('Could not display spelling suggestions: ' + str(exc))
        # Let the Text class finish its release/selection handling first.
        self._popup_after = self.root.after_idle(open_popup)
        return 'break'

    def show_at_cursor(self, _event=None):
        result = self.show_issue(self.editor.index('insert'))
        if self.popup is not None:
            buttons = self.popup.winfo_children()[0].winfo_children()
            first = next((widget for widget in buttons if widget.winfo_class() == 'TButton'), None)
            if first is not None:
                first.focus_set()
        return result

    def show_issue(self, index):
        import tkinter as tk
        from tkinter import ttk
        self.hide_popup()
        if self.text() != self.snapshot:
            self.schedule()
            return
        offset = len(self.editor.get('1.0', index))
        issue = next((i for i in self.issues if i.start <= offset < i.end), None)
        if not issue:
            return
        owner = self.editor.winfo_toplevel()
        popup = self.popup = tk.Toplevel(owner)
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(owner)
        popup.configure(bg='#64748b', padx=1, pady=1)
        box = tk.Frame(popup, bg='#1f2937', padx=12, pady=10)
        box.pack(fill='both', expand=True)
        tk.Label(box, text=issue.original.replace('\n', ' '), font=('Segoe UI', 12, 'bold'), bg='#1f2937', fg='#ff9d9d', wraplength=340).pack(anchor='w')
        tk.Label(box, text=issue.message, bg='#1f2937', fg='#e5e7eb', wraplength=340, justify='left').pack(anchor='w', pady=(3, 7))
        if not issue.suggestions:
            tk.Label(box, text='No reliable suggestion. Edit the word or add it below.', bg='#1f2937', fg='#aab4c5', wraplength=340).pack(anchor='w')
        for suggestion in issue.suggestions:
            ttk.Button(box, text=suggestion or '(remove character)', command=lambda replacement=suggestion: self.replace_issue(issue, replacement)).pack(fill='x', pady=1)
        ttk.Button(box, text='Add / ignore this word in this project', command=lambda: self.add_word(issue.original)).pack(fill='x', pady=(8, 1))
        ttk.Button(box, text='Close', command=self.dismiss_popup).pack(fill='x')
        self.editor.tag_add('ocr_word', self._index(issue.start), self._index(issue.end))
        popup.update_idletasks()
        bounds = self.editor.bbox(self._index(issue.start)) or (0, 0, 0, 20)
        x = self.editor.winfo_rootx() + bounds[0]
        y = self.editor.winfo_rooty() + bounds[1] + bounds[3] + 6
        if y + popup.winfo_reqheight() > self.root.winfo_screenheight():
            y -= popup.winfo_reqheight() + bounds[3] + 12
        x = max(0, min(x, self.root.winfo_screenwidth() - popup.winfo_reqwidth()))
        popup.geometry(f'+{x}+{max(0,y)}')
        popup.bind('<Escape>', self.dismiss_popup)
        popup.deiconify()
        popup.lift()
        return 'break'

    def replace_issue(self, issue, replacement):
        current = self.text()
        self.hide_popup()
        if current != self.snapshot or current[issue.start:issue.end] != issue.original:
            self.schedule()
            return
        start = self._index(issue.start)
        replace_text(self.editor, replacement, start, self._index(issue.end))
        length = int(self.editor.tk.call('string', 'length', replacement))
        self.editor.mark_set('insert', f'{start}+{length}c')
        self.editor.see('insert')
        self.editor.focus_set()
        self.changed()
        self.schedule()

    def add_word(self, word):
        self.personal.add(word.casefold())
        self.hide_popup()
        self.editor.focus_set()
        self.check()

    def restore(self, settings):
        self.personal = {str(w).casefold() for w in settings.get('spelling_words', [])}
        # Reset the worker's per-project learned words without touching a
        # checker that may currently be running.
        self.cancel.set()
        self.executor.submit(self._reset_checker)
        self.enabled = bool(settings.get('spelling_enabled', True))
        self.ocr = bool(settings.get('spelling_ocr', True))
        self.check_names = bool(settings.get('spelling_names', False))
        self.schedule()

    def _reset_checker(self):
        self.checker = None

    def settings(self):
        return {'spelling_words': sorted(self.personal), 'spelling_enabled': self.enabled, 'spelling_ocr': self.ocr, 'spelling_names': self.check_names}

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.hide_popup()
        if self.pending:
            self.root.after_cancel(self.pending)
        self.root.after_cancel(self.poll_id)
        self.executor.shutdown(wait=False, cancel_futures=True)


def show_ocr_import(app, paths=None, *, insert=False, as_book=False):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    if getattr(app, '_ocr_running', False):
        messagebox.showinfo('OCR import', 'An OCR import is already running.', parent=app.root)
        return
    if paths is None:
        paths = filedialog.askopenfilenames(parent=app.root, title='Import scanned PDF / image book', filetypes=[('Scans and image books', '*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.zip *.cbz *.pnm *.pgm *.ppm'), ('All files', '*.*')])
    if not paths:
        return
    paths = sorted((Path(p) for p in paths), key=natural_key)
    window, panel = app._dialog('Tesseract OCR — Import scans and image books', 760, 730, min_width=520, min_height=450)
    ttk.Label(panel, text='OCR IMPORT', style='Title.TLabel').pack(anchor='w')
    ttk.Label(panel, text='\n'.join(p.name for p in paths[:5]) + (f'\n+ {len(paths)-5} more' if len(paths)>5 else ''), wraplength=650).pack(anchor='w', pady=6)
    saved = getattr(app, 'ocr_settings', {})
    variables = {}
    def field(label, key, default, choices=None):
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=27).pack(side='left')
        var = tk.StringVar(value=str(saved.get(key, default)))
        variables[key] = var
        widget = ttk.Combobox(row, textvariable=var, values=choices, state='readonly') if choices else ttk.Entry(row, textvariable=var)
        widget.pack(side='left', fill='x', expand=True)
        return var
    field('Language codes', 'language', 'eng')
    field('PDF rendering DPI', 'dpi', 300, [150, 200, 300, 400, 600])
    field('Image preprocessing', 'preprocessing', 'auto', ['auto', 'adaptive', 'otsu', 'contrast', 'original'])
    field('Contrast (0.5–3)', 'contrast', 1.4)
    field('Segmentation (3=book, 6=block)', 'psm', 3, [3, 4, 6, 11, 12])
    field('First source page', 'first_page', 1)
    field('Last source page (0=all)', 'last_page', 0)
    for label, key, default in [('Remove speckle noise', 'denoise', True), ('Deskew tilted text', 'deskew', True), ('Detect rotated pages (requires osd data)', 'auto_rotate', True), ('Split wide two-page spreads (left then right)', 'split_spreads', False), ('Force OCR even if a PDF page has text', 'force_ocr', False)]:
        var = tk.BooleanVar(value=bool(saved.get(key, default)))
        variables[key] = var
        ttk.Checkbutton(panel, text=label, variable=var).pack(anchor='w', pady=2)
    book_var = tk.BooleanVar(value=as_book)
    ttk.Checkbutton(panel, text='Also add this scan import to Book Studio', variable=book_var).pack(anchor='w', pady=4)
    ttk.Label(panel, text='Auto tries adaptive black-and-white and contrast cleanup when confidence is low. ZIP/folder pages use natural filename order. Ctrl+Z undoes an import or correction.', wraplength=650, style='Muted.TLabel').pack(anchor='w', pady=6)
    status = tk.StringVar(value='Ready. OCR runs locally on the CPU.')
    ttk.Label(panel, textvariable=status, wraplength=650).pack(anchor='w', pady=5)
    progress = ttk.Progressbar(panel, mode='indeterminate')
    progress.pack(fill='x', pady=4)
    actions = ttk.Frame(panel)
    actions.pack(fill='x', pady=8)
    cancel = threading.Event()
    incoming = queue.Queue()
    running = [False]
    before = [None]
    def dismiss():
        if running[0]:
            cancel.set()
            status.set('Cancelling OCR…')
        else:
            window.destroy()
    window.protocol('WM_DELETE_WINDOW', dismiss)
    def start():
        try:
            settings = OCRSettings(**{k: (v.get() if k not in {'dpi','psm','first_page','last_page','contrast'} else float(v.get()) if k == 'contrast' else int(v.get())) for k,v in variables.items()})
            settings.validate()
        except Exception as exc:
            messagebox.showerror('OCR settings', str(exc), parent=window)
            return
        app.ocr_settings = asdict(settings)
        before[0] = app._get_text()
        running[0] = app._ocr_running = True
        app._ocr_cancel = cancel
        start_button.configure(state='disabled')
        progress.start(12)
        add_to_books = book_var.get()
        def work():
            result = OCRResult()
            try:
                for index, path in enumerate(paths, 1):
                    def report(page, total, message):
                        incoming.put(('progress', f'File {index}/{len(paths)} · page {page}: {message}'))
                    part = import_ocr(path, settings, progress=report, cancel=cancel)
                    result.pages.extend(part.pages)
                    result.warnings.extend(part.warnings)
                incoming.put(('done', result, add_to_books))
            except Exception as exc:
                incoming.put(('error', exc))
        threading.Thread(target=work, name='openmukti-ocr-import', daemon=True).start()
    def poll():
        if not window.winfo_exists():
            return
        try:
            while True:
                event = incoming.get_nowait()
                if event[0] == 'progress':
                    status.set(event[1])
                else:
                    running[0] = app._ocr_running = False
                    progress.stop()
                    start_button.configure(state='normal')
                    if event[0] == 'error':
                        status.set(str(event[1]))
                        if not isinstance(event[1], OCRCancelled):
                            messagebox.showerror('OCR import failed', str(event[1]), parent=window)
                        cancel.clear()
                        continue
                    result, add_to_books = event[1], event[2]
                    if cancel.is_set():
                        status.set('OCR cancelled; no text was applied.')
                        cancel.clear()
                        continue
                    app.ocr_report = result.to_dict()
                    # Never overwrite text typed while the CPU worker was busy.
                    if app._get_text() != before[0] and not insert:
                        insert_result = True
                        app.status_var.set('Editor changed during OCR; recognized text was appended.')
                    else:
                        insert_result = insert
                    with undo_group(app.editor):
                        if not insert_result:
                            app.editor.delete('1.0', 'end')
                            app.editor.insert('1.0', result.text)
                        else:
                            app.editor.insert('end-1c', '\n\n' + result.text)
                    app.current_file = paths[0] if len(paths) == 1 else None
                    app.ocr_var.set(True)
                    app.spelling.ocr = True
                    app.spelling.check()
                    app.update_stats()
                    if add_to_books:
                        from .audiobooks import Book, Chapter
                        from .chaptering import split_chapters
                        chapters = [Chapter(title, [], text=body) for title, body in split_chapters(result.text)]
                        app.books.append(Book(paths[0].stem, chapters))
                    confidence = f' · {result.confidence:.0f}% estimated confidence' if result.confidence is not None else ''
                    app.status_var.set(f'Imported {len(result.pages)} pages{confidence}. Edit freely; right-click an underlined word for suggestions.')
                    if result.warnings:
                        messagebox.showwarning('OCR pages to review', '\n'.join(result.warnings[:15]), parent=window)
                    window.destroy()
                    return
        except queue.Empty:
            pass
        window.after(100, poll)
    start_button = ttk.Button(actions, text='Start OCR import', command=start, style='Accent.TButton')
    start_button.pack(side='left')
    ttk.Button(actions, text='Cancel / Close', command=dismiss).pack(side='right')
    window.after(100, poll)
    return window


def show_spelling_settings(app):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    window, panel = app._dialog('English spelling and OCR correction', 620, 490)
    spelling = app.spelling
    ttk.Label(panel, text='ENGLISH SPELLING', style='Title.TLabel').pack(anchor='w')
    for label, attr in [('Check English while editing', 'enabled'), ('Include OCR restoration rules', 'ocr'), ('Also check capitalized names', 'check_names')]:
        var = tk.BooleanVar(value=getattr(spelling, attr))
        def update(attribute=attr, variable=var):
            setattr(spelling, attribute, variable.get())
            if not spelling.enabled:
                spelling.editor.tag_remove('ocr_spelling', '1.0', 'end')
            else:
                spelling.check()
        ttk.Checkbutton(panel, text=label, variable=var, command=update).pack(anchor='w', pady=4)
    ttk.Label(panel, text='Click to edit, double-click to select a word, or drag to select text. Right-click or Ctrl-click an underlined word for spelling suggestions. You can also place the cursor in the word and press Shift+F10 or Ctrl+period. Correct all uses the top suggestion; uncertain words without suggestions stay marked. All changes can be undone.', wraplength=550, style='Muted.TLabel').pack(anchor='w', pady=12)
    def import_words():
        path = filedialog.askopenfilename(parent=window, title='Import personal English words (one per line)', filetypes=[('Word lists', '*.txt *.dic')])
        if not path:
            return
        try:
            if Path(path).stat().st_size > 5 * 1024 * 1024:
                raise ValueError('Personal word list must be smaller than 5 MiB.')
            for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
                word = line.strip().split('/')[0]
                if word and not word.isdigit() and not word.startswith('#'):
                    spelling.personal.add(word.casefold())
            spelling.check()
            count.set(f'{len(spelling.personal):,} personal words saved with this project.')
        except Exception as exc:
            messagebox.showerror('Word list', str(exc), parent=window)
    count = tk.StringVar(value=f'{len(spelling.personal):,} personal words saved with this project.')
    ttk.Label(panel, textvariable=count).pack(anchor='w', pady=8)
    ttk.Button(panel, text='Import personal word list…', command=import_words).pack(fill='x', pady=3)
    ttk.Button(panel, text='Check English now', command=spelling.check).pack(fill='x', pady=3)
    ttk.Button(panel, text='Correct all OCR / spelling suggestions', command=spelling.correct_all).pack(fill='x', pady=3)
    ttk.Button(panel, text='Apply high-confidence corrections only', command=lambda: spelling.correct_all(safe_only=True)).pack(fill='x', pady=3)
    ttk.Button(panel, text='Close', command=window.destroy).pack(fill='x', pady=8)


def show_chapter_review(app, chapter, on_save=lambda: None):
    """Use the same in-text corrections on the exact text Book Studio exports."""
    import tkinter as tk
    from tkinter import ttk, messagebox
    from .documents import read_document
    window, panel = app._dialog('Review chapter OCR — ' + chapter.title, 900, 710, scroll=False)
    ttk.Label(panel, text=chapter.title, style='Title.TLabel').pack(anchor='w')
    ttk.Label(panel, text='Click to edit; double-click or drag to select text. Right-click or Ctrl-click an underlined word for suggestions, or press Shift+F10 at the cursor. Save updates the chapter used for audio/video export.', wraplength=780, style='Muted.TLabel').pack(anchor='w', pady=5)
    actions = ttk.Frame(panel)
    actions.pack(fill='x', pady=6)
    state = tk.StringVar(value='Ready')
    ttk.Label(panel, textvariable=state, wraplength=780).pack(side='bottom', anchor='w')
    editor = tk.Text(panel, wrap='word', undo=True, bg=app.FIELD, fg=app.FG, insertbackground=app.ACCENT, padx=12, pady=12, font=('Segoe UI', 12))
    editor.pack(fill='both', expand=True, side='left')
    scrollbar = ttk.Scrollbar(panel, command=editor.yview)
    scrollbar.pack(fill='y', side='right')
    editor.configure(yscrollcommand=scrollbar.set)
    spelling = SpellingController(app.root, editor, state)
    spelling.restore(app.spelling.settings())
    controllers = getattr(app, '_chapter_spelling', None)
    if controllers is None:
        app._chapter_spelling = controllers = []
    controllers.append(spelling)
    loaded = [chapter.text_file is None]
    def close():
        spelling.close()
        if spelling in controllers:
            controllers.remove(spelling)
        window.destroy()
    def save():
        if not loaded[0]:
            return
        chapter.text = editor.get('1.0', 'end-1c')
        chapter.text_file = None
        app.spelling.personal.update(spelling.personal)
        on_save()
        close()
    window.protocol('WM_DELETE_WINDOW', close)
    ttk.Button(actions, text='Check English', command=spelling.check).pack(side='left', padx=2)
    ttk.Button(actions, text='Correct all OCR', command=spelling.correct_all).pack(side='left', padx=2)
    ttk.Button(actions, text='Undo', command=lambda: editor.event_generate('<<Undo>>')).pack(side='left', padx=2)
    save_button = ttk.Button(actions, text='Save chapter', command=save, style='Accent.TButton')
    save_button.pack(side='right', padx=2)
    ttk.Button(actions, text='Cancel', command=close).pack(side='right', padx=2)
    if loaded[0]:
        editor.insert('1.0', chapter.text)
        spelling.check()
    else:
        save_button.configure(state='disabled')
        state.set('Reading chapter document…')
        incoming = queue.Queue()
        def work():
            try:
                incoming.put((read_document(chapter.text_file), None))
            except Exception as exc:
                incoming.put(('', str(exc)))
        def poll():
            if not window.winfo_exists():
                return
            try:
                text, error = incoming.get_nowait()
            except queue.Empty:
                window.after(100, poll)
                return
            if error:
                messagebox.showerror('Read chapter', error, parent=window)
                close()
                return
            editor.insert('1.0', text)
            loaded[0] = True
            save_button.configure(state='normal')
            state.set('Chapter loaded. Review OCR and spelling before saving.')
            spelling.check()
        threading.Thread(target=work, daemon=True).start()
        window.after(100, poll)
    return window
