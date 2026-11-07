from __future__ import annotations
import os
import copy
import tempfile
import queue
import threading
from pathlib import Path
from .documents import read_document, use_scan_dialog
from .engines import RunControl, SpeechSettings, all_engines, get_engine
from .service import JobOptions, render_text, speak_text
from .texttools import TOOLS, transform, text_stats
from . import narration_text as _narration_text  # registers speech-preparation text tools
from .audiofx import process_audio
from .video import VideoOptions, render_video, ASPECTS, HEIGHTS, video_size
from .animated_video import MODES
from .edition import APP_NAME, GUTENBERG_ENABLED, VERSION
from .piper_models import install_voice, discover_voices, get_voice, voice_directory, PiperSpeaker, speaker_list, speaker_label, speaker_id_from_label
from .character_voices import VoiceProject, CharacterProfile, auto_profiles, detected_languages, recommend_voices, merge_auto_profiles, profile_aliases, read_name_list, PROFILE_FIELDS
from .dialogue_analysis import analyze_dialogue
from .voice_catalog import fetch_catalog, download_selected, catalog_languages, voice_download_size, cached_catalog, catalog_voice, ensure_piper_voice
from .multivoice import render_multivoice, render_multivoice_video
from .project_archive import ProjectData, save_project, load_project
from .voice_design import design_for_profile, STYLE_DESIGNS
from .windowing import fit_window, keep_window_visible, scrollable_area, adaptive_grid
from .ocr_ui import SpellingController, show_ocr_import, show_spelling_settings, show_chapter_review
from .ocr import SCAN_EXTENSIONS
from .progress import emit, subprogress
from .editor_undo import replace_text
if GUTENBERG_ENABLED:
    from .gutenberg import clean_gutenberg, GutenbergOptions
from .audiobooks import Book, BookExportOptions, discover_books, load_manifest, export_books, _split_ebook, _match_cover, _files

def main(*, on_ready=None) -> int:
    from .desktop_prefs import activate
    activate()
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk, simpledialog
    except ImportError:
        print(f'{APP_NAME} requires Tkinter. On Debian/Ubuntu: sudo apt install python3-tk')
        return 1

    class App:
        BG = '#111827'
        CARD = '#1f2937'
        FIELD = '#0f172a'
        FG = '#e5e7eb'
        MUTED = '#aab4c5'
        ACCENT = '#20c997'

        def __init__(self, root):
            self.root = root
            from tkinter import font as tkfont
            self.ui_font=tkfont.nametofont('TkDefaultFont',root=root).actual()['family']
            self.root.title(f'{APP_NAME} — Version {VERSION}')
            fit_window(self.root, 1150, 750, 650, 430)
            self.root.configure(bg=self.BG)
            self.events: queue.Queue = queue.Queue()
            self.active = False
            self.control: RunControl | None = None
            self.current_file: Path | None = None
            self._saved_text=''
            self.engines = all_engines()
            self._piper_catalog = cached_catalog()
            self._voice_refresh_serial = 0
            self.voice_project = VoiceProject()
            self.books = []
            self.book_export_settings = {}
            self.video_images = []
            self.video_audio = None
            self.video_options = {}
            self.backup_folder = None
            self.backup_timer = None
            self.previous_backup = None
            self.project_file = None
            self.autosave_timer = None
            self._project_workspace = None
            self.ocr_settings = {}
            self.ocr_report = {}
            self._ocr_running = False
            self._ocr_cancel = None
            self.active_character_var = tk.StringVar(value='Narrator')
            self.use_character_voices_var = tk.BooleanVar(value=True)
            self._icon = None
            self._set_icon()
            self.engine_var = tk.StringVar(value='auto')
            self.voice_var = tk.StringVar()
            self.installed_voices_only_var = tk.BooleanVar(value=False)
            self.model_var = tk.StringVar()
            self.tts_language_var = tk.StringVar(value='auto')
            self.speaker_var = tk.StringVar(value="Speaker 0")
            self.dict_var = tk.StringVar()
            self.ipa_dict_var = tk.StringVar()
            self.rate_var = tk.IntVar(value=0)
            self.pitch_var = tk.IntVar(value=0)
            self.volume_var = tk.IntVar(value=100)
            self.ocr_var = tk.BooleanVar(value=False)
            self.status_var = tk.StringVar(value='Ready · Offline speech')
            self.progress_percent_var = tk.StringVar(value='0%')
            self.stage_percent_var = tk.StringVar(value='Ready')
            self.pause_var = tk.StringVar(value='Pause between sentences')
            self.counters_var = tk.StringVar(value='')
            self.font_size = 12
            self._styles()
            self._layout()
            self.spelling = SpellingController(self.root, self.editor, self.status_var, changed=self.update_stats)
            self._bindings()
            self._menus()
            self.root.after(600, self._watch_display)
            self.editor.bind('<KeyRelease>', lambda _event: self.update_stats())
            self.update_stats()
            self.refresh_voices()
            self.root.after(100, self.poll)
            self.root.protocol('WM_DELETE_WINDOW', self.close)

        def _dialog(self, title, width, height, *, min_width=480, min_height=360, padding=12, scroll=True):
            window = tk.Toplevel(self.root)
            window.title(title)
            fit_window(window, width, height, min_width, min_height)
            window.configure(bg=self.BG)
            self.root.after(650, lambda win=window: self._watch_dialog(win))
            if scroll:
                shell, panel, canvas = scrollable_area(window, padding=padding, background=self.BG)
                shell.pack(fill='both', expand=True)
                return window, panel
            panel = ttk.Frame(window, padding=padding)
            panel.pack(fill='both', expand=True)
            return window, panel

        def _watch_dialog(self, window):
            if not window.winfo_exists():
                return
            keep_window_visible(window)
            self.root.after(800, lambda win=window: self._watch_dialog(win))

        def _watch_display(self):
            if not self.root.winfo_exists():
                return
            keep_window_visible(self.root)
            compact = self.root.winfo_width() < 780 or self.root.winfo_height() < 540
            if compact != getattr(self, '_compact', None):
                self._compact = compact
                if compact:
                    self.secondary_toolbar.pack_forget()
                    self.subtitle.pack_forget()
                else:
                    self.subtitle.pack(anchor='w')
                    self.secondary_toolbar.pack(fill='x')
            self.root.after(800, self._watch_display)

        def _styles(self):
            style = ttk.Style()
            style.theme_use('clam')
            style.configure('TFrame', background=self.BG)
            style.configure('Panel.TFrame', background=self.CARD)
            style.configure('TLabel', background=self.BG, foreground=self.FG, font=(self.ui_font, 10))
            style.configure('Panel.TLabel', background=self.CARD, foreground=self.FG, font=(self.ui_font, 10))
            style.configure('Title.TLabel', background=self.BG, foreground=self.FG, font=(self.ui_font, 21, 'bold'))
            style.configure('Muted.TLabel', background=self.BG, foreground=self.MUTED, font=(self.ui_font, 10))
            style.configure('PanelTitle.TLabel', background=self.CARD, foreground=self.ACCENT, font=(self.ui_font, 12, 'bold'))
            style.configure('TButton', padding=(10, 8), font=(self.ui_font, 10), background='#334155', foreground=self.FG, borderwidth=0)
            style.map('TButton', background=[('active', '#45556e'), ('disabled', '#293343')], foreground=[('disabled', '#8190a3')])
            style.configure('Accent.TButton', background=self.ACCENT, foreground='#10231e', padding=(13, 9), font=(self.ui_font, 10, 'bold'))
            style.map('Accent.TButton', background=[('active', '#57e3bb')])
            style.configure('TCombobox', fieldbackground=self.FIELD, background='#334155', foreground=self.FG, arrowcolor=self.FG)
            style.map('TCombobox', fieldbackground=[('readonly', self.FIELD)], foreground=[('readonly', self.FG)], selectbackground=[('readonly', self.FIELD)], selectforeground=[('readonly', self.FG)])
            style.configure('TEntry', fieldbackground=self.FIELD, foreground=self.FG)
            style.configure('TCheckbutton', background=self.CARD, foreground=self.FG)
            style.map('TCheckbutton', background=[('active', self.CARD)])
            style.configure('Horizontal.TProgressbar', troughcolor='#334155', background=self.ACCENT, bordercolor='#334155')
            style.configure('Book.Treeview', background=self.FIELD, fieldbackground=self.FIELD, foreground=self.FG, borderwidth=0, rowheight=29)
            style.configure('Book.Treeview.Heading', background=self.CARD, foreground=self.ACCENT, font=(self.ui_font, 10, 'bold'), relief='flat')
            style.map('Book.Treeview', background=[('selected','#256c72')], foreground=[('selected','#ffffff')])
            style.configure('Treeview', background=self.FIELD, fieldbackground=self.FIELD, foreground=self.FG, borderwidth=0, rowheight=28)
            style.configure('Treeview.Heading', background=self.CARD, foreground=self.ACCENT, relief='flat')
            style.map('Treeview', background=[('selected','#256c72')], foreground=[('selected','#ffffff')])
            style.configure('TNotebook', background=self.BG, borderwidth=0)
            style.configure('TNotebook.Tab', background=self.CARD, foreground=self.FG, padding=(12,8))
            style.map('TNotebook.Tab', background=[('selected','#334155')], foreground=[('selected',self.ACCENT)])
            style.configure('TSpinbox', fieldbackground=self.FIELD, background=self.CARD, foreground=self.FG, arrowcolor=self.FG)

        def _layout(self):
            main = ttk.Frame(self.root, padding=18)
            main.pack(fill='both', expand=True)
            head = ttk.Frame(main)
            head.pack(fill='x', pady=(0, 5))
            ttk.Label(head, text=APP_NAME, style='Title.TLabel').pack(anchor='w')
            self.subtitle = ttk.Label(head, text='Create audiobooks · Cast voices · Design artwork · Mix sound', style='Muted.TLabel')
            self.subtitle.pack(anchor='w')
            toolbar = ttk.Frame(main)
            toolbar.pack(fill='x', pady=(0, 7))
            top_actions = [('Start creating', lambda:self.studio.home()), ('Open', self.open_file), ('Save', self.save_text), ('Text tools', self.tools_dialog), ('Find / Replace', self.find_replace)]
            more_actions = [('Combine Chapters', self.book_studio), ('Character Voices', self.character_voice_studio), ('Animated Audiobook Video', self.video_dialog), ('Statistics', self.show_stats)]
            if GUTENBERG_ENABLED:
                more_actions.append(('Gutenberg Mode', self.gutenberg_mode))
            for index, actions in enumerate((top_actions, more_actions)):
                bar = ttk.Frame(toolbar)
                if index == 1:
                    self.secondary_toolbar = bar
                bar.pack(fill='x')
                for label, callback in actions:
                    ttk.Button(bar, text=label, command=callback).pack(side='left', padx=(0, 3), pady=1)
            bottom = ttk.Frame(main)
            bottom.pack(side='bottom', fill='x')
            ttk.Label(bottom, textvariable=self.status_var, style='Muted.TLabel', wraplength=740, justify='left').pack(anchor='w')
            overall_row = ttk.Frame(bottom)
            overall_row.pack(fill='x', pady=(3, 0))
            ttk.Label(overall_row, text='Overall', width=12, style='Muted.TLabel').pack(side='left')
            self.progress = ttk.Progressbar(overall_row, orient='horizontal', mode='determinate', maximum=100)
            self.progress.pack(side='left', fill='x', expand=True, padx=(0, 8))
            ttk.Label(overall_row, textvariable=self.progress_percent_var, width=8, style='Muted.TLabel').pack(side='right')
            stage_row = ttk.Frame(bottom)
            stage_row.pack(fill='x', pady=(3, 3))
            ttk.Label(stage_row, text='Current stage', width=12, style='Muted.TLabel').pack(side='left')
            self.stage_progress = ttk.Progressbar(stage_row, orient='horizontal', mode='determinate', maximum=100)
            self.stage_progress.pack(side='left', fill='x', expand=True, padx=(0, 8))
            ttk.Label(stage_row, textvariable=self.stage_percent_var, width=8, style='Muted.TLabel').pack(side='right')
            stats = ttk.Frame(bottom)
            stats.pack(fill='x')
            ttk.Label(stats, textvariable=self.counters_var, style='Muted.TLabel').pack(side='left')

            controls = ttk.Frame(main)
            controls.pack(side='bottom', fill='x', pady=(5, 2))
            playback = ttk.Frame(controls)
            playback.pack(fill='x')
            actions = ttk.Frame(controls)
            actions.pack(fill='x')
            self.speak_btn = ttk.Button(playback, text='Speak', command=self.speak, style='Accent.TButton')
            self.speak_btn.pack(side='left', padx=(0, 4))
            self.pause_btn = ttk.Button(playback, textvariable=self.pause_var, command=self.pause)
            self.pause_btn.pack(side='left', padx=(0, 4))
            self.stop_btn = ttk.Button(playback, text='Stop', command=self.stop)
            self.stop_btn.pack(side='left', padx=(0, 4))
            self.export_btn = ttk.Button(actions, text='Export audio', command=self.export, style='Accent.TButton')
            self.export_btn.pack(side='left', padx=(0, 4), pady=(3, 0))
            self.video_btn = ttk.Button(actions, text='Video', command=self.video_dialog)
            self.video_btn.pack(side='left', padx=(0, 4), pady=(3, 0))
            self.batch_btn = ttk.Button(actions, text='Batch', command=self.batch)
            self.batch_btn.pack(side='left', padx=(0, 4), pady=(3, 0))
            work = ttk.Frame(main)
            work.pack(fill='both', expand=True)
            work.columnconfigure(0, weight=1)
            work.columnconfigure(1, weight=0, minsize=275)
            work.rowconfigure(0, weight=1)
            left = ttk.Frame(work)
            left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
            from .studio_windows import line
            editor_header = line(left)
            ttk.Label(editor_header, text='TEXT TO SPEAK').pack(side='left')
            ttk.Button(editor_header, text='Insert IPA', command=self.insert_inline_ipa).pack(side='right')
            ttk.Button(editor_header, text='Correct all OCR', command=lambda: self.spelling.correct_all()).pack(side='right', padx=3)
            ttk.Button(editor_header, text='Import scans', command=self.import_scans).pack(side='right', padx=3)
            editor_frame = tk.Frame(left, bg=self.FIELD, highlightthickness=1, highlightbackground='#334155')
            editor_frame.pack(fill='both', expand=True)
            self.editor = tk.Text(editor_frame, wrap='word', undo=True, bg=self.FIELD, fg='#f5f6fa', insertbackground=self.ACCENT, selectbackground='#256c72', relief='flat', padx=17, pady=15, height=1, width=1, font=(self.ui_font, 12), highlightthickness=0, spacing2=3, spacing3=7)
            scroll = ttk.Scrollbar(editor_frame, orient='vertical', command=self.editor.yview)
            self.editor.configure(yscrollcommand=scroll.set)
            self.editor.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')
            # Instructions belong in the task hub, never in the spoken manuscript.
            right_shell, right, _ = scrollable_area(work, padding=7, background=self.CARD, panel_style='Panel.TFrame')
            right_shell.grid(row=0, column=1, sticky='nsew')
            self.studio_editor_side,self.studio_settings_side=left,right_shell
            right.columnconfigure(0, weight=1)
            ttk.Label(right, text='VOICE SETTINGS', style='PanelTitle.TLabel').pack(fill='x', pady=(0, 6))
            ttk.Label(right, text='Speaker for untagged text', style='Panel.TLabel').pack(anchor='w')
            self.character_combo = ttk.Combobox(right, textvariable=self.active_character_var, values=['Narrator'], state='readonly')
            self.character_combo.pack(fill='x')
            ttk.Checkbutton(right, text='Apply character profiles to Speak / Audio / Video / Batch',variable=self.use_character_voices_var).pack(anchor='w', pady=(3, 2))
            ttk.Button(right, text='Edit all character voices', command=self.character_voice_studio).pack(fill='x',pady=(0,4))
            ttk.Button(right, text='Import / manage project sound effects', command=self.manage_sound_effects).pack(fill='x', pady=(0, 4))

            def label(s):
                ttk.Label(right, text=s, style='Panel.TLabel').pack(anchor='w', pady=(3, 1))
            label('Speech engine')
            choices = ['auto'] + list(self.engines)  # neural model weights require explicit GUI download
            self.engine_combo = ttk.Combobox(right, textvariable=self.engine_var, values=choices, state='readonly')
            self.engine_combo.pack(fill='x')
            self.engine_combo.bind('<<ComboboxSelected>>', lambda _ev: (self._update_piper_speakers(), self.refresh_voices()))
            label('Voice')
            self.voice_combo = ttk.Combobox(right, textvariable=self.voice_var)
            self.voice_combo.pack(fill='x')
            self.voice_combo.bind('<<ComboboxSelected>>', self._on_piper_voice_selected)
            self.voice_combo.configure(postcommand=self._update_voice_list_from_catalog)
            ttk.Checkbutton(right, text='Installed voices only', variable=self.installed_voices_only_var,
                            command=self.refresh_voices).pack(anchor='w', pady=(2, 0))
            self.voice_var.trace_add('write', lambda *_: self._update_piper_speakers())
            ttk.Button(right, text='Refresh voices / Piper catalog', command=self.refresh_voices).pack(fill='x', pady=(2, 0))
            ttk.Button(right, text='Install / repair selected neural engine (CPU)', command=self.install_neural_engine).pack(fill='x', pady=(3, 0))
            ttk.Label(right, text='Neural models never download during Speak, Preview or Export. Open the voice downloader and explicitly download your choices first.', style='Muted.TLabel', wraplength=330).pack(fill='x', pady=(3, 3))
            ttk.Button(right, text='Download Kokoro / Kitten / Pocket / Coqui voices', command=self.neural_voice_downloader).pack(fill='x', pady=(3, 0))
            ttk.Label(right, text='Piper catalog voices remain visible before download. Speak, Preview and Export ask permission before permanently installing missing voices. Manual downloads do not show confirmation or completion popups.', style='Muted.TLabel', wraplength=330).pack(fill='x', pady=(4, 2))
            ttk.Button(right, text='Download Piper voices by language', command=self.voice_downloader).pack(fill='x', pady=(4, 0))
            ttk.Button(right, text='Add local Piper model + configuration', command=self.add_piper_voice).pack(fill='x', pady=(3, 0))
            label('Model (Piper ONNX path, Kitten repository, or Coqui model ID; optional)')
            model_row = ttk.Frame(right, style='Panel.TFrame')
            model_row.pack(fill='x')
            ttk.Combobox(model_row, textvariable=self.model_var, values=['',
                'KittenML/kitten-tts-nano-0.8', 'KittenML/kitten-tts-micro-0.8',
                'KittenML/kitten-tts-mini-0.8', 'tts_models/en/ljspeech/tacotron2-DDC',
                'tts_models/en/vctk/vits','tts_models/multilingual/multi-dataset/xtts_v2',
                'english', 'english_18m_2026-10', 'english_7m_2026-10',
                'english_2m_2026-10', 'french', 'german', 'spanish',
                'portuguese', 'italian', 'dutch']).pack(side='left', fill='x', expand=True)
            ttk.Button(model_row, text='…', command=self.pick_model, width=3).pack(side='left', padx=(5, 0))
            ttk.Button(right, text='Discover Coqui speakers in selected model', command=self.discover_coqui_speakers).pack(fill='x', pady=(3,0))
            label('Piper speaker (used only for Piper multi-speaker models)')
            self.speaker_combo = ttk.Combobox(right, textvariable=self.speaker_var, state='readonly', values=['Speaker 0'])
            self.speaker_combo.pack(fill='x')
            self.model_var.trace_add('write', lambda *_: self._update_piper_speakers())
            label('Pocket / Coqui language (auto, en, fr, de, es, pt, it, nl; depends on model)')
            ttk.Entry(right, textvariable=self.tts_language_var).pack(fill='x')
            self._scale(right, 'Rate', self.rate_var, -10, 10)
            self._scale(right, 'Pitch (eSpeak NG)', self.pitch_var, -10, 10)
            self._scale(right, 'Volume', self.volume_var, 0, 100)
            label('Word substitutions')
            dicrow = ttk.Frame(right, style='Panel.TFrame')
            dicrow.pack(fill='x')
            ttk.Entry(dicrow, textvariable=self.dict_var).pack(side='left', fill='x', expand=True)
            ttk.Button(dicrow, text='…', command=self.pick_dictionary, width=3).pack(side='left', padx=(5, 0))
            ttk.Button(right,text='Edit word substitutions',command=self.pronunciation_editor).pack(fill='x',pady=(3,0))
            label('IPA pronunciations by language')
            iparow = ttk.Frame(right, style='Panel.TFrame')
            iparow.pack(fill='x')
            ttk.Entry(iparow,textvariable=self.ipa_dict_var).pack(side='left',fill='x',expand=True)
            ttk.Button(iparow,text='…',width=3,command=self.pick_ipa_dictionary).pack(side='left',padx=(5,0))
            ttk.Button(right,text='Edit IPA pronunciations',command=self.ipa_editor).pack(fill='x',pady=(3,0))
            ttk.Checkbutton(right, text='Clean OCR line wrapping', variable=self.ocr_var).pack(anchor='w', pady=(6, 0))
            ttk.Label(right, text='Pause starts at the next chunk.', style='Panel.TLabel').pack(anchor='w', pady=(4, 0))
        def _scale(self, parent, label_text, variable, minimum, maximum):
            group = ttk.Frame(parent, style='Panel.TFrame')
            group.pack(fill='x', pady=(4, 0))
            ttk.Label(group, text=label_text, style='Panel.TLabel').pack(side='left')
            val_label = ttk.Label(group, textvariable=variable, style='Panel.TLabel')
            val_label.pack(side='right')
            tk.Scale(parent, variable=variable, from_=minimum, to=maximum, resolution=1, orient='horizontal', showvalue=False, bg=self.CARD, troughcolor='#334155', fg=self.FG, highlightthickness=0, relief='flat', activebackground=self.ACCENT, length=200, width=9, sliderlength=16, borderwidth=0).pack(fill='x')

        def toggle_fullscreen(self, _event=None):
            enabled = bool(self.root.attributes('-fullscreen'))
            self.root.attributes('-fullscreen', not enabled)
            if enabled:
                self.root.after(100, lambda: keep_window_visible(self.root))
            return 'break'

        def escape_action(self, _event=None):
            if self.root.attributes('-fullscreen'):
                self.root.attributes('-fullscreen', False)
                self.root.after(100, lambda: keep_window_visible(self.root))
                return 'break'
            self.stop()

        def _bindings(self):
            self.root.bind('<Control-o>', lambda _ev: self.open_file())
            self.root.bind('<Control-Shift-o>', lambda _ev: self.open_entire_project())
            self.root.bind('<Control-Shift-s>', lambda _ev: self.export_entire_project())
            self.root.bind('<Control-s>', lambda _ev: self.save_text())
            self.root.bind('<F5>', lambda _ev: self.speak())
            self.root.bind('<Escape>', self.escape_action)
            self.root.bind('<F11>', self.toggle_fullscreen)
            self.root.bind('<Control-f>', lambda _ev: self.find_replace())
            self.root.bind('<Control-h>', lambda _ev: self.find_replace())
            self.root.bind('<Control-a>', self.select_all)
            self.root.bind('<Control-plus>', lambda _ev: self.resize_text(1))
            self.root.bind('<Control-minus>', lambda _ev: self.resize_text(-1))

        def pick_model(self):
            path = filedialog.askopenfilename(filetypes=[('Piper model', '*.onnx'), ('All files', '*.*')])
            if path:
                self.model_var.set(path)
                if self.engines['piper'].available():
                    self.engine_var.set('piper')
                    self.voice_var.set('')
                    self.refresh_voices()

        def add_piper_voice(self):
            source = filedialog.askopenfilename(title='Select downloaded Piper .onnx voice model', filetypes=[('Piper voice model', '*.onnx')])
            if not source:
                return
            self.status_var.set('Installing Piper voice files…')
            def work():
                try:
                    voice = install_voice(source)
                    self.events.put(('piper_installed', voice.name, str(voice.model)))
                except Exception as exc:
                    self.events.put(('error', f'Unable to add Piper voice: {exc}'))
            threading.Thread(target=work, daemon=True).start()

        def _show_document(self, title, filename):
            import importlib.resources
            source = importlib.resources.files('openvoice').joinpath('resources', filename)
            content = source.read_text(encoding='utf-8')
            window, panel = self._dialog(title, 920, 710, padding=12, scroll=False)
            ttk.Label(panel, text=title, style='Title.TLabel').pack(anchor='w', pady=(0, 10))
            row = ttk.Frame(panel)
            row.pack(fill='both', expand=True)
            editor = tk.Text(row, wrap='word', bg=self.FIELD, fg=self.FG, insertbackground=self.FG, font=(self.ui_font, 11), padx=16, pady=14)
            bar = ttk.Scrollbar(row, command=editor.yview)
            editor.configure(yscrollcommand=bar.set)
            editor.pack(side='left', fill='both', expand=True)
            bar.pack(side='right', fill='y')
            editor.insert('1.0', content)
            editor.configure(state='disabled')
            ttk.Button(panel, text='Close', command=window.destroy).pack(anchor='e', pady=(10, 0))

        def show_manual(self):
            self._show_document(f'{APP_NAME} — User Guide', 'GUI_GUIDE.txt')

        def piper_help(self):
            self._show_document('Install and Use Piper Voices', 'PIPER_SETUP.txt')

        def naming_help(self):
            self._show_document('How to Name Book and Chapter Cover Files', 'FILE_NAMING.txt')

        def about_us(self):
            messagebox.showinfo('About Us', f'{APP_NAME}\nVersion {VERSION}\n\nCreated by Aishik Dutta\n\nAn open-source desktop studio for narration, character voices, artwork, sound mixing and audiobook production.\n\nProject license: MIT. Third-party engines and voices have their own licenses.', parent=self.root)

        def pronunciation_editor(self):
            from .gui_workflows import PronunciationDesk
            return PronunciationDesk(self)

        def pick_dictionary(self):
            path = filedialog.askopenfilename(filetypes=[('Dictionaries', '*.json *.tsv *.dic *.txt'), ('All files', '*.*')])
            if path:
                self.dict_var.set(path)

        def pick_ipa_dictionary(self):
            source=filedialog.askopenfilename(filetypes=[('IPA dictionaries','*.json *.tsv *.dic *.txt'),('All files','*.*')])
            if source:
                self.ipa_dict_var.set(source)

        def ipa_editor(self):
            import json
            from .ipa_pronunciation import load_pronunciations
            window,panel=self._dialog('IPA Pronunciation Editor — All Languages',800,625)
            ttk.Label(panel,text='Custom IPA pronunciations (word, IPA, language, spoken fallback)',style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel,text='Language examples: en, bn, hi, fr, ja, * for all languages. Piper Python uses supported IPA phonemes directly. A spoken fallback works with other engines.',wraplength=650).pack(anchor='w',pady=(5,8))
            inputs=ttk.Frame(panel)
            inputs.pack(fill='x')
            word=tk.StringVar()
            ipa=tk.StringVar()
            language=tk.StringVar(value='*')
            spoken=tk.StringVar()
            for title,var in [('Word / phrase',word),('IPA /.../',ipa),('Language code',language),('Spoken fallback (optional)',spoken)]:
                ttk.Label(inputs,text=title).pack(anchor='w')
                ttk.Entry(inputs,textvariable=var).pack(fill='x',pady=(0,4))
            tree=ttk.Treeview(panel,columns=('ipa','language','spoken'),show='tree headings',height=7)
            tree.heading('#0',text='Word')
            tree.column('#0',width=140)
            for key,title,w in [('ipa','IPA',170),('language','Language',90),('spoken','Fallback',130)]:
                tree.heading(key,text=title)
                tree.column(key,width=w)
            tree.pack(fill='both',expand=True)
            rows=[]
            def show():
                tree.delete(*tree.get_children())
                for i,item in enumerate(rows):
                    tree.insert('','end',iid=str(i),text=item['word'],values=(item['ipa'],item['language'],item['spoken']))
            def choose(_event=None):
                selected=tree.selection()
                if selected:
                    item=rows[int(selected[0])]
                    for var,key in [(word,'word'),(ipa,'ipa'),(language,'language'),(spoken,'spoken')]:
                        var.set(item[key])
            tree.bind('<<TreeviewSelect>>',choose)
            def add():
                if not word.get().strip() or not ipa.get().strip():
                    messagebox.showerror('IPA entry','Enter a word and an IPA transcription.',parent=window)
                    return
                item=dict(word=word.get().strip(),ipa=ipa.get().strip(),language=language.get().strip() or '*',spoken=spoken.get().strip())
                selected=tree.selection()
                if selected:
                    rows[int(selected[0])]=item
                else:
                    rows.append(item)
                show()
            def remove():
                for selected in sorted(tree.selection(),key=int,reverse=True):
                    rows.pop(int(selected))
                show()
            def load():
                filename=filedialog.askopenfilename(parent=window,filetypes=[('IPA dictionary','*.json *.tsv *.txt')])
                if filename:
                    try:
                        rows[:]=[r.__dict__ for r in load_pronunciations([filename])]
                        self.ipa_dict_var.set(filename)
                        show()
                    except Exception as exc:
                        messagebox.showerror('IPA dictionary',str(exc),parent=window)
            def save():
                filename=filedialog.asksaveasfilename(parent=window,defaultextension='.json',filetypes=[('JSON','*.json')])
                if filename:
                    try:
                        Path(filename).write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
                        load_pronunciations([filename])
                        self.ipa_dict_var.set(filename)
                        messagebox.showinfo('IPA dictionary','Saved and activated your IPA dictionary.',parent=window)
                    except Exception as exc:
                        messagebox.showerror('IPA dictionary',str(exc),parent=window)
            existing=self.ipa_dict_var.get().strip()
            if existing:
                try:
                    rows[:]=[r.__dict__ for r in load_pronunciations([existing])]
                    show()
                except Exception as exc:
                    messagebox.showwarning('IPA dictionary',str(exc),parent=window)
            actions=ttk.Frame(panel)
            actions.pack(fill='x',pady=7)
            adaptive_grid(actions,[('Add / Update',add),('Delete',remove),('Open',load),('Save + Activate',save),('IPA Help',lambda:self._show_document('IPA Pronunciation Guide','IPA_GUIDE.txt'))],columns=2)

        def insert_inline_ipa(self):
            from .ipa_pronunciation import _clean_ipa, PronunciationError
            window, panel = self._dialog('Insert an IPA pronunciation', 480, 320, min_width=340, min_height=265)
            ttk.Label(panel, text='Insert phonetic speech directly in your story', style='PanelTitle.TLabel').pack(anchor='w', pady=(0, 9))
            ttk.Label(panel, text='IPA transcription (example: həˈloʊ)').pack(anchor='w')
            transcription = tk.StringVar()
            ipa_entry = ttk.Entry(panel, textvariable=transcription)
            ipa_entry.pack(fill='x', pady=(2, 10))
            ttk.Label(panel, text='Optional regular-text fallback (example: hello)').pack(anchor='w')
            fallback = tk.StringVar()
            ttk.Entry(panel, textvariable=fallback).pack(fill='x', pady=(2, 10))
            ttk.Label(panel, text='Works with Narrator and character tags. Piper Python plus a compatible model is needed for direct IPA; other engines require the regular-text fallback.', wraplength=380, justify='left').pack(fill='x', pady=(2, 8))
            def insert():
                try:
                    ipa = _clean_ipa(transcription.get())
                    ordinary = fallback.get().strip()
                    if any(x in ipa for x in '<>|') or any(x in ordinary for x in '<>|\n'):
                        raise PronunciationError('Angle brackets, vertical bars and newlines cannot occur inside IPA tags.')
                    tag = f'<ipa:{ipa}' + (f'|{ordinary}' if ordinary else '') + '>'
                    self.editor.insert('insert', tag)
                    self.editor.focus_set()
                    self.update_stats()
                    window.destroy()
                except PronunciationError as exc:
                    messagebox.showerror('IPA pronunciation', str(exc), parent=window)
            ttk.Button(panel, text='Insert into text', command=insert, style='Accent.TButton').pack(anchor='e')
            ipa_entry.focus_set()

        @staticmethod
        def _available_piper_speakers(target=''):
            """Expose all catalog-advertised speaker IDs before downloading a model."""
            try:
                return speaker_list(target) if target else speaker_list()
            except (OSError, ValueError):
                model = catalog_voice(target)
                if model is not None:
                    return [PiperSpeaker(index) for index in range(model.speakers)]
                return speaker_list()

        def _update_piper_speakers(self):
            # File lookup is local and fast (the ONNX model is not loaded).
            if not hasattr(self, 'speaker_combo'):
                return
            if self.engine_var.get() not in ('piper', 'auto'):
                self.speaker_combo.configure(values=['Speaker 0'], state='disabled')
                self.speaker_var.set('Speaker 0')
                return
            self.speaker_combo.configure(state='readonly')
            target = self.model_var.get().strip() or self.voice_var.get().strip()
            choices = self._available_piper_speakers(target)
            labels = [speaker.label for speaker in choices]
            self.speaker_combo.configure(values=labels)
            try:
                previous = speaker_id_from_label(self.speaker_var.get())
            except ValueError:
                previous = 0
            self.speaker_var.set(labels[previous] if previous < len(choices) else labels[0])

        def install_neural_engine(self):
            from .neural_runtime import NEURAL_ENGINES, ensure_installed
            chosen = self.engine_var.get()
            if chosen not in NEURAL_ENGINES:
                messagebox.showinfo('Neural engine', 'Choose Kokoro, Kitten, Pocket or Coqui first.', parent=self.root)
                return
            self.status_var.set(f'Installing {chosen} CPU dependencies in the user cache (internet needed)...')
            def worker():
                try:
                    python = ensure_installed(chosen, report=lambda msg: self.events.put(('ui', lambda msg=msg: self.status_var.set(msg))))
                    self.events.put(('ui', lambda: (self.status_var.set(f'{chosen} installed: {python}'), self.refresh_voices())))
                except Exception as exc:
                    detail = str(exc)
                    self.events.put(('ui', lambda: messagebox.showerror('Neural setup failed', detail, parent=self.root)))
            threading.Thread(target=worker, daemon=True).start()

        def show_neural_install_log(self, engine=None, parent=None):
            """View/copy installer diagnostics without opening a terminal."""
            return self._show_neural_diagnostics(engine, parent, worker=False)

        def show_neural_worker_log(self, engine=None, parent=None):
            """View/copy worker errors and native-library diagnostic output."""
            return self._show_neural_diagnostics(engine, parent, worker=True)

        def _show_neural_diagnostics(self, engine=None, parent=None, *, worker=False):
            from .neural_runtime import NEURAL_ENGINES, installation_log, cache_home
            selected = engine or self.engine_var.get()
            if selected not in NEURAL_ENGINES:
                messagebox.showinfo('Neural diagnostics',
                                    'Choose Kokoro, Kitten, Pocket or Coqui first.',
                                    parent=parent or self.root)
                return
            source = cache_home() / selected / 'worker.log' if worker else installation_log(selected)
            window = tk.Toplevel(parent or self.root)
            window.title(f'{selected.title()} ' + ('neural worker log' if worker else 'dependency installation log'))
            window.geometry('850x520')
            area = ttk.Frame(window, padding=10)
            area.pack(fill='both', expand=True)
            ttk.Label(area, text=f'Diagnostics file: {source}', wraplength=790).pack(anchor='w')
            middle = ttk.Frame(area)
            middle.pack(fill='both', expand=True, pady=(8, 8))
            view = tk.Text(middle, wrap='none', height=20)
            vertical = ttk.Scrollbar(middle, orient='vertical', command=view.yview)
            horizontal = ttk.Scrollbar(middle, orient='horizontal', command=view.xview)
            view.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
            view.grid(row=0, column=0, sticky='nsew')
            vertical.grid(row=0, column=1, sticky='ns')
            horizontal.grid(row=1, column=0, sticky='ew')
            middle.columnconfigure(0, weight=1)
            middle.rowconfigure(0, weight=1)
            def refresh():
                try:
                    body = source.read_text(encoding='utf-8', errors='replace')
                except FileNotFoundError:
                    body = ('No neural worker has started yet.' if worker else
                            'No dependency installation has been attempted yet.')
                except OSError as exc:
                    body = f'Unable to read the installation log: {exc}'
                view.configure(state='normal')
                view.delete('1.0', 'end')
                view.insert('1.0', body)
                view.see('end')
                view.configure(state='disabled')
            def copy_all():
                window.clipboard_clear()
                window.clipboard_append(view.get('1.0', 'end-1c'))
            buttons = ttk.Frame(area)
            buttons.pack(fill='x')
            ttk.Button(buttons, text='Refresh', command=refresh).pack(side='left')
            ttk.Button(buttons, text='Copy diagnostics', command=copy_all).pack(side='left', padx=8)
            ttk.Button(buttons, text='Close', command=window.destroy).pack(side='right')
            refresh()

        def discover_coqui_speakers(self):
            if self.engine_var.get() != 'coqui':
                messagebox.showinfo('Coqui model voices', 'Choose the Coqui engine first.', parent=self.root)
                return
            selected = self.model_var.get().strip() or 'tts_models/en/ljspeech/tacotron2-DDC'
            self.status_var.set('Reading speakers from the previously downloaded Coqui model (offline)…')
            def work():
                try:
                    engine = get_engine('coqui', selected)
                    speakers = engine.voices_for_model(selected)
                    self.events.put(('voices', 'coqui', speakers))
                except Exception as exc:
                    self.events.put(('error_voices', str(exc)))
            threading.Thread(target=work, daemon=True).start()

        def _filter_downloaded_voices(self, engine_name, names, model=''):
            """Apply the same installed-only preference to every supported voice backend."""
            if not self.installed_voices_only_var.get():
                return list(names)
            if engine_name in ('piper', 'auto'):
                catalog_names = {v.key.casefold() for v in self._piper_catalog}
                local = {v.name.casefold() for v in discover_voices()}
                return [v for v in names if v.casefold() not in catalog_names or v.casefold() in local]
            if engine_name in ('kokoro', 'kitten', 'pocket', 'coqui'):
                from .neural_models import is_downloaded, effective_model
                actual_model = effective_model(engine_name, model)
                return [v for v in names if is_downloaded(engine_name, actual_model,
                              '' if engine_name == 'coqui' else v)]
            # OS-built-in engines and eSpeak voices are installed with the engine.
            return list(names)

        def manage_sound_effects(self):
            """Add project-scoped audio resources by filename, without copying them into app data."""
            from .multivoice import AUDIO_EXTENSIONS
            win, panel = self._dialog('Imported sound effects / ambience', 690, 500)
            ttk.Label(panel, text='Import WAV, MP3, FLAC, OGG, M4A, etc. Sound names must be unique. '
                      'They are bundled with Export entire project.', wraplength=600).pack(anchor='w')
            items = tk.Listbox(panel, height=13, selectmode='extended', bg=self.FIELD, fg=self.FG,
                               selectbackground='#256c72')
            items.pack(fill='both', expand=True, pady=8)
            def refresh():
                items.delete(0, 'end')
                for source in self.voice_project.sound_files:
                    path = Path(source)
                    items.insert('end', path.name + ('  [missing]' if not path.is_file() else ''))
            def add():
                paths = filedialog.askopenfilenames(parent=win, title='Import sound effects',
                    filetypes=[('Audio files', '*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.aac *.aiff *.wma'),
                               ('All files', '*.*')])
                if not paths:
                    return
                current = {Path(x).name.casefold(): x for x in self.voice_project.sound_files}
                count = 0
                for source in paths:
                    path = Path(source).expanduser().resolve()
                    if path.suffix.lower() not in AUDIO_EXTENSIONS or not path.is_file():
                        messagebox.showerror('Unsupported sound file', path.name, parent=win)
                        continue
                    duplicate = current.get(path.name.casefold())
                    if duplicate and Path(duplicate) != path:
                        messagebox.showerror('Duplicate sound filename',
                            f'{path.name} already belongs to a different imported file. Rename one file first.', parent=win)
                        continue
                    if not duplicate:
                        self.voice_project.sound_files.append(str(path))
                        current[path.name.casefold()] = str(path)
                        count += 1
                refresh()
                self.status_var.set(f'{count} sound effect(s) added to this project')
            def remove():
                for index in reversed(items.curselection()):
                    self.voice_project.sound_files.pop(index)
                refresh()
            row = ttk.Frame(panel)
            row.pack(fill='x')
            ttk.Button(row, text='Import sounds…', command=add).pack(side='left')
            ttk.Button(row, text='Remove selected', command=remove).pack(side='left', padx=4)
            ttk.Button(row, text='Close', command=win.destroy).pack(side='right')
            refresh()

        def _piper_voice_names(self, *, installed_only=False):
            """Show only complete local voices when the checkbox is enabled."""
            local = {v.name for v in discover_voices()}
            names = local if installed_only else local | {v.key for v in self._piper_catalog}
            return sorted(names, key=str.casefold)

        def _update_voice_list_from_catalog(self):
            if self.engine_var.get() not in ('piper', 'auto'):
                return
            only = self.installed_voices_only_var.get()
            piper = set(self._piper_voice_names(installed_only=only))
            if self.engine_var.get() == 'auto':
                # Retain system voices (but not undownloaded Piper catalog voices).
                previous = set(self.voice_combo.cget('values'))
                known_catalog = {v.key for v in self._piper_catalog}
                previous -= known_catalog - {v.name for v in discover_voices()}
                piper |= previous
            self.voice_combo.configure(values=[''] + sorted(piper - {''}, key=str.casefold))

        def _on_piper_voice_selected(self, _event=None):
            """Selection is side-effect free; ask at actual speech/export time."""
            if self.engine_var.get() not in ('auto', 'piper'):
                return
            selected = self.voice_var.get().strip()
            if catalog_voice(selected) or any(v.name.casefold() == selected.casefold() for v in discover_voices()):
                self.model_var.set('')
            self._update_piper_speakers()

        def _piper_download_candidates(self, engine_name, settings, project=None, script=''):
            """Identify missing voices before starting a job, including character voices."""
            names = []
            def add(engine, name):
                candidate = str(name or '').strip()
                if not candidate or candidate.lower().endswith('.onnx') or candidate.isdecimal():
                    return
                is_piper = (engine == 'piper' or
                            engine == 'auto' and (catalog_voice(candidate) is not None or get_voice(candidate) is not None))
                if is_piper and not get_voice(candidate) and candidate.casefold() not in {x.casefold() for x in names}:
                    names.append(candidate)
            if not project or not script:
                add(engine_name, settings.model or settings.voice)
            if project:
                profiles = {p.name.casefold(): p for p in project.profiles}
                try:
                    from .character_voices import parse_passages
                    from .timeline_tags import has_timeline_tags, parse_timeline
                    if script and has_timeline_tags(script):
                        used = {part.speaker.casefold() for part in parse_timeline(
                            script, [p.name for p in project.profiles]).passages}
                    else:
                        used = {part.speaker.casefold() for part in parse_passages(
                            script, project.profiles, auto_tag=True)} if script else set(profiles)
                except (ValueError, TypeError):
                    used = set(profiles)
                for name in used:
                    profile = profiles.get(name) or profiles.get('narrator')
                    if profile:
                        # The renderer treats an Auto character with an explicit
                        # voice as Piper, regardless of the narrator engine.
                        engine = 'piper' if profile.engine == 'auto' and profile.voice else profile.engine
                        add(engine, profile.model if engine == 'piper' and profile.model else profile.voice)
                    elif name == 'narrator':
                        add(engine_name, settings.voice)
                # The default engine is still used for profiles without a voice.
                if any((profiles.get(name) or profiles.get('narrator')) and
                       not (profiles.get(name) or profiles.get('narrator')).voice
                       for name in used):
                    add(engine_name, settings.model or settings.voice)
            return names

        def _confirm_piper_downloads(self, engine_name, settings, project=None, script='', parent=None):
            """Called on Tk's main thread before background render/download."""
            voices = self._piper_download_candidates(engine_name, settings, project, script)
            if not voices:
                return True
            title = 'Download missing Piper voices?'
            summary = '\n'.join(f'• {name}' for name in voices[:12])
            if len(voices) > 12:
                summary += f'\n… and {len(voices) - 12} more'
            confirmed = messagebox.askyesno(
                title, f'These Piper voices are not installed:\n\n{summary}\n\n'
                f'Download and keep them permanently in:\n{voice_directory()}\n\n'
                'Continue with the voice download and then the requested operation?',
                parent=parent or self.root)
            if not confirmed:
                self.status_var.set('Voice download cancelled; no speech job started.')
            return confirmed

        def refresh_voices(self):
            """Populate Piper from metadata, not only downloaded models.

            The official catalog refresh is done in a worker; opening the
            selector never downloads model weights or blocks Tk.
            """
            requested = self.engine_var.get()
            model_path = self.model_var.get()
            self._voice_refresh_serial += 1
            sequence = self._voice_refresh_serial
            if requested in ('piper', 'auto'):
                self._update_voice_list_from_catalog()
            self.status_var.set('Checking available voices…')

            def work():
                try:
                    if requested in ('piper', 'auto'):
                        try:
                            catalog = fetch_catalog()
                        except Exception:
                            catalog = cached_catalog()
                        # A missing/disconnected network must not hide voices
                        # already cached or installed on disk.
                        def update_catalog():
                            if sequence != self._voice_refresh_serial:
                                return
                            self._piper_catalog = catalog or self._piper_catalog
                            if requested == 'piper':
                                names = self._piper_voice_names()
                                self._update_voice_list_from_catalog()
                                self.status_var.set(f'Piper: {len(names)} voices available (download on use with confirmation)')
                            else:
                                names = set(self.voice_combo.cget('values')) | set(self._piper_voice_names())
                                self._update_voice_list_from_catalog()
                        self.events.put(('ui', update_catalog))
                    if requested == 'piper':
                        return  # Show model names even when Piper runtime is missing.
                    engine = get_engine(requested, model_path)
                    names = engine.voices()
                    if engine.key == 'coqui' and model_path.strip():
                        from .neural_runtime import is_installed
                        from .neural_models import is_downloaded
                        if is_installed('coqui') and is_downloaded('coqui', model_path.strip()):
                            names = engine.voices_for_model(model_path.strip())
                    self.events.put(('voices', engine.key, names, requested, sequence))
                except Exception as exc:
                    self.events.put(('error_voices', str(exc)))
            threading.Thread(target=work, daemon=True).start()

        def import_clipboard(self, *, replace=False):
            try:
                clipboard = self.root.clipboard_get()
                if not isinstance(clipboard, str) or not clipboard.strip():
                    raise ValueError('Clipboard contains no text')
                if len(clipboard) > 5_000_000:
                    raise ValueError('Clipboard text exceeds the 5 million character limit')
                if replace:
                    self.editor.delete('1.0', 'end')
                    self.editor.insert('1.0', clipboard)
                    self.current_file = None
                else:
                    self.editor.insert('insert', clipboard)
                self.update_stats()
                self.status_var.set(f'Imported {len(clipboard):,} clipboard characters')
            except Exception as exc:
                messagebox.showerror('Clipboard import', str(exc), parent=self.root)

        def searchable_pdf_dialog(self):
            from .ocr import create_searchable_pdf
            source = filedialog.askopenfilename(parent=self.root, title='Select scanned PDF or image',
                filetypes=[('PDFs and scanned images', '*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp'), ('All files', '*.*')])
            if not source:
                return
            output = filedialog.asksaveasfilename(parent=self.root, title='Save searchable PDF',
                defaultextension='.pdf', filetypes=[('PDF', '*.pdf')])
            if not output:
                return
            if self.active:
                messagebox.showwarning('Busy', 'Finish the active render before starting OCR.', parent=self.root)
                return
            self.active = True
            self._set_buttons()
            def work():
                try:
                    result = create_searchable_pdf(source, output)
                    self.events.put(('done', 'Searchable PDF saved: ' + str(result)))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
                finally:
                    self.events.put(('idle',))
            threading.Thread(target=work, daemon=True).start()

        def audio_metadata_dialog(self):
            from .media_metadata import tag_audio
            source = filedialog.askopenfilename(parent=self.root, title='Select existing audiobook audio',
                filetypes=[('Supported audio', '*.mp3 *.m4a *.m4b *.flac *.ogg *.opus *.wav')])
            if not source:
                return
            output = filedialog.asksaveasfilename(parent=self.root, title='Save copy with metadata',
                defaultextension=Path(source).suffix, filetypes=[('Audio', '*' + Path(source).suffix)])
            if not output:
                return
            title = simpledialog.askstring('Audio title', 'Title metadata:', initialvalue=Path(source).stem, parent=self.root)
            if title is None:
                return
            artist = simpledialog.askstring('Audio narrator', 'Narrator / artist name (optional):', parent=self.root)
            if artist is None:
                return
            cover = None
            if Path(source).suffix.lower() in ('.mp3','.flac','.m4a','.m4b'):
                if messagebox.askyesno('Cover artwork', 'Embed cover artwork in this copy?', parent=self.root):
                    cover = filedialog.askopenfilename(parent=self.root, filetypes=[('Cover artwork', '*.png *.jpg *.jpeg')])
                    if not cover:
                        return
            if self.active:
                messagebox.showwarning('Busy', 'Finish the active render first.', parent=self.root)
                return
            self.active = True
            self._set_buttons()
            def work():
                try:
                    result = tag_audio(source, output, tags={'title': title, 'artist': artist}, cover=cover)
                    self.events.put(('done', 'Tagged audio saved: ' + str(result)))
                except Exception as exc:
                    self.events.put(('error', str(exc)))
                finally:
                    self.events.put(('idle',))
            threading.Thread(target=work, daemon=True).start()

        def hardware_diagnostics(self):
            from .hardware import hardware_status
            try:
                self._show_json_report('CPU, GPU and disk compatibility', hardware_status())
            except Exception as exc:
                messagebox.showerror('Hardware diagnostics', str(exc), parent=self.root)

        def manuscript_script_report(self):
            from .manuscript_validation import mixed_script_report
            import json
            try:
                data = mixed_script_report(self._get_text())
                self._show_json_report('Language and script validation', data)
            except Exception as exc:
                messagebox.showerror('Script validation', str(exc), parent=self.root)

        def publication_preflight_dialog(self):
            from .manuscript_validation import publication_preflight
            folder = filedialog.askdirectory(parent=self.root, title='Choose finished audiobook export folder')
            if not folder:
                return
            try:
                data = publication_preflight(folder)
                self._show_json_report('Publishing preflight report', data)
            except Exception as exc:
                messagebox.showerror('Publishing preflight', str(exc), parent=self.root)

        def _show_json_report(self, title, value):
            from .gui_forms import show_report
            return show_report(self.root,title,value)

        def _save_report(self, value):
            from .gui_forms import report_text
            path=filedialog.asksaveasfilename(parent=self.root,defaultextension='.txt',filetypes=[('Readable report','*.txt')])
            if path:
                from .security_tools import staged_file
                with staged_file(path) as stage:
                    stage.write_text(report_text(value),encoding='utf-8')
                self.status_var.set('Saved report: '+path)

        def voice_library_dialog(self):
            from .voice_library import VoiceLibrary, duplicate_models, export_voice_pack, import_voice_pack
            from .piper_models import discover_voices
            manager = VoiceLibrary()
            window = tk.Toplevel(self.root)
            window.title('Installed Piper voices — favorites, tags and packs')
            window.geometry('760x510')
            frame = ttk.Frame(window, padding=12)
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text='Select one or more installed Piper models. No downloads occur automatically.').pack(anchor='w')
            voice_list = tk.Listbox(frame, selectmode='extended', exportselection=False)
            voice_list.pack(fill='both', expand=True, pady=8)
            names = []
            def refresh():
                names[:] = [voice.name for voice in discover_voices()]
                voice_list.delete(0, 'end')
                for name in names:
                    info = manager.voices.get(name, {})
                    symbol = '★ ' if info.get('favorite') else '  '
                    voice_list.insert('end', symbol + name + '    ' + ', '.join(info.get('tags', [])))
            def selected():
                return [names[int(index)] for index in voice_list.curselection()]
            def handle(action):
                try:
                    choices = selected()
                    if action in ('favorite','tags','export') and not choices:
                        raise ValueError('Select one or more voices first')
                    if action == 'favorite':
                        for name in choices:
                            manager.set_favorite(name, not manager.voices.get(name, {}).get('favorite', False))
                    elif action == 'tags':
                        labels = simpledialog.askstring('Voice tags', 'Comma-separated tags for selected voices:', parent=window)
                        if labels is None:
                            return
                        for name in choices:
                            manager.set_tags(name, labels.split(','))
                    elif action == 'collection':
                        if not choices:
                            raise ValueError('Select the voices for the collection')
                        title = simpledialog.askstring('Voice collection', 'Name of this voice collection:', parent=window)
                        if title:
                            manager.set_collection(title, choices)
                    elif action == 'export':
                        path = filedialog.asksaveasfilename(parent=window, defaultextension='.zip',
                                                            filetypes=[('Voice pack', '*.zip')])
                        if path:
                            export_voice_pack(path, choices)
                            messagebox.showinfo('Voice pack', 'Export completed: ' + path, parent=window)
                    elif action == 'import':
                        path = filedialog.askopenfilename(parent=window, filetypes=[('Voice pack', '*.zip')])
                        if path and messagebox.askyesno('Import Piper voices', 'Import verified models from this pack? Existing models will not be overwritten.', parent=window):
                            paths = import_voice_pack(path)
                            messagebox.showinfo('Voice pack', f'Imported {len(paths)//2} Piper voice models.', parent=window)
                            self.refresh_voices()
                    elif action == 'duplicates':
                        self._show_json_report('Identical Piper model files', duplicate_models())
                    refresh()
                except Exception as exc:
                    messagebox.showerror('Voice library', str(exc), parent=window)
            refresh()
            actions = ttk.Frame(frame)
            actions.pack(fill='x')
            for label, action in [('Toggle Favorite','favorite'),('Set Tags','tags'),('Save Collection','collection'),
                                  ('Export Pack','export'),('Import Pack','import'),('Check Duplicates','duplicates')]:
                ttk.Button(actions, text=label, command=lambda a=action: handle(a)).pack(side='left', padx=3, pady=3)

        def _confirm_replace_manuscript(self):
            if self._get_text()==self._saved_text:
                return True
            answer=messagebox.askyesnocancel('Unsaved manuscript','Save your manuscript before continuing?',parent=self.root)
            if answer is None:return False
            if answer:
                self.save_text()
                return self._get_text()==self._saved_text
            return True

        def open_file(self, filename=None):
            path = filename or filedialog.askopenfilename(filetypes=[('Supported documents', '*.txt *.md *.html *.htm *.docx *.odt *.fb2 *.fb2.zip *.epub *.pdf *.rtf *.srt *.vtt *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.zip *.cbz'), ('All files', '*.*')])
            if not path:
                return
            if not self._confirm_replace_manuscript():
                return
            if use_scan_dialog(path):
                show_ocr_import(self, [path])
                return
            try:
                content = read_document(path)
            except Exception as exc:
                messagebox.showerror('Unable to import document', str(exc))
                return
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', content)
            self.update_stats()
            self.current_file = Path(path)
            self._saved_text=content
            from .gui_workflows import remember_recent
            remember_recent(path,'document')
            self.status_var.set(f'Imported {self.current_file.name} ({len(content):,} characters)')

        def insert_file(self):
            path = filedialog.askopenfilename()
            if path:
                if use_scan_dialog(path):
                    show_ocr_import(self, [path], insert=True)
                    return
                try:
                    self.editor.insert('insert', read_document(path))
                except Exception as exc:
                    messagebox.showerror('Import failed', str(exc))

        def import_scans(self):
            show_ocr_import(self)

        def import_scan_folder(self):
            folder = filedialog.askdirectory(parent=self.root, title='Choose naturally numbered book page images')
            if folder:
                show_ocr_import(self, [folder])

        def save_text(self):
            default_name = self.current_file.stem + '.txt' if self.current_file else 'speech.txt'
            path = filedialog.asksaveasfilename(defaultextension='.txt', initialfile=default_name, filetypes=[('Text files', '*.txt'), ('All files', '*.*')])
            if path:
                try:
                    Path(path).write_text(self.editor.get('1.0', 'end-1c'), encoding='utf-8')
                    self._saved_text=self._get_text()
                    self.current_file=Path(path)
                    from .gui_workflows import remember_recent
                    remember_recent(path,'document')
                    self.status_var.set(f'Saved text: {path}')
                except OSError as exc:
                    messagebox.showerror('Save failed', str(exc))

        def clear(self):
            if not self.active:
                self.editor.delete('1.0', 'end')

        def _set_icon(self):
            try:
                import importlib.resources
                import tkinter as tk
                icon = importlib.resources.files('openvoice').joinpath('resources', 'openmukti-icon.png')
                self._icon = tk.PhotoImage(data=icon.read_bytes())
                self.root.iconphoto(True, self._icon)
            except Exception:
                pass

        def open_voice_downloader(self):
            from .neural_runtime import NEURAL_ENGINES
            if self.engine_var.get() in NEURAL_ENGINES:
                self.neural_voice_downloader()
            else:
                self.voice_downloader()

        def neural_voice_downloader(self):
            """Piper-style explicit download chooser; no network calls on open."""
            from .neural_models import (MODEL_OPTIONS, VOICE_OPTIONS, effective_model,
                                        is_downloaded)
            from .neural_runtime import NEURAL_ENGINES, is_installed, ensure_installed
            from .engines.neural import download_neural_voice
            window, panel = self._dialog('Download Neural Voices — Manual Model Manager',
                                         900, 660, padding=10)
            ttk.Label(panel, text='KOKORO · KITTEN · POCKET · COQUI VOICE DOWNLOADS',
                      style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel, text='No model files are fetched when opening this window, previewing, '
                      'or exporting. Select a model and voices, then confirm each download batch. '
                      'Coqui speakers are bundled inside a model; Kitten voices share one model. '
                      'Some downloads are large; review upstream model licenses.',
                      style='Muted.TLabel', wraplength=760).pack(anchor='w', pady=(5, 8))
            top = ttk.Frame(panel)
            top.pack(fill='x', pady=5)
            engine_name = self.engine_var.get()
            if engine_name not in NEURAL_ENGINES:
                engine_name = 'kokoro'
            selected_engine = tk.StringVar(value=engine_name)
            selected_model = tk.StringVar(value='')
            query = tk.StringVar()
            neural_installed_only = tk.BooleanVar(value=False)
            ttk.Label(top, text='Engine').pack(side='left')
            engine_box = ttk.Combobox(top, textvariable=selected_engine,
                                      values=list(NEURAL_ENGINES), state='readonly', width=12)
            engine_box.pack(side='left', padx=(8, 18))
            ttk.Label(top, text='Find voice').pack(side='left')
            ttk.Entry(top, textvariable=query).pack(side='left', fill='x', expand=True, padx=(8, 0))
            model_row = ttk.Frame(panel)
            model_row.pack(fill='x', pady=4)
            ttk.Label(model_row, text='Model / variant').pack(side='left', padx=(0, 10))
            model_combo = ttk.Combobox(model_row, textvariable=selected_model)
            model_combo.pack(side='left', fill='x', expand=True)
            ttk.Checkbutton(panel, text='Installed voices only', variable=neural_installed_only,
                            command=lambda: redraw()).pack(anchor='w')
            ttk.Label(panel, text='For Coqui, you may enter another valid official model ID. '
                      'Model variants are downloaded separately.',
                      style='Muted.TLabel').pack(anchor='w', pady=(0, 6))
            columns = ('voice', 'model', 'status')
            tree = ttk.Treeview(panel, columns=columns, show='headings', selectmode='extended', height=14)
            for col, width in [('voice', 245), ('model', 295), ('status', 180)]:
                tree.heading(col, text=col.capitalize())
                tree.column(col, width=width, stretch=col != 'status')
            tree.pack(fill='both', expand=True, pady=(3, 7))
            status = tk.StringVar(value='Select the model and voice(s) to download.')
            ttk.Label(panel, textvariable=status, style='Muted.TLabel', wraplength=750).pack(anchor='w')
            activity = ttk.Progressbar(panel, mode='indeterminate')
            activity.pack(fill='x', pady=(5, 4))
            state = {'busy':False, 'visible':{}}

            def redraw(*_args):
                if not window.winfo_exists():
                    return
                selected = selected_engine.get()
                model = selected_model.get().strip() or MODEL_OPTIONS[selected][0]
                tree.delete(*tree.get_children())
                state['visible'].clear()
                for voice in VOICE_OPTIONS[selected]:
                    if query.get().strip().casefold() not in voice.casefold():
                        continue
                    actual_voice = '' if selected == 'coqui' else voice
                    installed = is_downloaded(selected, model, actual_voice)
                    if neural_installed_only.get() and not installed:
                        continue
                    item = tree.insert('', 'end', values=(voice, model,
                                        'Downloaded' if installed else 'Not downloaded'))
                    state['visible'][item] = actual_voice
                existing = sum(is_downloaded(selected, model, v) for v in state['visible'].values())
                status.set(f'{len(state["visible"])} entries shown · {existing} downloaded · '
                           f'engine dependencies: {"installed" if is_installed(selected) else "not installed"}. '
                           'Ctrl/Shift-click to select multiple voices.')

            def update_engine(_event=None):
                selected = selected_engine.get()
                model_combo.configure(values=MODEL_OPTIONS[selected])
                existing = self.model_var.get().strip() if selected == self.engine_var.get() else ''
                selected_model.set(existing or MODEL_OPTIONS[selected][0])
                redraw()

            def selected_voices(all_visible=False):
                ids = tuple(state['visible']) if all_visible else tree.selection()
                result = []
                for item in ids:
                    if item in state['visible']:
                        voice = state['visible'][item]
                        if voice not in result:
                            result.append(voice)
                # Kitten and Coqui ship all their speakers with one model.
                if selected_engine.get() in ('kitten', 'coqui') and result:
                    result = result[:1]
                return result

            def download(all_visible=False):
                if state['busy']:
                    return
                selected = selected_engine.get()
                model = selected_model.get().strip() or MODEL_OPTIONS[selected][0]
                voices = selected_voices(all_visible)
                if not voices:
                    status.set('Select one or more voices first.')
                    return
                outstanding = [v for v in voices if not is_downloaded(selected, model, v)]
                if not outstanding:
                    status.set('All selected voice/model assets are already downloaded.')
                    return
                state['busy'] = True
                activity.start(15)
                status.set(f'Installing dependencies if needed, then downloading {selected} assets…')

                def worker():
                    try:
                        # Only explicit GUI selection downloads neural model assets.
                        ensure_installed(selected, report=lambda msg: self.events.put(('ui',
                            lambda msg=msg: status.set(msg) if window.winfo_exists() else None)))
                        for number, voice in enumerate(outstanding, 1):
                            self.events.put(('ui',lambda number=number,voice=voice:
                                status.set(f'Downloading {number}/{len(outstanding)} · {selected} · '
                                           f'{voice or "all Coqui speakers"}…') if window.winfo_exists() else None))
                            download_neural_voice(selected, model, voice)
                        def success():
                            state['busy'] = False
                            if window.winfo_exists():
                                activity.stop()
                                redraw()
                                status.set(f'Downloaded {len(outstanding)} {selected} asset set(s). '
                                           'They can now be used offline.')
                            self.refresh_voices()
                        self.events.put(('ui', success))
                    except Exception as exc:
                        error = str(exc)
                        def failure():
                            state['busy'] = False
                            if window.winfo_exists():
                                activity.stop()
                                redraw()
                                status.set('Voice download failed: ' + error[:200])
                        self.events.put(('ui', failure))
                threading.Thread(target=worker, daemon=True).start()

            engine_box.bind('<<ComboboxSelected>>', update_engine)
            selected_model.trace_add('write', redraw)
            query.trace_add('write', redraw)
            buttons = ttk.Frame(panel)
            buttons.pack(fill='x', pady=8)
            adaptive_grid(buttons, [('Download Selected', download),
                                    ('Download All Shown', lambda:download(True)),
                                    ('Use this model in main window',
                                     lambda:(self.engine_var.set(selected_engine.get()),
                                             self.model_var.set(selected_model.get()),
                                             self.refresh_voices())),
                                    ('Refresh download status', redraw)], columns=2)
            diagnostics = ttk.Frame(panel)
            diagnostics.pack(fill='x', pady=(0, 4))
            ttk.Button(diagnostics, text='View / copy neural dependency installation log',
                       command=lambda: self.show_neural_install_log(selected_engine.get(), window)).pack(
                           side='left', fill='x', expand=True, padx=(0, 4))
            ttk.Button(diagnostics, text='View / copy neural worker log',
                       command=lambda: self.show_neural_worker_log(selected_engine.get(), window)).pack(
                           side='left', fill='x', expand=True, padx=(4, 0))
            update_engine()

        def voice_downloader(self):
            """Manual Piper downloader with accurate per-model state and byte progress."""
            window, panel = self._dialog('Download Piper Voices — Search and Filter by Language', 950, 710, padding=10)
            ttk.Label(panel, text='DOWNLOAD PIPER NEURAL VOICES', style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel, text='Browse the official voice catalog, including voices not yet installed. '
                      'Downloads are verified and saved permanently; manual downloads do not show confirmation or completion popups.',
                      style='Muted.TLabel', wraplength=780).pack(anchor='w', pady=(4, 8))
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=5)
            language = tk.StringVar(value='All languages')
            query = tk.StringVar()
            only_installed = tk.BooleanVar(value=False)
            languages = ttk.Combobox(row, state='readonly', textvariable=language, width=29,
                                     values=['All languages'])
            languages.pack(side='left', padx=(0, 8))
            ttk.Entry(row, textvariable=query, width=32).pack(side='left', fill='x', expand=True)
            ttk.Checkbutton(panel, text='Installed voices only', variable=only_installed,
                            command=lambda: update()).pack(anchor='w', pady=(2, 0))
            cols = ('language', 'voice', 'quality', 'speakers', 'MB', 'status')
            tree = ttk.Treeview(panel, columns=cols, show='headings', selectmode='extended')
            for key, width in [('language', 165), ('voice', 275), ('quality', 85),
                               ('speakers', 70), ('MB', 65), ('status', 145)]:
                tree.heading(key, text=key.title())
                tree.column(key, width=width, stretch=key in ('language', 'voice', 'status'))
            tree.pack(fill='both', expand=True, pady=8)
            state = {'catalog': [], 'shown': {}, 'busy': False, 'progress': {}, 'failures': {}}
            status = tk.StringVar(value='Loading Piper catalog…')
            ttk.Label(panel, textvariable=status, style='Muted.TLabel', wraplength=760).pack(anchor='w')
            activity = ttk.Progressbar(panel, mode='determinate', maximum=100)
            activity.pack(fill='x', pady=(5, 5))

            def update():
                if not window.winfo_exists():
                    return
                selected_names = {state['shown'][iid].key for iid in tree.selection()
                                  if iid in state['shown']}
                tree.delete(*tree.get_children())
                state['shown'].clear()
                local = {v.name.casefold() for v in discover_voices()}
                downloaded = 0
                for voice in state['catalog']:
                    lang = f'{voice.language_name} ({voice.language})'
                    installed = voice.key.casefold() in local
                    if only_installed.get() and not installed:
                        continue
                    if language.get() != 'All languages' and lang != language.get():
                        continue
                    if query.get().casefold() not in (voice.key + ' ' + lang + ' ' + voice.quality).casefold():
                        continue
                    if installed:
                        downloaded += 1
                    result = ('Downloaded' if installed else
                              state['progress'].get(voice.key) or
                              ('Failed' if voice.key in state['failures'] else 'Not downloaded'))
                    iid = tree.insert('', 'end', values=(lang, voice.key, voice.quality,
                        voice.speakers, round((voice.model_bytes + voice.config_bytes)/1048576, 1), result))
                    state['shown'][iid] = voice
                    if voice.key in selected_names:
                        tree.selection_add(iid)
                if not state['busy']:
                    status.set(f'{len(state["shown"])} voices shown · {downloaded} downloaded. '
                               'Ctrl/Shift-click to select several voices.')

            languages.bind('<<ComboboxSelected>>', lambda _e: update())
            query.trace_add('write', lambda *_: update())

            def load():
                if state['busy']:
                    return
                state['busy'] = True
                status.set('Loading official Piper catalog (metadata only)…')
                def worker():
                    try:
                        voices = fetch_catalog()
                        def success():
                            state['busy'] = False
                            if window.winfo_exists():
                                state['catalog'] = voices
                                self._piper_catalog = voices
                                languages.configure(values=['All languages'] + catalog_languages(voices))
                                update()
                                self._update_voice_list_from_catalog()
                        self.events.put(('ui', success))
                    except Exception as exc:
                        error = str(exc)
                        def fail():
                            state['busy'] = False
                            if window.winfo_exists():
                                # Failed metadata loads do not open an intrusive dialog.
                                status.set('Unable to load Piper catalog: ' + error[:250])
                        self.events.put(('ui', fail))
                threading.Thread(target=worker, daemon=True).start()

            def download(all_visible=False, all_catalog=False):
                if state['busy']:
                    return
                selected = (list(state['catalog']) if all_catalog else
                            list(state['shown'].values()) if all_visible else
                            [state['shown'][iid] for iid in tree.selection() if iid in state['shown']])
                if not selected:
                    status.set('Select one or more Piper voices first.')
                    return
                state['busy'] = True
                activity['value'] = 0
                state['progress'].clear()
                state['failures'].clear()
                status.set(f'Checking {len(selected)} selected Piper voices…')
                def worker():
                    success_count = 0
                    failures = []
                    count = len(selected)
                    for index, item in enumerate(selected):
                        last_percent = [-1]
                        def report(bytes_done, total, item=item, index=index):
                            percent = max(0, min(100, int(100 * bytes_done / max(1, total))))
                            if percent == last_percent[0]:
                                return
                            last_percent[0] = percent
                            def show():
                                if not window.winfo_exists():
                                    return
                                state['progress'][item.key] = f'Downloading {percent}%'
                                for iid, value in state['shown'].items():
                                    if value.key == item.key:
                                        tree.set(iid, 'status', state['progress'][item.key])
                                activity['value'] = 100 * (index + percent / 100) / count
                                status.set(f'Downloading {index+1}/{count}: {item.key} ({percent}%)')
                            self.events.put(('ui', show))
                        try:
                            ensure_piper_voice(item.key, progress=report)
                            success_count += 1
                            def complete(item=item, index=index):
                                if window.winfo_exists():
                                    state['progress'].pop(item.key, None)
                                    for iid, value in state['shown'].items():
                                        if value.key == item.key:
                                            tree.set(iid, 'status', 'Downloaded')
                                    activity['value'] = 100 * (index + 1) / count
                            self.events.put(('ui', complete))
                        except Exception as exc:
                            error = str(exc)
                            failures.append((item.key, error))
                            def failed(item=item, error=error, index=index):
                                if window.winfo_exists():
                                    state['progress'].pop(item.key, None)
                                    state['failures'][item.key] = error
                                    for iid, value in state['shown'].items():
                                        if value.key == item.key:
                                            tree.set(iid, 'status', 'Failed')
                                    activity['value'] = 100 * (index + 1) / count
                                    status.set(f'Failed: {item.key}: {error[:170]}')
                            self.events.put(('ui', failed))
                    def finished():
                        state['busy'] = False
                        if window.winfo_exists():
                            update()
                            activity['value'] = 100
                            if failures:
                                status.set(f'{success_count} installed; {len(failures)} failed. '
                                           f'{failures[0][0]}: {failures[0][1][:180]}')
                            else:
                                status.set(f'{success_count} voice(s) installed and saved permanently.')
                        self._update_voice_list_from_catalog()
                    self.events.put(('ui', finished))
                threading.Thread(target=worker, daemon=True).start()

            buttons = ttk.Frame(panel)
            buttons.pack(fill='x', pady=8)
            adaptive_grid(buttons, [('Load Voice Catalog', load), ('Download Selected', download),
                                    ('Download All Shown', lambda: download(all_visible=True)),
                                    ('Download Entire Catalog', lambda: download(all_catalog=True)),
                                    ('Refresh download status', update)], columns=2)
            load()

        def character_voice_studio(self):
            window, panel = self._dialog('Character Voices — Narrator and Dialogue Studio', 1020, 790, min_width=570, min_height=430, padding=10)
            ttk.Label(panel,text='CHARACTER VOICES',style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel,text='Find Characters inserts editable [Name] tags around attributed quotations and restores [Narrator] for other text.\nMixed languages, invented names, dialogue styles and voice settings can be reviewed and changed before export.',style='Muted.TLabel',wraplength=720).pack(anchor='w',pady=8)
            upper=ttk.Frame(panel)
            upper.pack(fill='both',expand=True)
            left=ttk.Frame(upper)
            right=ttk.Frame(upper)
            arrangement={'stacked':None}
            def layout_voice_columns(_event=None):
                stacked=window.winfo_width()<920
                if stacked==arrangement['stacked']:
                    return
                left.pack_forget()
                right.pack_forget()
                if stacked:
                    left.pack(side='top',fill='both',expand=True,pady=(0,10))
                    right.pack(side='top',fill='x')
                else:
                    left.pack(side='left',fill='both',expand=True,padx=(0,12))
                    right.pack(side='right',fill='both',expand=True)
                arrangement['stacked']=stacked
            window.bind('<Configure>',layout_voice_columns,add='+')
            layout_voice_columns()
            ttk.Label(left,text='Character voice profiles').pack(anchor='w')
            tree=ttk.Treeview(left,columns=('voice','language','gender','age','style'),show='tree headings',height=9)
            tree.heading('#0',text='Character')
            tree.column('#0',width=105)
            for c,w in [('voice',145),('language',90),('gender',70),('age',80),('style',85)]:
                tree.heading(c,text=c.title())
                tree.column(c,width=w)
            tree.pack(fill='both',expand=True)
            aliases_var=tk.StringVar()
            imported_names=set()
            last_analysis=[None]
            analysis_running=[False]
            name=tk.StringVar(value='Narrator')
            voice=tk.StringVar()
            character_engine=tk.StringVar(value='auto')
            character_model=tk.StringVar()
            character_speaker=tk.StringVar(value='Speaker 0')
            language=tk.StringVar(value='auto')
            gender=tk.StringVar(value='Unspecified')
            age=tk.StringVar(value='Unspecified')
            style=tk.StringVar(value='natural')
            rate=tk.IntVar(value=0)
            pitch=tk.IntVar(value=0)
            design_strength=tk.DoubleVar(value=85.0)
            character_volume=tk.IntVar(value=100)
            design_summary=tk.StringVar(value='')
            def update_design(*_args):
                try:
                    draft=CharacterProfile(name.get() or 'Character',gender=gender.get(),age=age.get(),characteristics=style.get(),pitch=pitch.get(),design_strength=design_strength.get())
                    result=design_for_profile(draft)
                except (tk.TclError, ValueError, TypeError):
                    return
                design_summary.set(f'Audio effect: pitch {result.semitones:+.1f} semitones, speed {result.speed_adjust:+d}, bass {result.bass_db:+.1f} dB, treble {result.treble_db:+.1f} dB')
            def refresh(select=''):
                self._refresh_character_selector()
                tree.delete(*tree.get_children())
                for profile in self.voice_project.profiles:
                    item=tree.insert('','end',text=profile.name,values=(profile.voice or 'Auto',profile.language,profile.gender,profile.age,profile.characteristics))
                    if profile.name==select:
                        tree.selection_set(item)
                if self.voice_project.profiles and not tree.selection():
                    tree.selection_set(tree.get_children()[0])
            def select(_event=None):
                selection=tree.selection()
                if not selection:
                    return
                existing=next((x for x in self.voice_project.profiles if x.name==tree.item(selection[0],'text')),None)
                if existing:
                    aliases_var.set('; '.join(existing.aliases))
                    for var,value in [(name,existing.name),(voice,existing.voice),(character_engine,existing.engine),(character_model,existing.model),(language,existing.language),(gender,existing.gender),(age,existing.age),(style,existing.characteristics),(rate,existing.rate),(pitch,existing.pitch),(design_strength,existing.design_strength),(character_volume,existing.volume)]:
                        var.set(value)
                    update_character_speakers(existing.speaker_id)
            tree.bind('<<TreeviewSelect>>',select)
            ttk.Label(right,text='Profile details').pack(anchor='w')
            for label,var in [('Character',name),('Language ISO code, e.g. en-US or bn-BD',language)]:
                ttk.Label(right,text=label).pack(anchor='w',pady=(6,0))
                ttk.Entry(right,textvariable=var).pack(fill='x')
            ttk.Label(right,text='Aliases / former identities (separate with ;)').pack(anchor='w',pady=(6,0))
            ttk.Entry(right,textvariable=aliases_var).pack(fill='x')
            ttk.Label(right,text='Character speech engine').pack(anchor='w',pady=(6,0))
            ttk.Combobox(right,textvariable=character_engine,state='readonly',values=['auto',*self.engines]).pack(fill='x')
            ttk.Label(right,text='Voice or speaker preset (Piper / Kokoro / Kitten / Pocket / Coqui)').pack(anchor='w',pady=(6,0))
            character_voice_combo=ttk.Combobox(right,textvariable=voice,values=['']+self._piper_voice_names())
            character_voice_combo.pack(fill='x')
            character_installed_only = tk.BooleanVar(value=False)
            def character_voice_choices():
                chosen = character_engine.get()
                if chosen in ('auto', 'piper'):
                    choices = self._piper_voice_names(installed_only=character_installed_only.get())
                else:
                    choices = list(self.engines[chosen].voices())
                    if character_installed_only.get() and chosen in ('kokoro', 'kitten', 'pocket', 'coqui'):
                        from .neural_models import is_downloaded, effective_model
                        model = effective_model(chosen, character_model.get().strip())
                        choices = [v for v in choices if is_downloaded(chosen, model, '' if chosen == 'coqui' else v)]
                return [''] + choices
            def update_character_choices():
                character_voice_combo.configure(values=character_voice_choices())
            character_voice_combo.configure(postcommand=update_character_choices)
            ttk.Checkbutton(right, text='Installed voices only', variable=character_installed_only,
                            command=update_character_choices).pack(anchor='w', pady=(2, 0))
            ttk.Label(right,text='Optional engine model (ONNX path, Kitten repo, Coqui model name)').pack(anchor='w',pady=(6,0))
            ttk.Combobox(right,textvariable=character_model,values=['', 'KittenML/kitten-tts-nano-0.8',
                'KittenML/kitten-tts-micro-0.8','KittenML/kitten-tts-mini-0.8',
                'tts_models/en/ljspeech/tacotron2-DDC', 'tts_models/en/vctk/vits',
                'tts_models/multilingual/multi-dataset/xtts_v2',
                'english', 'english_18m_2026-10', 'english_7m_2026-10', 'english_2m_2026-10',
                'french', 'german', 'spanish', 'portuguese', 'italian', 'dutch']).pack(fill='x')
            def refresh_character_engine(*_):
                chosen=character_engine.get()
                if chosen in ('kokoro','kitten','pocket','coqui'):
                    update_character_choices()
                else:
                    update_character_choices()
                update_character_speakers()
            character_engine.trace_add('write', refresh_character_engine)
            def discover_character_coqui_speakers():
                if character_engine.get() != 'coqui':
                    messagebox.showinfo('Character voice', 'Choose the Coqui character engine first.', parent=window)
                    return
                model_id=character_model.get().strip() or 'tts_models/en/ljspeech/tacotron2-DDC'
                self.status_var.set(f'Discovering speakers for {model_id}…')
                def find_speakers():
                    try:
                        names=get_engine('coqui',model_id).voices_for_model(model_id)
                        def apply():
                            if window.winfo_exists():
                                character_voice_combo.configure(values=['']+names)
                                if voice.get() and voice.get() not in names:
                                    voice.set('')
                                self.status_var.set(f'Coqui model has {len(names)} named speakers')
                        self.events.put(('ui',apply))
                    except Exception as exc:
                        error=str(exc)
                        self.events.put(('ui',lambda: messagebox.showerror('Coqui speakers',error,parent=window) if window.winfo_exists() else None))
                threading.Thread(target=find_speakers,daemon=True).start()
            ttk.Button(right,text='Discover voices for this Coqui model',command=discover_character_coqui_speakers).pack(fill='x',pady=(3,1))
            ttk.Label(right,text='Piper speaker in this model (different speakers can be assigned to different characters)').pack(anchor='w',pady=(6,0))
            character_speaker_combo=ttk.Combobox(right,textvariable=character_speaker,state='readonly',values=['Speaker 0'])
            character_speaker_combo.pack(fill='x')
            def update_character_speakers(preferred=None):
                if character_engine.get() not in ('auto','piper'):
                    character_speaker_combo.configure(values=['Speaker 0'], state='disabled')
                    character_speaker.set('Speaker 0')
                    return
                character_speaker_combo.configure(state='readonly')
                speakers = self._available_piper_speakers(character_model.get().strip() or voice.get().strip())
                labels=[speaker.label for speaker in speakers]
                character_speaker_combo.configure(values=labels)
                if preferred is None:
                    try:
                        preferred=speaker_id_from_label(character_speaker.get())
                    except ValueError:
                        preferred=0
                character_speaker.set(labels[preferred] if 0 <= preferred < len(labels) else labels[0])
            voice.trace_add('write',lambda *_:update_character_speakers())
            def character_voice_chosen(_event=None):
                if character_engine.get() not in ('auto', 'piper'):
                    return
                selected = voice.get().strip()
                if catalog_voice(selected) or any(v.name.casefold() == selected.casefold() for v in discover_voices()):
                    character_model.set('')
                update_character_speakers()
            character_voice_combo.bind('<<ComboboxSelected>>', character_voice_chosen)
            update_character_speakers()
            ttk.Label(right,text='Speech rate (-10 to +10)').pack(anchor='w',pady=(5,0))
            ttk.Spinbox(right,from_=-10,to=10,textvariable=rate,width=10).pack(anchor='w')
            ttk.Label(right,text='Character volume (0–100% of main output volume)').pack(anchor='w',pady=(5,0))
            ttk.Spinbox(right,from_=0,to=100,textvariable=character_volume,width=10).pack(anchor='w')
            ttk.Label(right,text='Pitch correction (-10 to +10; post-processes all Piper voices)').pack(anchor='w',pady=(5,0))
            ttk.Spinbox(right,from_=-10,to=10,textvariable=pitch,width=10).pack(anchor='w')
            for label,var,values in [('Voice presentation',gender,['Unspecified','Female','Male','Nonbinary','Androgynous']),('Character age',age,['Unspecified','Child','Teen','Young adult','Adult','Middle aged','Senior']),('Voice personality (combine styles with commas)',style,sorted(STYLE_DESIGNS))]:
                ttk.Label(right,text=label).pack(anchor='w',pady=(6,0))
                ttk.Combobox(right,textvariable=var,values=values).pack(fill='x')
            ttk.Label(right,text='Voice transformation strength (0=original, 100=full)').pack(anchor='w',pady=(8,0))
            ttk.Scale(right,from_=0,to=100,variable=design_strength,orient='horizontal').pack(fill='x')
            ttk.Label(right,textvariable=design_summary,style='Muted.TLabel',wraplength=350).pack(fill='x',pady=5)
            for variable in (gender,age,style,pitch,design_strength):
                variable.trace_add('write',update_design)
            update_design()
            def save_profile():
                title=name.get().strip()
                try:
                    values={'voice':voice.get().strip(),'engine':character_engine.get(),'model':character_model.get().strip(), 'speaker_id':speaker_id_from_label(character_speaker.get()),'language':language.get().strip() or 'auto',
                            'gender':gender.get(),'age':age.get(),'characteristics':style.get(),
                            'rate':rate.get(),'pitch':pitch.get(),'design_strength':design_strength.get(),
                            'volume':character_volume.get()}
                    draft=CharacterProfile(title,aliases=[a.strip() for a in aliases_var.get().split(';') if a.strip()],**values)
                except (ValueError, TypeError, tk.TclError) as exc:
                    messagebox.showerror('Profile','Enter valid profile values: '+str(exc),parent=window)
                    return False
                p=next((p for p in self.voice_project.profiles if p.name.casefold()==title.casefold()),None)
                if p is None:
                    p=CharacterProfile(title)
                    self.voice_project.profiles.append(p)
                for attr in PROFILE_FIELDS:
                    value=getattr(draft,attr)
                    if value!=getattr(p,attr) and attr not in p.locked_fields:
                        p.locked_fields.append(attr)
                    setattr(p,attr,value)
                p.aliases=draft.aliases
                refresh(title)
                return True
            def allow_automatic():
                if not save_profile():return
                p=next((p for p in self.voice_project.profiles if p.name.casefold()==name.get().strip().casefold()),None)
                if p:
                    p.locked_fields=[]
                    p.auto_values={attr:getattr(p,attr) for attr in PROFILE_FIELDS}
                    status.set('Automatic updates enabled for '+p.name+'. Click Find Characters to infer all settings again.')
            ttk.Button(right,text='Allow automatic updates for this profile',command=allow_automatic).pack(fill='x',pady=4)
            ttk.Button(right,text='Save / Add Profile',command=save_profile).pack(fill='x',pady=6)
            def preview_voice():
                if not save_profile():return
                from .character_voices import parse_passages
                from .engines.builtin import play_wav
                import tempfile
                script=editor.get('1.0','end-1c')
                selected=name.get().strip()
                available=[part.text for part in parse_passages(script,self.voice_project.profiles) if part.speaker.casefold()==selected.casefold()]
                sample=available[0][:280] if available else simpledialog.askstring('Character voice sample',f'Enter a short passage for {selected} in the model language:',parent=window)
                if not sample:
                    status.set('Preview cancelled: no text for this character.')
                    return
                selection=VoiceProject([CharacterProfile(**vars(p)) for p in self.voice_project.profiles],
                                       speaker_rules=dict(self.voice_project.speaker_rules),sound_files=self.voice_project.sound_files.copy(),pronunciation_files=[project_ipa.get().strip()] if project_ipa.get().strip() else [])
                preview_script=f'[{selected}] {sample}'
                if not self._confirm_piper_downloads('auto', SpeechSettings(), selection, preview_script, parent=window):
                    return
                status.set('Synthesizing preview for '+selected+'…')
                def worker():
                    try:
                        with tempfile.TemporaryDirectory(prefix='openmukti-voice-preview-') as work:
                            file=Path(work)/'preview.wav'
                            selection=VoiceProject([CharacterProfile(**vars(p)) for p in self.voice_project.profiles],speaker_rules=dict(self.voice_project.speaker_rules),sound_files=self.voice_project.sound_files.copy(),pronunciation_files=[project_ipa.get().strip()] if project_ipa.get().strip() else [])
                            render_multivoice(f'[{selected}] {sample}',file,selection,auto_tag=True)
                            play_wav(file)
                        self.events.put(('ui',lambda:status.set('Preview played for '+selected) if window.winfo_exists() else None))
                    except Exception as exc:
                        err=str(exc)
                        self.events.put(('ui',lambda:messagebox.showerror('Voice preview failed',err,parent=window) if window.winfo_exists() else None))
                threading.Thread(target=worker,daemon=True).start()
            ttk.Button(right,text='▶ Preview character voice with effects',command=preview_voice).pack(fill='x',pady=(0,6))
            def delete_profile():
                selected=name.get().strip()
                if selected.casefold()=='narrator':
                    messagebox.showwarning('Narrator','The Narrator profile is required.',parent=window)
                    return
                self.voice_project.profiles=[p for p in self.voice_project.profiles if p.name.casefold()!=selected.casefold()]
                refresh()
            ttk.Button(right,text='Delete Character Profile',command=delete_profile).pack(fill='x')
            ttk.Label(panel,text='IPA pronunciation dictionary for character voices (optional; language-scoped rules)').pack(anchor='w',pady=(7,3))
            project_ipa=tk.StringVar(value=self.voice_project.pronunciation_files[0] if self.voice_project.pronunciation_files else self.ipa_dict_var.get())
            pronunciation_row=ttk.Frame(panel)
            pronunciation_row.pack(fill='x')
            ttk.Entry(pronunciation_row,textvariable=project_ipa).pack(side='left',fill='x',expand=True)
            def browse_project_ipa():
                path=filedialog.askopenfilename(parent=window,filetypes=[('IPA rules','*.json *.tsv *.txt')])
                if path:
                    project_ipa.set(path)
            ttk.Button(pronunciation_row,text='Browse',command=browse_project_ipa).pack(side='left')
            ttk.Label(panel,text='Editable script — inline [Character Name] and [Narrator] tags can appear within paragraphs.').pack(anchor='w',pady=(10,4))
            editor=tk.Text(panel,height=11,wrap='word',undo=True,bg=self.FIELD,fg=self.FG,insertbackground=self.FG,font=(self.ui_font,10),padx=10,pady=8)
            editor.pack(fill='both',expand=True)
            editor.insert('1.0',self.voice_project.script or self._get_text())
            if not (self.voice_project.script or self._get_text()).strip():
                editor.insert('1.0','[Narrator] It was a bright morning.\n[Alice] Good morning!\n[Bob] Hello, Alice!')
            status=tk.StringVar(value='Choose each character’s engine, model, voice, and Piper speaker. Leaving Auto uses existing project behavior.')
            ttk.Label(panel,textvariable=status).pack(anchor='w',pady=6)
            def save_script():
                if not save_profile():return False
                self.voice_project.script=editor.get('1.0','end-1c')
                self.voice_project.pronunciation_files=[project_ipa.get().strip()] if project_ipa.get().strip() else []
                return True
            scan_progress=ttk.Progressbar(panel,mode='indeterminate')
            scan_progress.pack(fill='x',pady=2)
            def review_analysis():
                report=last_analysis[0]
                review_window,review_panel=self._dialog('Character and quote evidence',1000,720)
                report_text=tk.Text(review_panel,wrap='word',bg=self.FIELD,fg=self.FG,insertbackground=self.FG)
                report_text.pack(fill='both',expand=True)
                for p in self.voice_project.profiles:
                    report_text.insert('end',p.name+'\n')
                    if p.aliases:report_text.insert('end','  Aliases: '+'; '.join(p.aliases)+'\n')
                    for attr in PROFILE_FIELDS:
                        item=p.inference.get(attr,{})
                        lock=' (manual setting)' if attr in p.locked_fields else ''
                        report_text.insert('end',f'  {attr}: {getattr(p,attr)}{lock}\n')
                        if item:
                            report_text.insert('end',f'    Suggested: {item.get("suggested",getattr(p,attr))}; confidence {item.get("confidence",0):.0%}\n')
                            for clue in item.get('evidence',[]):report_text.insert('end','    '+str(clue)+'\n')
                    report_text.insert('end','\n')
                if report:
                    source,analysis=report
                    report_text.insert('end','QUOTATION ATTRIBUTION (positions in the source before tagging)\n\n')
                    for q in analysis.quotations:
                        line=source.count('\n',0,q.start)+1
                        report_text.insert('end',f'Line {line} · {q.speaker} · {q.confidence:.0%} · {q.reason}\n')
                        if q.alternatives:report_text.insert('end','  Candidates: '+', '.join(q.alternatives)+'\n')
                        report_text.insert('end',source[q.start:q.end][:300]+'\n\n')
                else:report_text.insert('end','Run Find Characters to populate quote evidence.\n')
                report_text.configure(state='disabled')
            def import_names():
                source=filedialog.askopenfilename(parent=window,title='Import additional character name hints',filetypes=[('Name lists','*.txt *.csv *.json *.gz'),('All files','*')])
                if not source:return
                try:
                    names=read_name_list(source)
                    imported_names.update(names)
                    status.set(f'{len(imported_names):,} extra name hints loaded for this session. Invented and Unicode names are also recognized from context.')
                except (OSError,ValueError) as exc:messagebox.showerror('Name list',str(exc),parent=window)
            def detect_names():
                """Infer every automatic control, preserving explicit manual edits."""
                if analysis_running[0] or not save_profile():return
                original=editor.get('1.0','end-1c')
                if not original.strip():
                    status.set('Nothing to analyze: enter or import a script first.')
                    return
                status.set('Analyzing identities, aliases, dialogue, languages and all voice controls…')
                analysis_running[0]=True
                scan_progress.start(25)
                snapshot=copy.deepcopy(self.voice_project.profiles)
                installed=discover_voices()
                extra=tuple(imported_names)
                def work():
                    try:
                        analyzed=auto_profiles(original,installed=installed,existing_profiles=snapshot,extra_names=extra)
                    except Exception as exc:
                        msg=str(exc)
                        def fail():
                            analysis_running[0]=False
                            if window.winfo_exists():
                                scan_progress.stop()
                                status.set('Analysis failed: '+msg)
                        self.events.put(('ui',fail))
                        return
                    def apply():
                        analysis_running[0]=False
                        if not window.winfo_exists():return
                        scan_progress.stop()
                        if editor.get('1.0','end-1c')!=original:
                            status.set('Script changed during analysis. Click Find Characters to analyze the current text.')
                            return
                        # Edits made to profiles while the worker ran are merged
                        # against the CURRENT values, not its stale snapshot.
                        before={p.name.casefold() for p in self.voice_project.profiles}
                        self.voice_project.profiles=merge_auto_profiles(self.voice_project.profiles,analyzed.profiles)
                        added=sum(p.name.casefold() not in before for p in self.voice_project.profiles)
                        if analyzed.script!=original:replace_text(editor,analyzed.script)
                        self.voice_project.script=analyzed.script
                        last_analysis[0]=(original,analyzed.analysis)
                        selected=analyzed.analysis.aliases.get(name.get(),name.get())
                        refresh(selected)
                        select()
                        quotes=analyzed.analysis.quotations
                        tagged=sum(q.speaker!='Narrator' for q in quotes)
                        uncertain=len(quotes)-tagged
                        status.set(f'{added} new profiles; {tagged} attributed quotations; {uncertain} uncertain. Automatic controls refreshed; manual edits kept. Review evidence below.')
                        if self._get_text()==original:self._replace_text(analyzed.script)
                    self.events.put(('ui',apply))
                threading.Thread(target=work,daemon=True).start()

            def suggest():
                """Analyze mixed languages, apply unconfigured language choices,
                and show installed + downloadable recommendations per language."""
                if not save_profile():return
                script_text=editor.get('1.0','end-1c')
                if not script_text.strip():
                    status.set('Enter a script to detect languages first.')
                    return
                current=[CharacterProfile(**vars(p)) for p in self.voice_project.profiles]
                installed=[v.name for v in discover_voices()]
                status.set('Detecting language(s) and checking installed voice models…')
                def work():
                    try:
                        detected=detected_languages(script_text)
                        annotated=analyze_dialogue(script_text,known_names=[p.name for p in current],known_aliases=profile_aliases(current)).tagged_text
                        from .character_voices import parse_passages, _choose_installed_voice
                        passages=parse_passages(annotated,current)
                        by_speaker={}
                        for profile in current:
                            own=' '.join(p.text for p in passages if p.speaker.casefold()==profile.name.casefold())
                            local=detected_languages(own)
                            if not local and detected:local=detected
                            by_speaker[profile.name.casefold()]=local[0][0] if local else 'und'
                        try:
                            catalog=fetch_catalog()
                            catalog_error=''
                        except Exception as exc:
                            catalog=[]
                            catalog_error=str(exc)
                        used={p.voice for p in current if p.voice}
                        suggestions={}
                        for profile in current:
                            code=by_speaker[profile.name.casefold()]
                            chosen=_choose_installed_voice(code,installed,used)
                            if chosen:used.add(chosen)
                            available=recommend_voices(CharacterProfile(profile.name,language=code),catalog,limit=5)
                            suggestions[profile.name.casefold()]=(code,chosen,available)
                    except Exception as exc:
                        msg=str(exc)
                        self.events.put(('ui',lambda:status.set('Language analysis failed: '+msg) if window.winfo_exists() else None))
                        return
                    def apply():
                        if not window.winfo_exists():return
                        updated=0
                        for profile in self.voice_project.profiles:
                            code,chosen,_=suggestions[profile.name.casefold()]
                            if code not in ('auto','und') and profile.language in ('','auto','und'):
                                profile.language=code;updated+=1
                            if chosen and not profile.voice:
                                profile.voice=chosen
                        refresh(name.get())
                        selected=next((p for p in self.voice_project.profiles if p.name.casefold()==name.get().casefold()),None)
                        if selected:
                            language.set(selected.language)
                            voice.set(selected.voice)
                        summary=', '.join(f'{lang} ({confidence:.0%})' for lang,confidence in detected) or 'insufficient evidence'
                        status.set('Detected: '+summary+f'. Updated {updated} unconfigured profiles. Check recommendations below.')
                        report=tk.Toplevel(window)
                        report.title('Language detection and recommended voices')
                        fit_window(report,780,520,550,350)
                        contents=ttk.Frame(report,padding=12);contents.pack(fill='both',expand=True)
                        ttk.Label(contents,text='Detected languages: '+summary,wraplength=700).pack(anchor='w',pady=(0,8))
                        review=tk.Text(contents,wrap='word',bg=self.FIELD,fg=self.FG,insertbackground=self.FG,font=(self.ui_font,10))
                        review.pack(fill='both',expand=True)
                        for profile in self.voice_project.profiles:
                            code,chosen,available=suggestions[profile.name.casefold()]
                            review.insert('end',f'{profile.name}: {code}\n')
                            review.insert('end',f'  Installed model: {profile.voice or chosen or "No matching installed Piper voice"}\n')
                            review.insert('end','  Downloadable Piper suggestions: '+(', '.join(v.key for v in available) or 'None in catalog')+'\n\n')
                        if catalog_error:
                            review.insert('end','Online catalog unavailable (offline recommendations used): '+catalog_error+'\n')
                        review.configure(state='disabled')
                        actions=ttk.Frame(contents); actions.pack(fill='x',pady=8)
                        ttk.Button(actions,text='Download / browse voices',command=self.open_voice_downloader).pack(side='left')
                        ttk.Button(actions,text='Close',command=report.destroy).pack(side='right')
                    self.events.put(('ui',apply))
                threading.Thread(target=work,daemon=True).start()
            def save_project():
                if not save_script():return
                target=filedialog.asksaveasfilename(parent=window,defaultextension='.json',filetypes=[('Voice project','*.json')])
                if target:
                    self.voice_project.save(target)
                    status.set('Saved voice project: '+target)
            def open_project():
                source=filedialog.askopenfilename(parent=window,filetypes=[('Voice project','*.json')])
                if source:
                    try:
                        self.voice_project=VoiceProject.load(source)
                        last_analysis[0]=None
                        editor.delete('1.0','end')
                        editor.insert('1.0',self.voice_project.script)
                        project_ipa.set(self.voice_project.pronunciation_files[0] if self.voice_project.pronunciation_files else '')
                        refresh()
                    except Exception as exc:
                        messagebox.showerror('Project',str(exc),parent=window)
            def export(as_video=False):
                if not save_script():return
                dest=filedialog.asksaveasfilename(parent=window,defaultextension='.mp4' if as_video else '.wav',filetypes=[('Video','*.mp4 *.mkv *.mov *.webm')] if as_video else [('Audio','*.wav *.mp3 *.m4a *.flac *.ogg')])
                if not dest:
                    return
                images=[]
                if as_video:
                    images=list(filedialog.askopenfilenames(parent=window,title='Choose covers/images in order',filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp')]))
                    if not images:
                        return
                script=self.voice_project.script
                project=VoiceProject([CharacterProfile(**vars(p)) for p in self.voice_project.profiles],script,speaker_rules=dict(self.voice_project.speaker_rules),sound_files=self.voice_project.sound_files.copy(),pronunciation_files=[project_ipa.get().strip()] if project_ipa.get().strip() else [])
                if not self._confirm_piper_downloads('auto', SpeechSettings(), project, script, parent=window):
                    return
                status.set('Rendering passages with assigned voices…')
                def worker():
                    try:
                        if as_video:
                            result=render_multivoice_video(script,images,dest,project,auto_tag=True)
                        else:
                            result=render_multivoice(script,dest,project,auto_tag=True)
                        self.events.put(('ui',lambda:status.set('Saved: '+str(result)) if window.winfo_exists() else None))
                    except Exception as exc:
                        err=str(exc)
                        self.events.put(('ui',lambda:messagebox.showerror('Export failed',err,parent=window) if window.winfo_exists() else None))
                threading.Thread(target=worker,daemon=True).start()
            refresh()
            actions=ttk.Frame(panel)
            actions.pack(fill='x',pady=8)
            adaptive_grid(actions,[('Find Characters',detect_names),('Review Characters / Quotes',review_analysis),('Import Name List',import_names),('Detect Language + Recommend',suggest),('Download Piper Voices',self.voice_downloader),('Download Neural Voices',self.neural_voice_downloader),('Open Project',open_project),('Save Project',save_project),('Export Audio',export),('Export Video',lambda:export(True))],columns=2)

        def _menus(self):
            menu = tk.Menu(self.root)
            file_menu = tk.Menu(menu, tearoff=False)
            for label, action in [('Open entire project (.oamproj)', self.open_entire_project), ('Export entire project (.oamproj)', self.export_entire_project), ('Open document', self.open_file), ('Insert document', self.insert_file), ('Save text', self.save_text), ('Export audio', self.export), ('Make Video from Text + Images', self.video_dialog), ('Combine Chapters into Audiobooks', self.book_studio), ('Character Voices — Multiple Speakers', self.character_voice_studio), *([('Gutenberg Mode', self.gutenberg_mode)] if GUTENBERG_ENABLED else []), ('Batch convert', self.batch), ('Save voice preset', self.save_preset), ('Load voice preset', self.load_preset), ('Exit', self.close)]:
                file_menu.add_command(label=label, command=action)
            file_menu.add_command(label='Import clipboard as document', command=lambda:self.import_clipboard(replace=True))
            file_menu.add_command(label='Insert clipboard text', command=self.import_clipboard)
            file_menu.add_command(label='Set in-place project autosave…', command=self.configure_autosave)
            file_menu.add_command(label='Set automatic project backups…', command=self.configure_backups)
            file_menu.add_command(label='Save named project snapshot…', command=self.named_snapshot)
            file_menu.add_command(label='Create project with wizard…', command=self.project_wizard)
            file_menu.add_command(label='Save reusable project template…', command=self.save_project_template)
            file_menu.add_command(label='Project notes, category and tags', command=self.project_details)
            file_menu.add_command(label='Inspect saved project resources', command=self.review_archive)
            file_menu.add_command(label='Compare two project versions', command=lambda: self.review_archive(True))
            menu.add_cascade(label='File', menu=file_menu)
            file_menu.insert_command(3, label='Import scanned PDF / images / ZIP book…', command=self.import_scans)
            file_menu.insert_command(4, label='Import book page image folder…', command=self.import_scan_folder)
            edit = tk.Menu(menu, tearoff=False)
            for label, action in [('Undo', lambda: self.studio.history(-1)), ('Redo', lambda: self.studio.history(1)), ('Cut', lambda: self.editor.event_generate('<<Cut>>')), ('Copy', lambda: self.editor.event_generate('<<Copy>>')), ('Paste', lambda: self.editor.event_generate('<<Paste>>')), ('Select all', self.select_all), ('Find / Replace', self.find_replace), ('Go to line', self.goto_line), ('Clear', self.clear)]:
                edit.add_command(label=label, command=action)
            menu.add_cascade(label='Edit', menu=edit)
            view = tk.Menu(menu, tearoff=False)
            view.add_command(label='Toggle Fullscreen (F11)', command=self.toggle_fullscreen)
            view.add_command(label='Return to Windowed Mode (Esc)', command=lambda: self.root.attributes('-fullscreen', False))
            menu.add_cascade(label='View', menu=view)
            tools = tk.Menu(menu, tearoff=False)
            tools.add_command(label=f'Text tools ({len(TOOLS)} operations)', command=self.tools_dialog)
            tools.add_command(label='Document statistics', command=self.show_stats)
            tools.add_command(label='English spelling / OCR settings…', command=lambda: show_spelling_settings(self))
            tools.add_command(label='Check English spelling', command=lambda: self.spelling.check())
            tools.add_command(label='Suggestions at the cursor', accelerator='Shift+F10', command=lambda: self.spelling.show_at_cursor())
            tools.add_command(label='Correct all OCR / spelling suggestions', command=lambda: self.spelling.correct_all())
            tools.add_command(label='Apply high-confidence OCR fixes only', command=lambda: self.spelling.correct_all(safe_only=True))
            tools.add_command(label='Increase font size', command=lambda: self.resize_text(1))
            tools.add_command(label='Decrease font size', command=lambda: self.resize_text(-1))
            tools.add_command(label='Export timed captions (SRT / WebVTT)', command=self.export_captions)
            tools.add_command(label='Package finished book with checksums', command=self.package_release)
            tools.add_command(label='Audio processor', command=self.audio_dialog)
            tools.add_command(label='Edit audio metadata / embed cover', command=self.audio_metadata_dialog)
            tools.add_command(label='Create searchable PDF from scanned pages', command=self.searchable_pdf_dialog)
            tools.add_command(label='Check multilingual scripts / Unicode', command=self.manuscript_script_report)
            tools.add_command(label='Check export/publishing readiness', command=self.publication_preflight_dialog)
            tools.add_command(label='Hardware / GPU compatibility diagnostics', command=self.hardware_diagnostics)
            tools.add_command(label='Chapters, contents and duration estimate', command=self.chapter_overview)
            tools.add_command(label='Editorial reports (names, dialogue, readability)', command=self.editorial_reports)
            tools.add_command(label='Speech preparation (abbreviations, numbers, dates)', command=self.speech_preparation)
            tools.add_command(label='Export transcript (PDF / HTML / TXT)', command=self.export_transcript_dialog)
            menu.add_cascade(label='Tools', menu=tools)
            voices = tk.Menu(menu, tearoff=False)
            from .hardware import gpu_preference, apply_cpu_profile
            from .desktop_prefs import write as save_preferences
            from .acceleration import gpu_enabled
            self.gpu_var = tk.BooleanVar(value=gpu_enabled())
            voices.add_checkbutton(label='Use available GPU for speech, video, OCR and audio analysis', variable=self.gpu_var,
                                   command=lambda: (gpu_preference(self.gpu_var.get()),save_preferences(gpu_mode='auto' if self.gpu_var.get() else 'cpu')))
            profile_menu = tk.Menu(voices, tearoff=False)
            self.cpu_profile_var = tk.StringVar(value=os.environ.get('OPENMUKTI_CPU_PROFILE','system-default'))
            for profile in ('low','balanced','fast'):
                profile_menu.add_radiobutton(label=profile.capitalize(), value=profile,
                    variable=self.cpu_profile_var, command=lambda p=profile:apply_cpu_profile(p))
            voices.add_cascade(label='CPU performance (thread) profile', menu=profile_menu)
            voices.add_command(label='Refresh installed voices', command=self.refresh_voices)
            voices.add_command(label='Voice Library — favorites / packs / tags', command=self.voice_library_dialog)
            voices.add_command(label='Download Piper voices by language', command=self.voice_downloader)
            voices.add_command(label='Download Kokoro / Kitten / Pocket / Coqui voices', command=self.neural_voice_downloader)
            voices.add_command(label='Character Voice Studio', command=self.character_voice_studio)
            voices.add_command(label='Choose Piper model', command=self.pick_model)
            voices.add_command(label='Add Piper Voice Files', command=self.add_piper_voice)
            voices.add_command(label='How to Install Piper Voices', command=self.piper_help)
            voices.add_command(label='Choose dictionary', command=self.pick_dictionary)
            voices.add_command(label='IPA Pronunciation Editor',command=self.ipa_editor)
            voices.add_command(label='Insert inline IPA in text',command=self.insert_inline_ipa)
            menu.add_cascade(label='Voices', menu=voices)
            help_menu = tk.Menu(menu, tearoff=False)
            help_menu.add_command(label='Complete User Manual', command=self.show_manual)
            help_menu.add_command(label='Scanned books, OCR and English spelling', command=lambda:self._show_document('OCR and English spelling','OCR_AND_SPELLING.txt'))
            help_menu.add_command(label='Set Up Piper Voices', command=self.piper_help)
            help_menu.add_command(label='Inline IPA tags and custom pronunciations',command=lambda:self._show_document('IPA Pronunciation Guide','IPA_GUIDE.txt'))
            help_menu.add_command(label='How to Name Chapter Covers', command=self.naming_help)
            help_menu.add_separator()
            help_menu.add_command(label='About Us', command=self.about_us)
            menu.add_cascade(label='Help', menu=help_menu)
            from .studio_desk import DesktopStudio
            self.studio = DesktopStudio(self,menu)
            self.root.config(menu=menu)

        def _get_text(self):
            return self.editor.get('1.0', 'end-1c')

        def _replace_text(self, text):
            replace_text(self.editor, text)
            self.update_stats()

        def update_stats(self):
            stats = text_stats(self._get_text())
            self.counters_var.set(f"{stats['words']:,} words · {stats['characters']:,} chars · {stats['estimated_seconds'] / 60:.1f} min")

        def show_stats(self):
            self._show_json_report('Document statistics',text_stats(self._get_text()))

        def chapter_overview(self):
            from .book_structure import detect_chapters, table_of_contents, estimate_durations
            sections = detect_chapters(self._get_text())
            if not sections:
                messagebox.showinfo('Chapters', 'No text to analyze.')
                return
            estimate = estimate_durations(sections)
            toc = table_of_contents(sections)
            hours = estimate['total_estimated_seconds'] / 3600
            self._show_report('Chapters and table of contents',
                              f'{len(sections)} sections, about {hours:.2f} hours of narration at 160 wpm.\n\n{toc}')

        def editorial_reports(self):
            import json
            from .proofreading import (proper_name_consistency, dialogue_punctuation_issues,
                                       ocr_punctuation_report, readability)
            text = self._get_text()
            if not text.strip():
                messagebox.showinfo('Editorial reports', 'No text to analyze.')
                return
            report = {'readability': readability(text),
                      'proper_name_variants': proper_name_consistency(text)[:10],
                      'dialogue_punctuation': dialogue_punctuation_issues(text)[:10],
                      'ocr_artifacts': ocr_punctuation_report(text)[:10]}
            self._show_json_report('Editorial reports',report)

        def speech_preparation(self):
            from .narration_text import expand_abbreviations, speak_numbers, speak_dates_times
            text = self._get_text()
            if not text.strip():
                messagebox.showinfo('Speech preparation', 'No text to prepare.')
                return
            prepared = speak_dates_times(speak_numbers(expand_abbreviations(text), mode='ordinal-aware'))
            self._replace_text(prepared)
            self.status_var.set('Expanded abbreviations, numbers, dates and times for narration')

        def export_transcript_dialog(self):
            from .book_structure import detect_chapters
            from .publishing import export_transcript
            text = self._get_text()
            if not text.strip():
                messagebox.showinfo('Transcript', 'No text to export.')
                return
            target = filedialog.asksaveasfilename(
                defaultextension='.pdf',
                filetypes=[('PDF transcript', '*.pdf'), ('HTML transcript', '*.html'),
                           ('Plain text transcript', '*.txt')])
            if not target:
                return
            sections = detect_chapters(text)
            title = self.current_file.stem if self.current_file else 'Audiobook transcript'
            try:
                result = export_transcript(target, title, [(s.title, s.text) for s in sections])
            except (OSError, ValueError) as exc:
                messagebox.showerror('Transcript', str(exc))
                return
            self.status_var.set(f'Transcript saved: {result}')

        def _show_report(self, title, content):
            dialog = tk.Toplevel(self.root)
            dialog.title(title)
            fit_window(dialog, 760, 560, 420, 300)
            area = tk.Text(dialog, wrap='word')
            area.pack(fill='both', expand=True)
            area.insert('1.0', content)
            area.configure(state='disabled')

        def select_all(self, _event=None):
            self.editor.tag_add('sel', '1.0', 'end-1c')
            self.editor.mark_set('insert', '1.0')
            self.editor.see('insert')
            return 'break'

        def resize_text(self, delta):
            self.font_size = max(8, min(32, self.font_size + delta))
            self.editor.configure(font=(self.ui_font, self.font_size))
            self.status_var.set(f'Editor font size: {self.font_size}')

        def goto_line(self):
            line = simpledialog.askinteger('Go to line', 'Line number:', minvalue=1, parent=self.root)
            if line:
                self.editor.mark_set('insert', f'{line}.0')
                self.editor.see('insert')
                self.editor.focus_set()

        def find_replace(self):
            dialog = tk.Toplevel(self.root)
            dialog.title('Find and replace')
            fit_window(dialog, 470, 250, 340, 220)
            dialog.transient(self.root)
            find_text = tk.StringVar()
            replace_text = tk.StringVar()
            case_sensitive = tk.BooleanVar(value=False)
            frame = ttk.Frame(dialog, padding=12)
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text='Find').grid(row=0, column=0, sticky='w')
            ttk.Entry(frame, textvariable=find_text, width=42).grid(row=0, column=1, sticky='ew')
            ttk.Label(frame, text='Replace').grid(row=1, column=0, sticky='w')
            ttk.Entry(frame, textvariable=replace_text, width=42).grid(row=1, column=1, sticky='ew')
            ttk.Checkbutton(frame, text='Case sensitive', variable=case_sensitive).grid(row=2, column=1, sticky='w')
            frame.columnconfigure(1, weight=1)

            regex = tk.BooleanVar(value=False)
            ttk.Checkbutton(frame, text='Regular expression', variable=regex).grid(row=3, column=1, sticky='w')

            def find_next():
                term = find_text.get()
                if not term:
                    return
                import re
                self.editor.tag_remove('search', '1.0', 'end')
                offset = len(self.editor.get('1.0', 'insert'))
                content = self._get_text()
                try:
                    pattern = re.compile(term if regex.get() else re.escape(term), 0 if case_sensitive.get() else re.I)
                except re.error as exc:
                    messagebox.showerror('Search', str(exc), parent=dialog)
                    return
                match = pattern.search(content, offset) or pattern.search(content)
                if match:
                    index = f'1.0+{match.start()}c'
                    end = f'1.0+{match.end()}c'
                    self.editor.tag_configure('search', background='#eab308', foreground='#111827')
                    self.editor.tag_add('search', index, end)
                    self.editor.mark_set('insert', end)
                    self.editor.see(index)
                else:
                    messagebox.showinfo('Find', 'No matches found.', parent=dialog)

            def replace_all():
                import re
                needle = find_text.get()
                if not needle:
                    return
                flags = 0 if case_sensitive.get() else re.IGNORECASE
                try:
                    pattern = re.compile(needle if regex.get() else re.escape(needle), flags)
                    replacement = replace_text.get() if regex.get() else lambda match: replace_text.get()
                    original = self._get_text()
                    result, count = pattern.subn(replacement, original)
                except (re.error, IndexError) as exc:
                    messagebox.showerror('Find and replace', str(exc), parent=dialog)
                    return
                if not count:
                    messagebox.showinfo('Replace', 'No matches found.', parent=dialog)
                    return
                from difflib import unified_diff
                from itertools import islice
                preview = '\n'.join(islice(unified_diff(original.splitlines(), result.splitlines(), n=1, lineterm=''), 22))
                if not messagebox.askyesno('Apply replacements?', f'{count} matches. Preview (first changes):\n\n{preview[:1600]}', parent=dialog):
                    return
                self._replace_text(result)
                self.status_var.set(f'Replaced {count} occurrences')
            row = ttk.Frame(frame)
            row.grid(row=4, column=1, sticky='e', pady=8)
            ttk.Button(row, text='Find next', command=find_next).pack(side='left', padx=4)
            ttk.Button(row, text='Replace all', command=replace_all).pack(side='left', padx=4)

        def tools_dialog(self):
            dialog, body = self._dialog('Text preparation and OCR tools', 760, 610, padding=9)
            dialog.transient(self.root)
            search_var = tk.StringVar()
            ttk.Label(body, text=f'Search {len(TOOLS)} available transformations').pack(anchor='w')
            ttk.Entry(body, textvariable=search_var).pack(fill='x', pady=5)
            entries = tk.Listbox(body, bg=self.FIELD, fg=self.FG, selectbackground='#117b70', font=(self.ui_font, 10))
            entries.pack(fill='both', expand=True)
            preview = tk.Text(body, height=7, wrap='word', bg=self.FIELD, fg=self.FG, font=(self.ui_font, 10))
            preview.pack(fill='x', pady=7)
            visible = []

            def repopulate(*_args):
                entries.delete(0, 'end')
                visible.clear()
                query = search_var.get().casefold().strip()
                for op in TOOLS.values():
                    if not query or query in (op.name + ' ' + op.title + ' ' + op.group).casefold():
                        visible.append(op.name)
                        entries.insert('end', f'[{op.group}] {op.title} · {op.name}')

            def selected():
                indices = entries.curselection()
                return visible[indices[0]] if indices else None

            def make_preview(_event=None):
                name = selected()
                if name:
                    try:
                        result = transform(self._get_text(), [name])
                        preview.delete('1.0', 'end')
                        preview.insert('1.0', result[:12000])
                    except ValueError as exc:
                        messagebox.showerror('Text tool', str(exc), parent=dialog)

            def apply_selected():
                name = selected()
                if name:
                    self._replace_text(transform(self._get_text(), [name]))
                    self.status_var.set(f'Applied: {name}')
                    make_preview()
            search_var.trace_add('write', repopulate)
            entries.bind('<<ListboxSelect>>', make_preview)
            row = ttk.Frame(body)
            row.pack(fill='x')
            ttk.Button(row, text='Apply to editor', command=apply_selected).pack(side='right')
            ttk.Button(row, text='Close', command=dialog.destroy).pack(side='right', padx=8)
            repopulate()

        def _refresh_character_selector(self):
            names = [p.name for p in self.voice_project.profiles]
            if getattr(self, 'character_combo', None):
                self.character_combo.configure(values=names)
            if self.active_character_var.get() not in names:
                self.active_character_var.set('Narrator')

        def _effective_project(self, text=''):
            project = copy.deepcopy(self.voice_project)
            project.script = text
            ipa = self.ipa_dict_var.get().strip()
            if ipa and ipa not in project.pronunciation_files:
                project.pronunciation_files.append(ipa)
            return project

        def _tagged_text(self, text):
            if not self.use_character_voices_var.get():
                return text
            speaker = self.active_character_var.get()
            return f'[{speaker}] ' + text if speaker.casefold() != 'narrator' else text

        def stop_autosave(self):
            if self.autosave_timer is not None:
                self.root.after_cancel(self.autosave_timer)
                self.autosave_timer = None

        def configure_autosave(self):
            if not self.project_file:
                messagebox.showinfo('Project autosave', 'Save or open an entire project first.', parent=self.root)
                return
            target = self.project_file
            minutes = simpledialog.askinteger('Project autosave',
                f'Save changes to {target.name} every how many minutes? Enter 0 to disable.',
                minvalue=0, maxvalue=1440, initialvalue=5, parent=self.root)
            if minutes is None:
                return
            self.stop_autosave()
            if not minutes:
                self.status_var.set('Project autosave disabled')
                return
            def file_stamp():
                stat = target.stat()
                return stat.st_mtime_ns, stat.st_size, stat.st_ino
            try:
                stamp = file_stamp()
            except OSError as exc:
                messagebox.showerror('Project autosave', str(exc), parent=self.root)
                return
            previous = None
            def tick():
                nonlocal stamp, previous
                self.autosave_timer = None
                if self.project_file != target:
                    return
                try:
                    if file_stamp() != stamp:
                        raise ValueError('The project was changed outside this autosave session.')
                    if not self.active:
                        current = self._project_snapshot()
                        if current != previous:
                            save_project(target, current)
                            stamp = file_stamp()
                            previous = current
                            self.status_var.set('Autosaved project: ' + str(target))
                except Exception as exc:
                    self.status_var.set('Autosave stopped: ' + str(exc))
                    return
                self.autosave_timer = self.root.after(minutes * 60000, tick)
            self.autosave_timer = self.root.after(minutes * 60000, tick)
            self.status_var.set(f'Autosave enabled for {target.name} every {minutes} minutes')

        def configure_backups(self):
            minutes = simpledialog.askinteger('Automatic backups', 'Minutes between backups (0 disables them for this session)',
                                              minvalue=0, maxvalue=1440, initialvalue=5, parent=self.root)
            if minutes is None:
                return
            if minutes:
                folder = filedialog.askdirectory(parent=self.root, title='Choose a backup folder')
                if not folder:
                    return
                self.backup_folder = Path(folder)
            if self.backup_timer:
                self.root.after_cancel(self.backup_timer)
                self.backup_timer = None
            self.previous_backup = None
            self.backup_interval = minutes * 60000
            if minutes:
                self.backup_timer = self.root.after(self.backup_interval, self.automatic_backup)
            self.status_var.set(f'Backup interval: {minutes} minutes' if minutes else 'Automatic backups disabled')

        def automatic_backup(self):
            from datetime import datetime
            try:
                if not self.active:
                    project = self._project_snapshot()
                    if project != self.previous_backup:
                        target = self.backup_folder / datetime.now().strftime('Openmukti-%Y%m%d-%H%M%S-%f.oamproj')
                        save_project(target, project)
                        self.previous_backup = project
                        self.status_var.set('Recovery project saved: ' + str(target))
            except Exception as exc:
                self.status_var.set('Automatic backup failed: ' + str(exc))
            finally:
                self.backup_timer = self.root.after(self.backup_interval, self.automatic_backup)

        def named_snapshot(self):
            target = filedialog.asksaveasfilename(parent=self.root, title='Name this snapshot', defaultextension='.oamproj',
                                                  filetypes=[('Project snapshot', '*.oamproj')])
            if target:
                try:
                    save_project(target, self._project_snapshot())
                    self.status_var.set('Project snapshot saved: ' + target)
                except Exception as exc:
                    messagebox.showerror('Snapshot failed', str(exc), parent=self.root)

        def save_project_template(self):
            from .project_archive import project_template
            filename = filedialog.asksaveasfilename(parent=self.root, title='Save casting and production settings',
                defaultextension='.oamtemplate', filetypes=[('Project template', '*.oamtemplate')])
            if filename:
                try:
                    save_project(filename, project_template(self._project_snapshot()))
                    self.status_var.set('Template saved: ' + filename)
                except Exception as exc:
                    messagebox.showerror('Save template', str(exc), parent=self.root)

        def project_wizard(self):
            from .gui_workflows import project_wizard
            return project_wizard(self)

        def project_details(self):
            window, panel = self._dialog('Project details', 580, 460)
            entries = {}
            for key in ('category', 'tags', 'notes'):
                ttk.Label(panel, text=key.capitalize()).pack(anchor='w')
                field = tk.Text(panel, height=6 if key == 'notes' else 1, wrap='word')
                field.insert('1.0', getattr(self, 'production', {}).get(key, ''))
                field.pack(fill='x')
                entries[key] = field
            def apply():
                self.production = {**getattr(self, 'production', {}), **{key: field.get('1.0', 'end-1c') for key, field in entries.items()}}
                window.destroy()
            ttk.Button(panel, text='Apply to project', command=apply).pack(anchor='e')

        def review_archive(self, compare=False):
            from .project_review import compare_projects, resource_report
            def pick(title):
                return filedialog.askopenfilename(parent=self.root, title=title, filetypes=[('Openmukti project', '*.oamproj')])
            first = pick('Choose earlier project' if compare else 'Choose saved project')
            if not first:
                return
            try:
                if compare:
                    second = pick('Choose later project')
                    if not second:
                        return
                    report = compare_projects(first, second)
                else:
                    report = resource_report(first)
            except Exception as exc:
                messagebox.showerror('Project review', str(exc), parent=self.root)
                return
            window, panel = self._dialog('Project review', 850, 600, scroll=False)
            from tkinter.scrolledtext import ScrolledText
            field = ScrolledText(panel, wrap='word')
            field.pack(fill='both', expand=True)
            field.insert('1.0', report)
            field.configure(state='disabled')

        def _project_snapshot(self):
            settings = {**copy.deepcopy(getattr(self, '_imported_settings', {})),'engine':self.engine_var.get(),'voice':self.voice_var.get(),'model':self.model_var.get(),'speaker_id':speaker_id_from_label(self.speaker_var.get()),'language':self.tts_language_var.get(),
                        'dictionary':self.dict_var.get(),'ipa_dictionary':self.ipa_dict_var.get(),
                        'rate':self.rate_var.get(),'pitch':self.pitch_var.get(),'volume':self.volume_var.get(),
                        'ocr':self.ocr_var.get(),'font_size':self.font_size}
            settings['production'] = dict(getattr(self, 'production', {}))
            settings['ocr_import'] = self.ocr_settings.copy()
            settings['ocr_report'] = self.ocr_report.copy()
            settings.update(self.spelling.settings())
            return ProjectData(text=self._get_text(),settings=settings,voice_project=copy.deepcopy(self.voice_project),
                books=copy.deepcopy(self.books),video_images=[Path(x) for x in self.video_images],
                video_audio=Path(self.video_audio) if self.video_audio else None,video_settings=self.video_options.copy(),
                book_settings=self.book_export_settings.copy(),current_filename=self.current_file.name if self.current_file else '',
                active_character=self.active_character_var.get(),use_character_voices=self.use_character_voices_var.get())

        def export_entire_project(self):
            if self.active:
                messagebox.showwarning('Project export','Finish the running job first.')
                return
            filename = filedialog.asksaveasfilename(parent=self.root,title='Export complete audiobook project',defaultextension='.oamproj',filetypes=[('Openmukti complete project','*.oamproj')])
            if not filename:
                return
            try:
                save_project(filename,self._project_snapshot())
                self.stop_autosave()
                self.project_file=Path(filename)
                self._saved_text=self._get_text()
                from .gui_workflows import remember_recent
                remember_recent(filename)
                self.status_var.set('Complete project saved: '+str(filename))
            except Exception as exc:
                messagebox.showerror('Project export failed',str(exc),parent=self.root)

        def open_entire_project(self, filename=None):
            if self.active:
                messagebox.showwarning('Project import','Finish the running job first.')
                return
            filename=filename or filedialog.askopenfilename(parent=self.root,title='Open complete audiobook project',filetypes=[('Openmukti complete project','*.oamproj')])
            if not filename:
                return
            if not self._confirm_replace_manuscript():
                return
            new_workspace=tempfile.TemporaryDirectory(prefix='openmukti-import-')
            try:
                project=load_project(filename,new_workspace.name)
            except Exception as exc:
                new_workspace.cleanup()
                messagebox.showerror('Project import failed',str(exc),parent=self.root)
                return
            old=self._project_workspace
            self.stop_autosave()
            self._project_workspace=new_workspace
            self.project_file=Path(filename)
            self._saved_text=project.text
            from .gui_workflows import remember_recent
            remember_recent(filename)
            self._imported_settings=copy.deepcopy(project.settings)
            self._replace_text(project.text)
            self.ocr_settings = project.settings.get('ocr_import', {})
            self.production = project.settings.get('production', {})
            self.ocr_report = project.settings.get('ocr_report', {})
            self.spelling.restore(project.settings)
            self.voice_project=project.voice_project
            self.books=project.books
            self.video_images=[str(x) for x in project.video_images]
            self.video_audio=str(project.video_audio) if project.video_audio else None
            self.video_options=project.video_settings
            self.book_export_settings=project.book_settings
            self.current_file=None
            for key,var in [('engine',self.engine_var),('voice',self.voice_var),('model',self.model_var),('language',self.tts_language_var),('dictionary',self.dict_var),
                            ('ipa_dictionary',self.ipa_dict_var),('rate',self.rate_var),('pitch',self.pitch_var),
                            ('volume',self.volume_var),('ocr',self.ocr_var)]:
                if key in project.settings:
                    var.set(project.settings[key])
            self.speaker_var.set(f"Speaker {int(project.settings.get('speaker_id', 0))}")
            self._update_piper_speakers()
            self.font_size=int(project.settings.get('font_size',self.font_size))
            self.editor.configure(font=(self.ui_font,self.font_size))
            self.active_character_var.set(project.active_character)
            self.use_character_voices_var.set(project.use_character_voices)
            self._refresh_character_selector()
            self.refresh_voices()
            self.update_stats()
            self.status_var.set('Opened complete project: '+str(filename))
            if old is not None:
                old.cleanup()

        def save_preset(self):
            import json
            path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Voice presets', '*.json')])
            if path:
                preset = {'engine': self.engine_var.get(), 'voice': self.voice_var.get(), 'model': self.model_var.get(), 'speaker_id': speaker_id_from_label(self.speaker_var.get()), 'language':self.tts_language_var.get(), 'dictionary': self.dict_var.get(), 'rate': self.rate_var.get(), 'pitch': self.pitch_var.get(), 'volume': self.volume_var.get(), 'ocr': self.ocr_var.get()}
                Path(path).write_text(json.dumps(preset, indent=2), encoding='utf-8')
                self.status_var.set('Voice preset saved')

        def load_preset(self):
            import json
            path = filedialog.askopenfilename(filetypes=[('Voice presets', '*.json')])
            if path:
                try:
                    data = json.loads(Path(path).read_text(encoding='utf-8'))
                    if not isinstance(data, dict) or data.get('engine', 'auto') not in ['auto', *self.engines]:
                        raise ValueError('Unrecognized voice preset')
                    for key, var in [('engine', self.engine_var), ('voice', self.voice_var), ('model', self.model_var), ('language', self.tts_language_var), ('dictionary', self.dict_var), ('rate', self.rate_var), ('pitch', self.pitch_var), ('volume', self.volume_var), ('ocr', self.ocr_var)]:
                        if key in data:
                            var.set(data[key])
                    self.speaker_var.set(f"Speaker {int(data.get('speaker_id', 0))}")
                    self._update_piper_speakers()
                    self.refresh_voices()
                    self.status_var.set('Voice preset loaded')
                except (OSError, ValueError, TypeError) as exc:
                    messagebox.showerror('Preset', str(exc))

        def export_captions(self):
            from .release_tools import caption_export
            source = filedialog.askopenfilename(parent=self.root, title='Open timed cues', filetypes=[('Caption cues', '*.json *.srt *.vtt')])
            if source:
                target = filedialog.asksaveasfilename(parent=self.root, defaultextension='.vtt', filetypes=[('WebVTT', '*.vtt'), ('SubRip', '*.srt')])
                if target:
                    try:
                        caption_export(source, target)
                        self.status_var.set('Saved captions: ' + target)
                    except Exception as exc:
                        messagebox.showerror('Caption export', str(exc), parent=self.root)

        def package_release(self):
            from .release_tools import release_archive
            folder = filedialog.askdirectory(parent=self.root, title='Select finished book folder')
            if folder:
                target = filedialog.asksaveasfilename(parent=self.root, title='Save outside the book folder', defaultextension='.zip')
                if target:
                    def pack():
                        try:
                            release_archive(folder, target)
                            self.events.put(('done', 'Packaged book: ' + target))
                        except Exception as exc:
                            self.events.put(('error', str(exc)))
                    threading.Thread(target=pack, daemon=True).start()

        def audio_dialog(self):
            from .gui_workflows import audio_processor
            return audio_processor(self)

        def _params(self):
            settings = SpeechSettings(voice=self.voice_var.get().strip(), rate=self.rate_var.get(), pitch=self.pitch_var.get(), volume=self.volume_var.get(), model=self.model_var.get().strip(), speaker_id=speaker_id_from_label(self.speaker_var.get()),language=self.tts_language_var.get().strip() or 'auto')
            dictionary = self.dict_var.get().strip()
            options = JobOptions(repair_ocr=self.ocr_var.get(), dictionaries=(dictionary,) if dictionary else (),ipa_dictionaries=(self.ipa_dict_var.get().strip(),) if self.ipa_dict_var.get().strip() else ())
            return (self.engine_var.get(), settings, options)

        def _launch(self, mode, output=None, files=None, audio_format='wav', images=None, existing_audio=None, video_settings=None):
            if self.active:
                messagebox.showinfo('Speech running', 'Stop the current job first.')
                return
            try:
                engine_name, settings, options = self._params()
                text = self.editor.get('1.0', 'end-1c')
                if mode != 'batch' and not (mode == 'video' and existing_audio) and (not text.strip()):
                    messagebox.showwarning('Missing text', 'Enter some text or open a document.')
                    return
                use_characters=self.use_character_voices_var.get()
                from .timeline_tags import has_timeline_tags
                # Timing grammar needs the multivoice timeline path even if the
                # user disabled personality/voice-profiles. Narrator falls back
                # to the selected main engine in that case.
                timed = has_timeline_tags(text)
                project=(self._effective_project() if use_characters else
                         VoiceProject(sound_files=self.voice_project.sound_files.copy()) if timed else None)
                script=self._tagged_text(text)
                batch_prefix=(f'[{self.active_character_var.get()}] ' if use_characters and self.active_character_var.get().casefold()!='narrator' else '')
                if not (mode == 'video' and existing_audio) and not self._confirm_piper_downloads(
                        engine_name, settings, project, script if mode != 'batch' else ''):
                    return
                self.active = True
                self.control = RunControl()
                self._start_progress('Preparing audiobook creation…')
                self.pause_var.set('Pause between sentences')
                self._set_buttons()

                def progress(done, total):
                    self.events.put(('progress', done, total))

                def status(event):
                    self.events.put(('job_progress', event))

                def task():
                    try:
                        engine = get_engine(engine_name, settings.model, settings.voice)
                        if mode == 'speak':
                            if project:
                                from .engines.builtin import play_wav
                                with tempfile.TemporaryDirectory(prefix='openmukti-main-preview-') as work:
                                    wav=render_multivoice(script,Path(work)/'preview.wav',project,auto_tag=True,control=self.control,default_engine=engine,default_settings=settings,speech_options=options,status=subprogress(status,0,.8))
                                    emit(status,.8,'Playing the character narration')
                                    play_wav(wav,self.control)
                            else:
                                speak_text(text, engine, settings, options, self.control, status=status)
                            self.events.put(('done', 'Finished speaking.'))
                        elif mode == 'export':
                            rendered = render_multivoice(script,output,project,auto_tag=True,control=self.control,default_engine=engine,default_settings=settings,speech_options=options,status=status) if project else render_text(text, output, engine, settings, options, self.control, status=status)
                            self.events.put(('done', f'Audio saved: {rendered}'))
                        elif mode == 'video':
                            if project and not existing_audio:
                                result=render_multivoice_video(script,images or [],output,project,auto_tag=True,video_options=video_settings or VideoOptions(),control=self.control,default_engine=engine,default_settings=settings,speech_options=options,status=status)
                            else:
                                result=render_video(images or [],output,audio=existing_audio,text=text,engine=engine if not existing_audio else None,settings=settings,speech_options=options,video_options=video_settings or VideoOptions(),control=self.control,status=status)
                            self.events.put(('done', f'Video saved: {result}'))
                        elif mode == 'batch':
                            errors = []
                            for i, file in enumerate(files):
                                self.control.check()
                                file_status=subprogress(status,.98*i/len(files),.98*(i+1)/len(files),f'File {i+1} of {len(files)}: {Path(file).name}')
                                emit(file_status,0,'Loading document')
                                try:
                                    content = read_document(file)
                                    dest = Path(output) / (Path(file).stem + '.' + audio_format)
                                    render_multivoice(batch_prefix+content,dest,project,auto_tag=True,control=self.control,default_engine=engine,default_settings=settings,speech_options=options,status=file_status) if project else render_text(content,dest,engine,settings,options,self.control,status=file_status)
                                except Exception as exc:
                                    errors.append(f'{Path(file).name}: {exc}')
                            if errors:
                                self.events.put(('error', 'Some files failed:\n' + '\n'.join(errors[:10])))
                            else:
                                self.events.put(('done', f'Batch complete: {len(files)} {audio_format.upper()} files saved in {output}'))
                    except Exception as exc:
                        self.events.put(('error', str(exc)))
                    finally:
                        self.events.put(('idle',))
                threading.Thread(target=task, daemon=True).start()
            except Exception as exc:
                self.active = False
                messagebox.showerror('Cannot start speech job', str(exc))
                self._set_buttons()

        def video_dialog(self):
            if self.active:
                messagebox.showinfo('Busy', 'Finish or stop the current speech job first.')
                return
            window, panel = self._dialog('Animated Audiobook Video', 800, 790, min_width=480, min_height=390, padding=12)
            window.transient(self.root)
            window.grab_set()
            ttk.Label(panel, text='TEXT + COVER ART TO VIDEO', style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel, text='Cover artwork stays available beneath animated text. Optional for animated modes, required for classic slideshow.', style='Muted.TLabel',wraplength=600).pack(anchor='w', pady=(5, 12))
            paths: list[str] = self.video_images
            image_row = ttk.Frame(panel)
            image_row.pack(fill='both', expand=True)
            image_box = tk.Listbox(image_row, bg=self.FIELD, fg=self.FG, selectbackground='#256c72', relief='flat', height=7, selectmode='extended')
            image_box.pack(side='left', fill='both', expand=True)
            controls = ttk.Frame(image_row)
            controls.pack(side='right', fill='y', padx=(8, 0))

            def repaint():
                image_box.delete(0, 'end')
                for item in paths:
                    image_box.insert('end', Path(item).name)

            def add():
                picked = filedialog.askopenfilenames(parent=window, title='Choose images in slide order', filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff')])
                paths.extend(picked)
                repaint()

            def remove():
                for index in reversed(image_box.curselection()):
                    paths.pop(index)
                repaint()

            def move(step):
                selected = image_box.curselection()
                if len(selected) != 1:
                    return
                index = selected[0]
                dest = index + step
                if 0 <= dest < len(paths):
                    paths[index], paths[dest] = paths[dest], paths[index]
                    repaint()
                    image_box.selection_set(dest)

            for label, action in [('Add images', add), ('Remove', remove), ('Move up', lambda: move(-1)), ('Move down', lambda: move(1))]:
                ttk.Button(controls, text=label, command=action).pack(fill='x', pady=(0, 7))
            dimensions = ttk.Frame(panel)
            dimensions.pack(fill='x', pady=(15, 8))
            aspect = tk.StringVar(value=self.video_options.get('aspect','16:9'))
            resolution = tk.StringVar(value=self.video_options.get('resolution','720p'))
            fps = tk.StringVar(value=str(self.video_options.get('fps',30)))
            fit = tk.StringVar(value=self.video_options.get('fit','contain'))
            for index, (name, var, values) in enumerate([('Aspect ratio (or custom W:H)', aspect, list(ASPECTS)), ('Resolution', resolution, list(HEIGHTS)), ('Frame rate', fps, ['24', '25', '30', '60']), ('Image scaling', fit, ['contain', 'cover'])]):
                cell = ttk.Frame(dimensions)
                cell.grid(row=0, column=index, padx=(0, 12), sticky='ew')
                dimensions.columnconfigure(index, weight=1)
                ttk.Label(cell, text=name).pack(anchor='w')
                ttk.Combobox(cell, textvariable=var, values=values, state='normal' if var is aspect else 'readonly', width=11).pack(fill='x')
            animation = tk.StringVar(value=self.video_options.get('animation','none'))
            dimensions = tk.StringVar(value=self.video_options.get('dimensions',''))
            font_path = tk.StringVar(value=self.video_options.get('font_path',''))
            font_size = tk.StringVar(value=str(self.video_options.get('font_size',0)))
            text_color = tk.StringVar(value=self.video_options.get('text_color','FFFFFF'))
            panel_opacity = tk.StringVar(value=str(self.video_options.get('panel_opacity',165)))
            timing_file = tk.StringVar(value=self.video_options.get('timing_file',''))
            pen_width = tk.StringVar(value=str(self.video_options.get('pen_width',0)))
            nib_angle = tk.StringVar(value=str(self.video_options.get('nib_angle',-32)))
            stroke_library = tk.StringVar(value=self.video_options.get('stroke_library',''))
            strict_strokes = tk.BooleanVar(value=self.video_options.get('strict_strokes',False))
            paper_grain = tk.StringVar(value=str(self.video_options.get('paper_grain',14)))
            brush_dryness = tk.StringVar(value=str(self.video_options.get('brush_dryness',12)))
            pen_tool = tk.StringVar(value=self.video_options.get('pen_tool','auto'))
            style_area=ttk.Frame(panel); style_area.pack(fill='x',pady=(7,3))
            for idx,(label,var,values,width) in enumerate([
                ('Text motion / handwriting',animation,list(MODES),18),
                ('Exact dimensions (optional, e.g. 1080x1920)',dimensions,None,19),
                ('Font size (0 = auto)',font_size,None,8),
                ('Text RGB hex',text_color,None,10),
                ('Background panel alpha (0–255)',panel_opacity,None,8),
                ('Pen thickness (0 = auto, 1–40)',pen_width,None,8),
                ('Calligraphy nib tilt (-80 to 80°)',nib_angle,None,8),
                ('Paper grain (0–80)',paper_grain,None,8),
                ('Brush dryness (0–80)',brush_dryness,None,8),
                ('Drawing instrument',pen_tool,['auto','pencil','ballpoint','fountain','brush','broad-nib'],17),
            ]):
                cell=ttk.Frame(style_area);cell.grid(row=idx//2,column=idx%2,sticky='ew',padx=(0,12),pady=3)
                style_area.columnconfigure(idx%2,weight=1)
                ttk.Label(cell,text=label).pack(anchor='w')
                if values is None:
                    ttk.Entry(cell,textvariable=var,width=width).pack(fill='x')
                else:
                    ttk.Combobox(cell,textvariable=var,values=values,state='readonly',width=width).pack(fill='x')
            def file_row(label,var,extensions):
                ttk.Label(panel,text=label).pack(anchor='w',pady=(7,0))
                row=ttk.Frame(panel);row.pack(fill='x')
                ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
                def browse():
                    found=filedialog.askopenfilename(parent=window,title=label,filetypes=extensions)
                    if found:var.set(found)
                ttk.Button(row,text='Browse',command=browse).pack(side='left',padx=(5,0))
            file_row('Unicode/OpenType font for your script (optional)',font_path,[('Font files','*.ttf *.otf *.ttc'),('All files','*.*')])
            file_row('Precise word/phrase timings, JSON/SRT/VTT (optional)',timing_file,[('Timed text','*.json *.srt *.vtt'),('All files','*.*')])
            file_row('Hand-drawn Unicode stroke library (JSON, optional)',stroke_library,[('OpenMukti stroke library','*.json'),('All files','*.*')])
            studio=ttk.Frame(panel);studio.pack(fill='x',pady=(4,2))
            def edit_strokes():
                from .stroke_studio import open_stroke_studio
                try:open_stroke_studio(window,stroke_library.get(),lambda path:stroke_library.set(path))
                except (ValueError,OSError) as error:
                    messagebox.showerror('Stroke Studio',str(error),parent=window)
            ttk.Button(studio,text='Open Stroke Studio — draw actual pen trajectories',command=edit_strokes).pack(side='left')
            ttk.Checkbutton(studio,text='Strict drawn-only (no auto-tracing)',variable=strict_strokes).pack(side='left',padx=(12,0))
            ttk.Label(panel,text='Stroke Studio draws authentic Unicode pen paths independent of fonts. The output is painted from round nibs or bristle/angled brush, not printed glyphs. Without a saved character template, automatic font-guided trajectory reconstruction is used (not authentic stroke order). Choose Strict drawn-only to require real stroke templates. For accurate speech sync provide word alignment.',style='Muted.TLabel',wraplength=630).pack(anchor='w',pady=(5,2))
            soundtrack = tk.StringVar(value=self.video_audio or '')
            row = ttk.Frame(panel)
            row.pack(fill='x', pady=(8, 3))
            ttk.Label(row, text='Existing narration file (optional; skips speech synthesis)').pack(anchor='w')
            audio_row = ttk.Frame(panel)
            audio_row.pack(fill='x')
            ttk.Entry(audio_row, textvariable=soundtrack).pack(side='left', fill='x', expand=True)

            def choose_audio():
                found = filedialog.askopenfilename(parent=window, title='Select audio track', filetypes=[('Audio', '*.wav *.mp3 *.flac *.m4a *.ogg *.opus *.aac *.wma'), ('All files', '*.*')])
                if found:
                    soundtrack.set(found)

            ttk.Button(audio_row, text='Browse', command=choose_audio).pack(side='left', padx=(7, 0))
            caption = tk.BooleanVar(value=self.video_options.get('captions',False))
            ttk.Checkbutton(panel, text='Create approximate-timing SRT captions from editor text', variable=caption).pack(anchor='w', pady=(8, 0))
            ttk.Label(panel, text='Output: MP4, MKV, MOV, or WebM. Integrated media tools used when bundled.', style='Muted.TLabel').pack(anchor='w', pady=(4, 0))
            def remember_video(*_args):
                # Tk fires on every keystroke, including incomplete numeric
                # values such as '-' while editing the calligraphy nib angle.
                # Preserve the last valid settings until the user finishes.
                try:
                    numbers=(int(fps.get()),int(font_size.get() or 0),
                             int(panel_opacity.get() or 0),int(pen_width.get() or 0),
                             int(nib_angle.get() or -32),int(paper_grain.get() or 0),int(brush_dryness.get() or 0))
                except ValueError:
                    return
                self.video_audio=soundtrack.get().strip() or None
                self.video_options={**self.video_options,'aspect':aspect.get(),'resolution':resolution.get(),'fps':numbers[0],
                                    'fit':fit.get(),'captions':caption.get(),'animation':animation.get(),'dimensions':dimensions.get().strip(),
                                    'font_path':font_path.get().strip(),'font_size':numbers[1],'text_color':text_color.get().strip(),
                                    'panel_opacity':numbers[2],'timing_file':timing_file.get().strip(),
                                    'pen_width':numbers[3],'nib_angle':numbers[4],
                                    'stroke_library':stroke_library.get().strip(),'strict_strokes':strict_strokes.get(),
                                    'paper_grain':numbers[5],'brush_dryness':numbers[6],'pen_tool':pen_tool.get()}
            for v in (aspect,resolution,fps,fit,soundtrack,caption,animation,dimensions,font_path,font_size,text_color,panel_opacity,timing_file,pen_width,nib_angle,stroke_library,strict_strokes,paper_grain,brush_dryness,pen_tool):
                v.trace_add('write',remember_video)
            remember_video()
            repaint()

            def start():
                if not paths and animation.get()=='none' and not self.video_options.get('storyboard'):
                    messagebox.showwarning('Missing images', 'Add a cover image or select an animated text mode.', parent=window)
                    return
                narrative = self.editor.get('1.0', 'end-1c')
                if (not soundtrack.get() or caption.get() or animation.get()!='none') and not narrative.strip() and not timing_file.get().strip():
                    messagebox.showwarning('Missing narration', 'Enter narration text or select existing audio. Captions require text.', parent=window)
                    return
                try:
                    video_settings=VideoOptions(**{**self.video_options,'aspect':aspect.get(),'resolution':resolution.get(),'fps':int(fps.get()),'fit':fit.get(),'captions':caption.get(),
                                                  'animation':animation.get(),'dimensions':dimensions.get().strip(),'font_path':font_path.get().strip(),
                                                  'font_size':int(font_size.get()),'text_color':text_color.get().strip(),
                                                  'panel_opacity':int(panel_opacity.get()),'timing_file':timing_file.get().strip(),
                                                  'pen_width':int(pen_width.get()),'nib_angle':int(nib_angle.get()),
                                                  'stroke_library':stroke_library.get().strip(),'strict_strokes':strict_strokes.get(),
                                                  'paper_grain':int(paper_grain.get()),'brush_dryness':int(brush_dryness.get()),
                                                  'pen_tool':pen_tool.get()})
                    video_size(video_settings.aspect,video_settings.resolution,video_settings.dimensions)
                except (TypeError,ValueError) as exc:
                    messagebox.showerror('Invalid video settings',str(exc),parent=window)
                    return
                destination = filedialog.asksaveasfilename(parent=window, defaultextension='.mp4', filetypes=[('MP4 video', '*.mp4'), ('WebM video', '*.webm'), ('Matroska video', '*.mkv'), ('QuickTime video', '*.mov')])
                if not destination:
                    return
                selections = list(paths)
                existing_audio = soundtrack.get().strip() or None
                window.destroy()
                self._launch('video', output=destination, images=selections, existing_audio=existing_audio, video_settings=video_settings)

            ttk.Button(panel, text='Export audiobook video…', command=start, style='Accent.TButton').pack(anchor='e', pady=(15, 0))

        def gutenberg_mode(self):
            window, panel = self._dialog('Gutenberg Mode — One-click ebook cleanup', 760, 590, padding=12)
            ttk.Label(panel, text='GUTENBERG MODE', style='Title.TLabel').pack(anchor='w')
            ttk.Label(panel, text='Removes Gutenberg header/footer, contents pages, placeholders and page-number artifacts. Source files are not changed.', style='Muted.TLabel', wraplength=700).pack(anchor='w', pady=(4,12))
            toc = tk.BooleanVar(value=True)
            placeholders = tk.BooleanVar(value=True)
            pages = tk.BooleanVar(value=True)
            reflow = tk.BooleanVar(value=True)
            toggles = ttk.Frame(panel)
            toggles.pack(fill='x')
            for label, var in [('Remove table of contents',toc), ('Remove image placeholders',placeholders), ('Remove page numbers',pages), ('Repair wrapped paragraphs',reflow)]:
                ttk.Checkbutton(toggles, text=label, variable=var).pack(anchor='w', pady=2)
            summary = tk.StringVar(value='Select an action below.')
            ttk.Label(panel, textvariable=summary).pack(anchor='w', pady=12)
            text_preview = tk.Text(panel, bg=self.FIELD, fg=self.FG, wrap='word', height=12, font=(self.ui_font, 10))
            text_preview.pack(fill='both', expand=True)

            def clean(text):
                return clean_gutenberg(text, GutenbergOptions(remove_toc=toc.get(), remove_image_placeholders=placeholders.get(), remove_page_numbers=pages.get(), reflow_paragraphs=reflow.get()))

            def preview():
                report = clean(self._get_text())
                text_preview.delete('1.0','end')
                text_preview.insert('1.0', report.content[:16000])
                summary.set(f'{report.chapter_count} chapters · header {"removed" if report.removed_header else "not found"} · footer {"removed" if report.removed_footer else "not found"} · {report.removed_placeholders} placeholders removed')
                return report

            def apply_to_editor():
                report = preview()
                if not report.content:
                    messagebox.showwarning('Gutenberg Mode', 'No content remains after cleanup.', parent=window)
                    return
                self._replace_text(report.content)
                self.status_var.set('Gutenberg Mode applied to editor')

            def bulk():
                docs = filedialog.askopenfilenames(parent=window, title='Select ebook files in bulk', filetypes=[('Ebooks', '*.txt *.md *.odt *.fb2 *.fb2.zip *.epub *.docx *.html *.htm *.pdf *.rtf')])
                if not docs:
                    return
                output = filedialog.askdirectory(parent=window, title='Output directory for cleaned books')
                if not output:
                    return
                def task():
                    errors=[]
                    for n, file in enumerate(docs, 1):
                        try:
                            report=clean(read_document(file))
                            dest=Path(output)/(Path(file).stem+'-cleaned.txt')
                            dest.write_text(report.content, encoding='utf-8')
                            self.events.put(('progress', n, len(docs)))
                        except Exception as exc:
                            errors.append(f'{Path(file).name}: {exc}')
                    self.events.put(('error' if errors else 'done', '\n'.join(errors[:8]) if errors else f'Gutenberg Mode: cleaned {len(docs)} ebooks in {output}'))
                summary.set(f'Processing {len(docs)} ebooks…')
                threading.Thread(target=task, daemon=True).start()

            row=ttk.Frame(panel)
            row.pack(fill='x', pady=(12,0))
            for label, action in [('Preview editor', preview), ('Clean editor in one click', apply_to_editor), ('Bulk clean ebook files…', bulk)]:
                ttk.Button(row, text=label, command=action).pack(side='left', padx=(0,8))
            preview()

        def book_studio(self):
            if self.active:
                messagebox.showinfo(APP_NAME, 'A job is running. Finish or stop it first.')
                return
            window, panel = self._dialog(f'{APP_NAME} — Combine Chapters into Audiobooks', 1060, 730, min_width=570, min_height=400, padding=10)
            ttk.Label(panel,text='COMBINE CHAPTERS INTO AUDIOBOOKS',style='Title.TLabel').pack(anchor='w')
            book_hint=ttk.Label(panel,text='Import books and chapters; optionally match each chapter to a cover image. Export audio-only or video audiobooks, complete books or individual chapters.',style='Muted.TLabel',wraplength=540)
            book_hint.pack(anchor='w',pady=(4,8))
            panel.bind('<Configure>',lambda event:book_hint.configure(wraplength=max(180,event.width-30)),add='+')
            ttk.Label(panel, text='Naming tip: Chapter 01.txt + Chapter 01.png, Chapter 02.txt + Chapter 02.jpg in the same book folder.', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
            ttk.Button(panel, text='How should I name my books, chapters and covers?', command=self.naming_help).pack(anchor='w', pady=(0, 8))
            books: list[Book] = self.books
            import_queue = queue.Queue()
            row=ttk.Frame(panel)
            row.pack(fill='x',pady=8)
            table_frame=ttk.Frame(panel)
            table_frame.pack(fill='both',expand=True)
            tree=ttk.Treeview(table_frame, columns=('book','chapter','text','cover','audio'), show='headings',selectmode='browse',height=9,style='Book.Treeview')
            for key,name,width in [('book','Book',170),('chapter','Chapter',160),('text','Text file / extracted',250),('cover','Cover image',270),('audio','Recorded narration',170)]:
                tree.heading(key,text=name)
                tree.column(key,width=width,minwidth=75)
            tree.pack(side='top',fill='both',expand=True)
            xbar=ttk.Scrollbar(table_frame,orient='horizontal',command=tree.xview)
            tree.configure(xscrollcommand=xbar.set)
            xbar.pack(side='bottom',fill='x')
            mapping={}
            hint=tk.StringVar(value='Add a book folder or a manifest to begin. Books are queued in the order shown.')
            ttk.Label(panel,textvariable=hint,style='Muted.TLabel',wraplength=960).pack(anchor='w',pady=(6,4))

            def update():
                if not tree.winfo_exists():
                    return
                tree.delete(*tree.get_children())
                mapping.clear()
                for bi,book in enumerate(books):
                    for ci,ch in enumerate(book.chapters):
                        ref=tree.insert('','end',values=(book.title,ch.title,str(ch.text_file) if ch.text_file else ('Embedded text' if ch.text else ''),', '.join(p.name for p in ch.images) or 'MISSING',ch.audio.name if ch.audio else 'Synthesize'))
                        mapping[ref]=(bi,ci)
                hint.set(f'{len(books)} books · {sum(len(b.chapters) for b in books)} chapters · {sum(not c.images for b in books for c in b.chapters)} missing cover matches. Select a chapter to set/replace its cover.')

            def poll_imports():
                if not window.winfo_exists():
                    return
                try:
                    while True:
                        incoming, errors = import_queue.get_nowait()
                        books.extend(incoming)
                        update()
                        if errors:
                            messagebox.showwarning('Book import', '\n'.join(errors[:10]), parent=window)
                except queue.Empty:
                    pass
                window.after(120, poll_imports)

            def import_folder():
                root=filedialog.askdirectory(parent=window,title='Select library folder containing separate book folders, or a single book folder')
                if root:
                    hint.set('Scanning book folders and covers…')
                    def work():
                        try:
                            import_queue.put((discover_books(root),[]))
                        except Exception as exc:
                            import_queue.put(([],[str(exc)]))
                    threading.Thread(target=work,daemon=True).start()

            def import_manifest():
                file=filedialog.askopenfilename(parent=window,title='Select Openmukti book manifest',filetypes=[('Openmukti JSON manifest','*.json')])
                if file:
                    try:
                        books.extend(load_manifest(file))
                        update()
                    except Exception as exc:
                        messagebox.showerror('Import manifest',str(exc),parent=window)

            def import_files():
                paths=filedialog.askopenfilenames(parent=window,title='Select many whole ebooks',filetypes=[('Ebook files and scan archives','*.txt *.md *.odt *.fb2 *.fb2.zip *.epub *.docx *.html *.htm *.pdf *.rtf *.zip *.cbz *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp')])
                if not paths:
                    return
                hint.set(f'Importing {len(paths)} ebook files…')
                def work():
                    incoming=[]
                    errors=[]
                    for path in paths:
                        file=Path(path)
                        try:
                            covers=_files(file.parent,{'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'})
                            match=_match_cover(file.stem,covers)
                            chapters=_split_ebook(file,match,gutenberg=False)
                            incoming.append(Book(file.stem,chapters))
                        except Exception as exc:
                            errors.append(f'{file.name}: {exc}')
                    import_queue.put((incoming,errors))
                threading.Thread(target=work,daemon=True).start()

            def set_cover():
                selected=tree.selection()
                if not selected:
                    return
                bi,ci=mapping[selected[0]]
                files=filedialog.askopenfilenames(parent=window,title='Choose image(s) for this chapter',filetypes=[('Images','*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff')])
                if files:
                    books[bi].chapters[ci].images=[Path(file) for file in files]
                    update()

            def remove_book():
                selected=tree.selection()
                if selected:
                    bi,_=mapping[selected[0]]
                    books.pop(bi)
                    update()

            def review_chapter():
                selected=tree.selection()
                if selected:
                    bi,ci=mapping[selected[0]]
                    show_chapter_review(self,books[bi].chapters[ci],update)

            tree.bind('<Double-1>',lambda _event:review_chapter())
            adaptive_grid(row,[('Add folder of books',import_folder),('Add many ebooks',import_files),('Import JSON manifest',import_manifest),('Review chapter OCR / spelling',review_chapter),('Assign selected chapter cover',set_cover),('Remove selected book',remove_book)],columns=2)
            settings_row=ttk.Frame(panel)
            settings_row.pack(fill='x',pady=(12,8))
            stored=self.book_export_settings
            mode=tk.StringVar(value=stored.get('mode','both'))
            aspect=tk.StringVar(value=stored.get('aspect','16:9'))
            res=tk.StringVar(value=stored.get('resolution','720p'))
            kind=tk.StringVar(value=stored.get('video_format','mp4'))
            output_type=tk.StringVar(value=stored.get('output_type','video'))
            audio_fmt=tk.StringVar(value=stored.get('audio_format','mp3'))
            characters=self.use_character_voices_var
            gutenberg=tk.BooleanVar(value=GUTENBERG_ENABLED)
            skip=tk.BooleanVar(value=stored.get('skip_existing',False))
            for column in range(2):
                settings_row.columnconfigure(column, weight=1)
            for index,(title,var,values) in enumerate([('Export',mode,['both','book','chapters']),('Output',output_type,['video','audio']),('Aspect',aspect,list(ASPECTS)),('Video format',kind,['mp4','mkv','mov','webm']),('Audio format',audio_fmt,['wav','mp3','m4a','flac','ogg'])]):
                group=ttk.Frame(settings_row)
                group.grid(row=index//2,column=index%2,sticky='ew',padx=(0,8),pady=3)
                ttk.Label(group,text=title).pack(anchor='w')
                ttk.Combobox(group,textvariable=var,values=values,width=12,state='readonly').pack(fill='x')
            book_animation=tk.StringVar(value=stored.get('animation','none'))
            book_dimensions=tk.StringVar(value=stored.get('dimensions',''))
            book_font=tk.StringVar(value=stored.get('font_path',''))
            block=ttk.Frame(panel);block.pack(fill='x',pady=(7,0))
            ttk.Label(block,text='Animated text style').grid(row=0,column=0,sticky='w')
            ttk.Combobox(block,textvariable=book_animation,values=list(MODES),state='readonly',width=19).grid(row=1,column=0,padx=(0,8),sticky='ew')
            ttk.Label(block,text='Custom W:H aspect / custom dimensions').grid(row=0,column=1,sticky='w')
            ttk.Entry(block,textvariable=book_dimensions,width=22).grid(row=1,column=1,padx=(0,8),sticky='ew')
            block.columnconfigure(0,weight=1);block.columnconfigure(1,weight=1)
            row=ttk.Frame(panel);row.pack(fill='x',pady=(4,0))
            ttk.Label(row,text='Font for multilingual text (optional):').pack(side='left')
            ttk.Entry(row,textvariable=book_font).pack(side='left',fill='x',expand=True,padx=5)
            ttk.Button(row,text='Browse',command=lambda:book_font.set(filedialog.askopenfilename(parent=window,filetypes=[('Font','*.ttf *.otf *.ttc')]) or book_font.get())).pack(side='left')
            if GUTENBERG_ENABLED:
                ttk.Checkbutton(settings_row,text='Gutenberg Mode',variable=gutenberg).grid(row=3,column=0,sticky='w')
            ttk.Checkbutton(settings_row,text='Skip existing files',variable=skip).grid(row=3,column=1,sticky='w')

            ttk.Checkbutton(panel,text='Use my Character Voice Studio profiles (tag narrator/characters inside each chapter)',variable=characters).pack(anchor='w',pady=4)
            ttk.Button(panel,text='Edit character profiles',command=self.character_voice_studio).pack(anchor='w',pady=4)
            def remember_book_settings(*_args):
                self.book_export_settings={'mode':mode.get(),'aspect':aspect.get(),'resolution':res.get(),'video_format':kind.get(),
                    'output_type':output_type.get(),'audio_format':audio_fmt.get(),'skip_existing':skip.get(),
                    'animation':book_animation.get(),'dimensions':book_dimensions.get().strip(),'font_path':book_font.get().strip()}
            for v in (mode,aspect,res,kind,output_type,audio_fmt,skip,book_animation,book_dimensions,book_font):
                v.trace_add('write',remember_book_settings)
            remember_book_settings()

            def start():
                if getattr(self, '_chapter_spelling', []):
                    messagebox.showinfo('Chapter review','Save or close the chapter review editor before exporting books.',parent=window)
                    return
                if not books:
                    messagebox.showwarning('Combine Chapters','Add books or chapters first.',parent=window)
                    return
                missing=[f'{b.title}: {c.title}' for b in books for c in b.chapters if not c.images] if output_type.get()=='video' and book_animation.get()=='none' else []
                if missing:
                    messagebox.showerror('Missing chapter covers','Assign images to these chapters before exporting:\n'+'\n'.join(missing[:12]),parent=window)
                    return
                dest=filedialog.askdirectory(parent=window,title='Choose audiobook output folder')
                if not dest:
                    return
                try:
                    engine_name,speech_settings,speech_opts=self._params()
                    need_voice=any(not ch.audio for book in books for ch in book.chapters)
                    engine=get_engine(engine_name,speech_settings.model,speech_settings.voice) if need_voice else None
                except Exception as exc:
                    messagebox.showerror('Voice setup',str(exc),parent=window)
                    return
                opts=BookExportOptions(mode=mode.get(),video=VideoOptions(aspect=aspect.get(),resolution=res.get(),animation=book_animation.get(),dimensions=book_dimensions.get().strip(),font_path=book_font.get().strip()),gutenberg=gutenberg.get(),skip_existing=skip.get(),video_format=kind.get(),audio_format=audio_fmt.get(),output_type=output_type.get())
                voice_project=self._effective_project() if characters.get() else None
                if need_voice and not self._confirm_piper_downloads(
                        engine_name, speech_settings, voice_project, '', parent=window):
                    return
                all_books=list(books)
                self.active=True
                self.control=RunControl()
                self._set_buttons()
                window.destroy()
                self._start_progress(f'Preparing {len(all_books)} book(s)…')
                def task():
                    try:
                        result=export_books(all_books,dest,engine=engine,settings=speech_settings,speech_options=speech_opts,options=opts,voice_project=voice_project,auto_tag=True,control=self.control,status=lambda event:self.events.put(('job_progress',event)))
                        failures=result['failures']
                        if failures:
                            self.events.put(('error', f'Completed with {len(failures)} failures. See openvoice-batch-report.json in {dest}.\n'+str(failures[:3])))
                        else:
                            self.events.put(('done',f'Audiobook Creator: {len(result["books"])} books and {len(result["outputs"])} files exported to {dest}'))
                    except Exception as exc:
                        self.events.put(('error',str(exc)))
                    finally:
                        self.events.put(('idle',))
                threading.Thread(target=task,daemon=True).start()

            ttk.Button(panel,text='▶  One-click export all books',command=start,style='Accent.TButton').pack(anchor='e',pady=(8,0))
            poll_imports()

        def _start_progress(self, label):
            self.progress['value'] = 0
            self.progress_percent_var.set('0%')
            self.stage_progress.stop()
            self.stage_progress.configure(mode='indeterminate')
            self.stage_progress.start(30)
            self.stage_percent_var.set('Working')
            self.status_var.set(label)

        def _show_progress(self, event):
            percent = int(event.fraction * 100)
            self.progress['value'] = percent
            self.progress_percent_var.set(f'{percent}%')
            if event.stage_fraction is None:
                if str(self.stage_progress.cget('mode')) != 'indeterminate':
                    self.stage_progress.configure(mode='indeterminate')
                    self.stage_progress.start(30)
                self.stage_percent_var.set('Working')
            else:
                self.stage_progress.stop()
                self.stage_progress.configure(mode='determinate', value=event.stage_fraction * 100)
                self.stage_percent_var.set(f'{int(event.stage_fraction*100)}%')
            if self.control and self.control.stopped.is_set():
                self.status_var.set('Stopping…')
            elif self.control and not self.control.resumed.is_set():
                self.status_var.set('Paused · ' + event.label)
            else:
                self.status_var.set(event.label)

        def _set_buttons(self):
            state = 'disabled' if self.active else 'normal'
            for btn in (self.speak_btn, self.export_btn, self.batch_btn, self.video_btn):
                btn.configure(state=state)
            for btn in (self.pause_btn, self.stop_btn):
                btn.configure(state='normal' if self.active else 'disabled')

        def speak(self):
            self._launch('speak')

        def export(self):
            path = filedialog.asksaveasfilename(defaultextension='.wav', initialfile='speech.wav', filetypes=[('WAV', '*.wav'), ('MP3 (FFmpeg)', '*.mp3'), ('FLAC (FFmpeg)', '*.flac'), ('OGG (FFmpeg)', '*.ogg'), ('M4A (FFmpeg)', '*.m4a'), ('Opus (FFmpeg)', '*.opus'), ('AAC (FFmpeg)', '*.aac'), ('AIFF (FFmpeg)', '*.aiff')])
            if path:
                self._launch('export', output=path)

        def batch(self):
            from .gui_forms import FormEditor
            files=filedialog.askopenfilenames(parent=self.root,title='Select documents to convert')
            if not files:return
            output=filedialog.askdirectory(parent=self.root,title='Choose output folder')
            if not output:return
            return FormEditor(self.root,'Batch audiobook export',{'audio_format':self.book_export_settings.get('audio_format','wav')},
                lambda d:self._launch('batch',output=output,files=files,audio_format=d['audio_format']),apply_label='Start batch')

        def pause(self):
            if self.control:
                if self.control.resumed.is_set():
                    self.control.pause()
                    self.pause_var.set('Resume')
                    self.status_var.set('Pausing after the current text chunk…')
                else:
                    self.control.resume()
                    self.pause_var.set('Pause between sentences')
                    self.status_var.set('Resuming…')

        def stop(self):
            if self.control:
                self.control.stop()
                self.status_var.set('Stopping…')

        def poll(self):
            try:
                while True:
                    event = self.events.get_nowait()
                    kind = event[0]
                    if kind == 'progress':
                        self.progress['value'] = round(event[1] / event[2] * 100) if event[2] else 0
                        self.progress_percent_var.set(f'{int(self.progress["value"])}%')
                        self.status_var.set(f'Processed {event[1]} of {event[2]} chunks/files')
                    elif kind == 'job_progress':
                        self._show_progress(event[1])
                    elif kind == 'done':
                        self.progress['value'] = 100
                        self.progress_percent_var.set('100%')
                        self.stage_progress.stop()
                        self.stage_progress.configure(mode='determinate', value=100)
                        self.stage_percent_var.set('100%')
                        self.status_var.set(event[1])
                    elif kind == 'error':
                        self.stage_progress.stop()
                        self.stage_percent_var.set('Stopped' if self.control and self.control.stopped.is_set() else 'Error')
                        self.status_var.set(f'Error: {event[1][:140]}')
                        messagebox.showerror(APP_NAME, event[1])
                    elif kind == 'idle':
                        self.stage_progress.stop()
                        self.active = False
                        self.control = None
                        self._set_buttons()
                    elif kind == 'ui':
                        event[1]()
                    elif kind == 'voices':
                        _engine_key, names = (event[1], event[2])
                        if len(event) >= 5 and (event[3] != self.engine_var.get() or event[4] != self._voice_refresh_serial):
                            continue
                        if self.engine_var.get() == 'auto':
                            names = sorted(set(names) | set(self._piper_voice_names()), key=str.casefold)
                        names = self._filter_downloaded_voices(self.engine_var.get(), names,
                                                               self.model_var.get().strip())
                        self.voice_combo.configure(values=[''] + names)
                        # Do not delete a chosen catalog voice if the index is
                        # temporarily unavailable or being refreshed.
                        self.status_var.set(f'{_engine_key}: {len(names)} available voices' if names else f'{_engine_key}: select or install a voice/model')
                    elif kind == 'piper_installed':
                        self.model_var.set('')
                        self.engine_var.set('piper')
                        self.voice_var.set(event[1])
                        self.status_var.set(f'Piper voice installed: {event[1]}')
                        self.refresh_voices()
                    elif kind == 'error_voices':
                        self.status_var.set(f'Unable to list voices: {event[1]}')
            except queue.Empty:
                pass
            self.root.after(100, self.poll)

        def close(self):
            if not self._confirm_replace_manuscript():
                return
            self.stop_autosave()
            if self._ocr_cancel:
                self._ocr_cancel.set()
            self.spelling.close()
            for controller in getattr(self, '_chapter_spelling', []):
                controller.close()
            if self.control:
                self.control.stop()
            if getattr(self,'studio',None):
                if self.studio.playing:self.studio.playing.stop()
                for server in self.studio.servers:
                    server.shutdown();server.server_close()
            for scheduled in self.root.tk.call('after','info'):
                try:self.root.after_cancel(scheduled)
                except tk.TclError:pass
            self.root.destroy()
            if self._project_workspace is not None:
                self._project_workspace.cleanup()
    try:
        from .windowing import prepare_desktop_dpi
        prepare_desktop_dpi()
        try:
            from tkinterdnd2 import TkinterDnD
            root=TkinterDnD.Tk()
        except (ImportError,RuntimeError,tk.TclError):
            root = tk.Tk()
    except tk.TclError as exc:
        print(f'Cannot open GUI (is a desktop display available?): {exc}')
        return 1
    app = App(root)
    app._set_buttons()
    if on_ready is not None:
        root.after_idle(lambda:on_ready(app))
    root.mainloop()
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
