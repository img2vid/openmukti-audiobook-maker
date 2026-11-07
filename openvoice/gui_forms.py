"""Typed desktop forms and readable reports. Serialization stays behind the UI.

The editors work on copies and only commit through their Apply callback. Unknown
fields survive round trips, including fields added by a newer application.
"""
from __future__ import annotations

import copy
import csv
import math
import re
import tkinter as tk
from dataclasses import dataclass, field, replace
from pathlib import Path
from tkinter import colorchooser, filedialog, font, ttk

from .windowing import fit_window, scrollable_area


@dataclass(frozen=True)
class Field:
    label: str = ''
    kind: str = ''
    choices: dict = field(default_factory=dict)
    minimum: float | None = None
    maximum: float | None = None
    hint: str = ''
    required: bool = False
    extension: str = ''
    allow_custom: bool = False


LABELS = {
    'gpu_mode': 'Graphics acceleration', 'font': 'Editor typeface',
    'font_size': 'Editor text size', 'interface_scale': 'Interface size (%)',
    'high_contrast': 'Use high contrast colors', 'touch': 'Larger touch controls',
    'left_handed': 'Put voice settings on the left', 'reduced_motion': 'Reduce animation',
    'translate_missing': 'Translate additional interface text locally',
    'translation_file': 'Additional translation file', 'toolbar': 'Quick access buttons',
    'shortcuts': 'Keyboard shortcuts', 'permissions': 'Access preferences',
    'external_tools': 'Allow external audio and document tools',
    'native_plugins': 'Allow native extensions', 'network': 'Allow internet access',
    'microphone': 'Allow microphone access', 'folders': 'Allowed working folders',
    'import_preset': 'Document import preferences', 'render_cache': 'Reusable audio folder',
    'model_lock': 'Voice verification file', 'caption_preset': 'Caption colors',
    'safe_margin': 'Safe margin (fraction of the image)', 'seconds': 'Seconds per panel',
    'box': 'Position on canvas', 'crop': 'Crop area', 'size': 'Text size / image size',
    'start': 'Start time (seconds)', 'end': 'End time (seconds)',
    'fade_in': 'Fade in (seconds)', 'fade_out': 'Fade out (seconds)',
    'offset': 'Skip source audio (seconds)', 'duration': 'Duration (seconds)',
    'gain': 'Volume multiplier', 'gain_db': 'Volume change (dB)',
    'target_lufs': 'Target loudness (LUFS)', 'pan': 'Stereo position',
    'space': 'Acoustic space', 'curve': 'Volume automation points',
    'impulse': 'Room response recording', 'duck_music': 'Lower music during narration',
    'loop': 'Repeat to fill duration', 'loop_crossfade': 'Loop seam fade (seconds)',
    'source_seconds': 'Source length (seconds)', 'muted': 'Mute this clip',
    'terms': 'Project vocabulary', 'protected': 'Protected words and phrases',
    'style': 'Preferred wording', 'learned': 'Learned corrections',
    'engines': 'Enabled editorial checks', 'speakers': 'Speaker attribution rules',
    'pace': 'Speaking speed multiplier', 'semitones': 'Pitch change (semitones)',
    'pause': 'Pause length (seconds)', 'speaker_id': 'Speaker number',
    'find': 'Word or phrase', 'replace': 'Say instead',
    'case_sensitive': 'Match capitalization', 'regex': 'Use pattern matching',
    'at': 'Start after (local date and time)', 'profile': 'Character voice',
    'test_text': 'Sample passage', 'file': 'Source file', 'safe': 'Keep inside safe area',
    'avoid_overlap': 'Avoid other text layers', 'source_url': 'Source web address',
}


def label_for(key):
    return LABELS.get(str(key), str(key).replace('_', ' ').strip().capitalize())


def choices(*values):
    return {v: str(v).replace('_', ' ').capitalize() for v in values}


CHOICES = {
    'gpu_mode': {'auto': 'Use available graphics hardware', 'cpu': 'Use processor only'},
    'language': {'auto': 'Detect automatically', 'en': 'English', 'bn': 'Bengali', 'es': 'Spanish'},
    'caption_preset': {'custom': 'Custom', 'white on black': 'White on black',
                       'yellow on black': 'Yellow on black', 'black on white': 'Black on white'},
    'footnotes': {'inline': 'Read with the text', 'skip': 'Skip footnotes', 'end': 'Read at the end'},
    'tables': {'plain': 'Read cell contents', 'describe': 'Describe table rows'},
    'role': choices('narration', 'music', 'effects', 'ambience'),
    'space': choices('dry', 'small room', 'hall', 'telephone', 'underwater'),
    'easing': choices('linear', 'ease-in', 'ease-out', 'smooth'),
    'ease': choices('linear', 'ease-in', 'ease-out', 'smooth'),
    'emotion': choices('neutral', 'calm', 'excited', 'sad', 'angry', 'whisper'),
    'engine': choices('auto', 'piper', 'kokoro', 'kitten', 'pocket', 'coqui', 'espeak', 'sapi', 'macos', 'flite'),
    'audio_format': {v: v.upper() for v in ('wav', 'mp3', 'm4a', 'flac', 'ogg', 'opus')},
    'cpu_profile': {'low': 'Quiet / low power', 'balanced': 'Balanced', 'fast': 'Fast rendering'},
    'fit': choices('cover', 'contain'), 'align': choices('left', 'center', 'right'),
}

RANGES = {
    'font_size': (7, 48), 'interface_scale': (50, 300), 'safe_margin': (0, .35),
    'gain': (0, 8), 'pan': (-1, 1), 'target_lufs': (-40, -6), 'pace': (.35, 3),
    'semitones': (-18, 18), 'gain_db': (-90, 18), 'opacity': (0, 1),
    'start': (0, 2592000), 'end': (0, 2592000), 'offset': (0, 2592000),
    'duration': (.0001, 2592000), 'fade_in': (0, 86400), 'fade_out': (0, 86400),
    'pause': (0, 86400), 'seconds': (.01, 86400), 'speaker_id': (0, 100000),
    'priority': (-100, 100), 'rate': (-10, 10), 'pitch': (-10, 10), 'volume': (0, 100),
    'loop_crossfade': (0, 86400), 'sample_rate': (8000, 192000),
    'time': (0, 2592000), 'zoom': (1, 4),
}

HINTS = {
    'gain': '1 = original volume; 0.5 = half; 2 = double.',
    'pan': '-1 = left, 0 = center, 1 = right.',
    'pace': '1 = normal speed; 0.8 = slower; 1.2 = faster.',
    'folders': 'Leave empty to allow all folders. Add folders with Browse.',
    'box': 'Coordinates run from 0 to 1: left, top, right, bottom.',
    'crop': 'Coordinates run from 0 to 1: left, top, right, bottom.',
    'curve': 'Each point contains a time in seconds and a volume multiplier. Times must increase.',
    'shortcuts': 'Record a key combination, then choose its action.',
    'terms': 'One word or phrase per item. These are protected from automatic corrections.',
    'at': 'Leave empty to run immediately. Example: 2026-11-05 18:30.',
    'font': 'Choose an installed typeface or enter its name.',
    'language': 'You may also enter a language code such as hi, ta, fr, or ja.',
}


def field_for(key, value, context=''):
    kind = ('boolean' if isinstance(value, bool) else 'integer' if isinstance(value, int)
            else 'number' if isinstance(value, float) else 'collection' if isinstance(value, (dict, list))
            else 'text' if key in ('text', 'test_text', 'notes', 'description') or isinstance(value, str) and '\n' in value
            else 'entry')
    if key in ('color', 'background', 'outline') and isinstance(value, str):
        kind = 'color'
    if key in ('file', 'image', 'model', 'translation_file', 'model_lock', 'impulse', 'font_file', 'manuscript', 'template_file'):
        kind = 'file'
    if key in ('render_cache', 'output_folder', 'cache_dir'):
        kind = 'folder'
    if key == 'output':
        kind = 'savefile'
    if key in ('gain', 'pan', 'pace', 'semitones', 'gain_db', 'target_lufs', 'safe_margin', 'start', 'end', 'offset', 'duration', 'fade_in', 'fade_out', 'opacity', 'pause', 'seconds', 'loop_crossfade', 'time', 'zoom'):
        kind = 'number'
    bounds = RANGES.get(key, (None, None))
    options = CHOICES.get(key, {}) if not isinstance(value, (dict, list, bool)) else {}
    if key == 'font':
        kind = 'file' if context == 'layer' else 'font'
    if key == 'focus' and (value == 'auto' or isinstance(value, list)):
        kind = 'focus'
    if key in ('box', 'crop', 'size', 'pause_range') and isinstance(value, list) and all(isinstance(v, (float, int)) for v in value):
        kind = 'vector'
    if value is None and key == 'speaker_id':
        kind = 'optional_integer'
    label = label_for(key)
    hint = HINTS.get(key, '')
    if context == 'layer':
        if key == 'type':
            options = choices('rectangle', 'image', 'text', 'correction', 'notebook', 'waveform', 'progress')
        if key == 'font':
            label = 'Optional font file'
        if key == 'pan':
            label, hint = 'Horizontal camera movement', '-1 = left, 0 = still, 1 = right.'
        if key == 'size' and not isinstance(value, list):
            label, bounds = 'Text size (fraction of canvas)', (.005, 1)
    return Field(label, kind, options, *bounds, hint, allow_custom=key=='language')


def coerce(raw, spec, original=''):
    """Validate a single form value without evaluating code or expressions."""
    if spec.kind == 'boolean':
        return bool(raw)
    if spec.kind in ('number', 'integer', 'optional_integer'):
        if spec.kind == 'optional_integer' and not str(raw).strip():
            return None
        try:
            n = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f'{spec.label}: enter a number.') from None
        if not math.isfinite(n):
            raise ValueError(f'{spec.label}: enter a finite number.')
        if spec.kind in ('integer', 'optional_integer') and not n.is_integer():
            raise ValueError(f'{spec.label}: enter a whole number.')
        if spec.minimum is not None and n < spec.minimum or spec.maximum is not None and n > spec.maximum:
            raise ValueError(f'{spec.label}: choose a value from {spec.minimum:g} to {spec.maximum:g}.')
        return int(n) if spec.kind in ('integer', 'optional_integer') else n
    value = str(raw)
    if spec.required and not value.strip():
        raise ValueError(f'{spec.label}: this field is required.')
    if spec.kind == 'color' and value:
        from PIL import ImageColor
        try:
            ImageColor.getrgb(value)
        except ValueError:
            raise ValueError(f'{spec.label}: choose a valid color.') from None
    return value


def validate_record(data):
    """Cross-field validation shared by visual editors and their unit tests."""
    for key in ('box', 'crop'):
        if key in data:
            v = data[key]
            if not isinstance(v, list) or len(v) != 4 or any(not isinstance(n, (float, int)) or not math.isfinite(n) or not 0 <= n <= 1 for n in v) or v[0] >= v[2] or v[1] >= v[3]:
                raise ValueError(f'{label_for(key)}: left must be before right and top before bottom, between 0 and 1.')
    if 'start' in data and 'end' in data and float(data['end']) <= float(data['start']):
        raise ValueError('End time must be later than start time.')
    if data.get('loop') and not data.get('duration'):
        raise ValueError('Set a duration for a repeating clip.')
    if 'duration' in data:
        for name in ('fade_in', 'fade_out'):
            if float(data.get(name, 0)) > float(data['duration']):
                raise ValueError(f'{label_for(name)} must not exceed clip duration.')
    if data.get('curve'):
        from .sound_studio import envelope
        envelope(data['curve'], data.get('duration', data.get('source_seconds', 2592000)))
    if 'pause_range' in data and (len(data['pause_range']) != 2 or not 0 <= data['pause_range'][0] <= data['pause_range'][1] <= 15):
        raise ValueError('Pause range must increase and stay between 0 and 15 seconds.')
    return data


def summary(value):
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if value is None:
        return 'Automatic'
    if isinstance(value, dict):
        if not value:
            return 'No entries'
        return ' · '.join(f'{label_for(k)}: {summary(v)}' for k, v in list(value.items())[:4])
    if isinstance(value, list):
        return f'{len(value)} item' + ('' if len(value) == 1 else 's')
    return str(value).replace('\n', '  ') or '—'


MAPPINGS = {'style', 'learned', 'speakers', 'shortcuts', 'sounds', 'profiles', 'cast_by_language', 'languagetool'}
TEMPLATES = {
    'markers': {'time': 0.0, 'label': 'Marker'},
    'curve': [0.0, 1.0], 'panels': [0.0, 0.0, 1.0, 1.0],
    'tracks': {'file': '', 'role': 'narration', 'start': 0.0, 'gain': 1.0},
    'profiles': {'engine': 'auto', 'voice': '', 'model': '', 'language': 'auto', 'speaker_id': None,'rate':0,'pitch':0,'volume':100},
    'passages': {'text': '', 'profile': 'Narrator', 'emotion': 'neutral', 'pace': 1.0, 'semitones': 0.0, 'gain_db': 0.0},
    'rules': {'find': '', 'replace': '', 'case_sensitive': False, 'regex': False},
}


class ValueControl:
    def __init__(self, parent, key, value, *, context='', spec=None, on_change=None):
        self.frame = ttk.Frame(parent)
        self.key, self.original, self.context = key, copy.deepcopy(value), context
        self.spec = spec or field_for(key, value, context)
        self.value = copy.deepcopy(value)
        self.variable = None
        self.on_change = on_change or (lambda: None)
        kind = self.spec.kind
        if kind == 'focus':
            self.automatic = tk.BooleanVar(self.frame, value=value == 'auto')
            ttk.Checkbutton(self.frame, text='Find the focal point automatically', variable=self.automatic).pack(anchor='w')
            self.parts = []
            for label, n in zip(('Horizontal', 'Vertical'), [.5, .5] if value == 'auto' else value):
                part = ttk.Frame(self.frame)
                part.pack(side='left', fill='x', expand=True)
                ttk.Label(part, text=label).pack(side='left')
                var = tk.StringVar(part, value=n)
                self.widget = ttk.Spinbox(part, from_=0, to=1, increment=.05, textvariable=var, width=7)
                self.widget.pack(side='left', padx=4)
                self.parts.append((var, n))
        elif kind in ('collection', 'vector'):
            if kind == 'vector':
                self.parts = []
                names = ('Left', 'Top', 'Right', 'Bottom') if key in ('box', 'crop') else ('Width', 'Height') if key == 'size' else ('Minimum', 'Maximum')
                for i, n in enumerate(value):
                    f = ttk.Frame(self.frame)
                    f.pack(side='left', fill='x', expand=True, padx=(0, 5))
                    ttk.Label(f, text=names[i] if i < len(names) else str(i + 1)).pack(anchor='w')
                    var = tk.StringVar(f, value=str(n))
                    widget = ttk.Spinbox(f, textvariable=var, from_=0, to=10000 if key == 'size' else 15 if key == 'pause_range' else 1, increment=1 if key == 'size' else .01, width=7)
                    widget.pack(fill='x')
                    self.parts.append((var, n))
                self.widget = widget if value else self.frame
            else:
                self.variable = tk.StringVar(self.frame, value=summary(value))
                ttk.Label(self.frame, textvariable=self.variable, wraplength=300).pack(side='left', fill='x', expand=True)
                self.widget = ttk.Button(self.frame, text='Edit…', command=self.edit_collection)
                self.widget.pack(side='right')
        elif kind == 'text':
            self.widget = tk.Text(self.frame, height=4, width=30, wrap='word', undo=True)
            theme_text(self.widget)
            self.widget.insert('1.0', '' if value is None else str(value))
            scroll = ttk.Scrollbar(self.frame, command=self.widget.yview)
            self.widget.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
            self.widget.pack(side='left', fill='both', expand=True)
        elif kind == 'boolean':
            self.variable = tk.BooleanVar(self.frame, value=value)
            self.widget = ttk.Checkbutton(self.frame, variable=self.variable, text='Enabled')
            self.widget.pack(anchor='w')
        else:
            self.variable = tk.StringVar(self.frame, value='' if value is None else str(value))
            if self.spec.choices:
                self.options = dict(self.spec.choices)
                if value not in self.options:
                    self.options[value] = str(value)
                self.variable.set(self.options[value])
                self.widget = ttk.Combobox(self.frame, textvariable=self.variable, values=list(self.options.values()), state='normal' if self.spec.allow_custom else 'readonly')
            elif kind == 'font':
                self.widget = ttk.Combobox(self.frame, textvariable=self.variable, values=sorted(set(font.families(parent))))
            elif kind in ('number', 'integer', 'optional_integer'):
                self.widget = ttk.Spinbox(self.frame, textvariable=self.variable,
                    from_=self.spec.minimum if self.spec.minimum is not None else -1000000000,
                    to=self.spec.maximum if self.spec.maximum is not None else 1000000000,
                    increment=1 if kind != 'number' else .1, width=16)
            else:
                self.widget = ttk.Entry(self.frame, textvariable=self.variable)
            self.widget.pack(side='left', fill='x', expand=True)
            if kind in ('file', 'savefile', 'folder', 'color'):
                ttk.Button(self.frame, text='Choose color…' if kind == 'color' else 'Browse…', command=self.browse).pack(side='right', padx=(5, 0))
        if self.spec.hint:
            self.hint = self.spec.hint

    def browse(self):
        if self.spec.kind == 'color':
            value = colorchooser.askcolor(self.variable.get() or '#ffffff', parent=self.frame.winfo_toplevel())[1]
        elif self.spec.kind == 'folder':
            value = filedialog.askdirectory(parent=self.frame.winfo_toplevel())
        elif self.spec.kind == 'savefile':
            value = filedialog.asksaveasfilename(parent=self.frame.winfo_toplevel(), defaultextension=self.spec.extension or '.wav')
        else:
            value = filedialog.askopenfilename(parent=self.frame.winfo_toplevel())
        if value:
            self.variable.set(value)

    def edit_collection(self):
        def accept(value):
            self.value = copy.deepcopy(value)
            self.variable.set(summary(value))
            self.on_change()
        if isinstance(self.value, dict) and self.key not in MAPPINGS and self.value:
            FormEditor(self.frame.winfo_toplevel(), self.spec.label, self.value, accept, context=self.key)
        else:
            CollectionEditor(self.frame.winfo_toplevel(), self.spec.label, self.value, accept, context=self.key)

    def get(self):
        if self.spec.kind == 'focus':
            if self.automatic.get():
                return 'auto'
            return [coerce(v.get(), Field('Focal point', 'number', minimum=0, maximum=1)) for v, _ in self.parts]
        if self.spec.kind == 'collection':
            return copy.deepcopy(self.value)
        if self.spec.kind == 'vector':
            return [coerce(v.get(), Field(self.spec.label, 'integer' if self.key == 'size' else 'number'), n) for v, n in self.parts]
        if self.spec.kind == 'text':
            raw = self.widget.get('1.0', 'end-1c')
        else:
            raw = self.variable.get()
        if self.spec.choices:
            raw = next((k for k, v in self.options.items() if v == raw), raw)
            if self.key != 'language' and raw not in self.options:
                raise ValueError(f'{self.spec.label}: choose an item from the list.')
        if self.original is None and raw == '' and self.spec.kind != 'text':
            return None
        return coerce(raw, self.spec, self.original)


class FormEditor:
    def __init__(self, parent, title, data, save, *, context='', fields=None, groups=None, description='', apply_label='Apply changes', validator=None):
        self.original = copy.deepcopy(data)
        context = context or ('layer' if isinstance(data.get('type'), str) and 'box' in data else '')
        self.save, self.context, self.validator = save, context, validator
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        theme_window(self.win)
        self.win.form_editor = self
        self.win.transient(parent.winfo_toplevel())
        fit_window(self.win, 760, 640, 400, 320)
        heading=ttk.Label(self.win, text=title, font=ui_font(self.win,16,True), wraplength=650)
        heading.pack(anchor='w', padx=16, pady=(14, 4))
        detail=ttk.Label(self.win, text=description or 'Choose settings below. Changes take effect when you apply them.', wraplength=640)
        detail.pack(anchor='w', padx=16, pady=(0, 8))
        def resize(event):
            if event.widget is self.win:
                heading.configure(wraplength=max(240,event.width-32))
                detail.configure(wraplength=max(240,event.width-32))
        self.win.bind('<Configure>',resize,add='+')
        footer = ttk.Frame(self.win, padding=10)
        footer.pack(side='bottom', fill='x')
        self.error = tk.StringVar(self.win)
        ttk.Label(footer, textvariable=self.error, foreground='#ee8b80', wraplength=600).pack(fill='x')
        buttons = ttk.Frame(footer)
        buttons.pack(fill='x', pady=(4, 0))
        ttk.Button(buttons, text='Reset changes', command=self.reset).pack(side='left')
        ttk.Button(buttons, text='Cancel', command=self.win.destroy).pack(side='right')
        self.apply_button = ttk.Button(buttons, text=apply_label, command=self.apply, style='Accent.TButton')
        self.apply_button.pack(side='right', padx=6)
        self.body = ttk.Frame(self.win)
        self.body.pack(fill='both', expand=True)
        self.fields, self.groups = fields or {}, groups
        self.controls = {}
        self.build()
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.win.bind('<Control-Return>', lambda e: self.apply())

    def build(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.controls = {}
        groups = self.groups or {'Settings': list(self.original)}
        assigned = {key for keys in groups.values() for key in keys}
        extra = [k for k in self.original if k not in assigned]
        if extra:
            groups = {**groups, 'Other preferences': extra}
        self.notebook = ttk.Notebook(self.body) if len(groups) > 1 else None
        if self.notebook:
            selector=ttk.Frame(self.body,padding=(12,0,12,5))
            selector.pack(fill='x')
            ttk.Label(selector,text='Section').pack(side='left',padx=(0,6))
            self.section_var=tk.StringVar(selector,value=next(iter(groups)))
            section=ttk.Combobox(selector,textvariable=self.section_var,values=list(groups),state='readonly')
            section.pack(side='left',fill='x',expand=True)
            section.bind('<<ComboboxSelected>>',lambda e:self.notebook.select(section.current()))
            self.notebook.bind('<<NotebookTabChanged>>',lambda e:self.section_var.set(self.notebook.tab(self.notebook.select(),'text')) if self.notebook.select() else None)
            self.notebook.pack(fill='both', expand=True)
        for group, keys in groups.items():
            host = ttk.Frame(self.notebook or self.body)
            if self.notebook:
                self.notebook.add(host, text=group)
            else:
                host.pack(fill='both', expand=True)
            shell, panel, _ = scrollable_area(host)
            shell.pack(fill='both', expand=True)
            panel.columnconfigure(0, weight=1)
            for key in keys:
                if key not in self.original:
                    continue
                row = ttk.Frame(panel, padding=(4, 7))
                row.pack(fill='x')
                spec = self.fields.get(key) or field_for(key, self.original[key], self.context)
                label=ttk.Label(row, text=spec.label or label_for(key),wraplength=590)
                label.pack(anchor='w', pady=(0, 3))
                control = ValueControl(row, key, self.original[key], context=self.context, spec=spec)
                control.frame.pack(fill='x')
                if spec.hint:
                    hint=ttk.Label(row, text=spec.hint, wraplength=590, style='Muted.TLabel')
                    hint.pack(anchor='w', pady=(3, 0))
                else:
                    hint=None
                def wrap(event,label=label,hint=hint):
                    label.configure(wraplength=max(180,event.width-10))
                    if hint is not None:hint.configure(wraplength=max(180,event.width-10))
                row.bind('<Configure>',wrap)
                self.controls[key] = control

    def reset(self):
        self.build()
        self.error.set('Changes in this window were reset.')

    def collect(self):
        result = copy.deepcopy(self.original)
        for key, control in self.controls.items():
            try:
                result[key] = control.get()
            except ValueError:
                if self.notebook:
                    for tab in self.notebook.tabs():
                        if str(control.frame).startswith(tab + '.'):
                            self.notebook.select(tab)
                control.widget.focus_set()
                raise
        validate_record(result)
        if self.validator:
            self.validator(result)
        return result

    def apply(self):
        try:
            value = self.collect()
            self.save(value)
        except Exception as exc:
            self.error.set(str(exc))
            return False
        if self.win.winfo_exists():
            self.win.destroy()
        return True


class CollectionEditor:
    """Ordered list/table editor and named mapping editor with atomic Apply."""
    def __init__(self, parent, title, data, save, *, context='', template=None, item_fields=None):
        self.data = copy.deepcopy(data)
        self.original = copy.deepcopy(data)
        self.save, self.context = save, context
        self.mapping = isinstance(data, dict)
        self.template = copy.deepcopy(template if template is not None else TEMPLATES.get(context, self._infer_template()))
        self.item_fields = item_fields or {}
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        theme_window(self.win)
        self.win.collection_editor = self
        self.win.transient(parent.winfo_toplevel())
        fit_window(self.win, 800, 560, 400, 310)
        ttk.Label(self.win, text=title, font=ui_font(self.win,15,True)).pack(anchor='w', padx=12, pady=10)
        self.search = tk.StringVar(self.win)
        bar = ttk.Frame(self.win, padding=(10, 0))
        bar.pack(fill='x')
        ttk.Label(bar, text='Search').pack(side='left', padx=(0, 6))
        ttk.Entry(bar, textvariable=self.search).pack(side='left', fill='x', expand=True)
        middle = ttk.Frame(self.win, padding=10)
        middle.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(middle, columns=('value',), show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='Name' if self.mapping else 'Order')
        self.tree.heading('value', text='Details')
        self.tree.column('#0', width=150, stretch=False)
        self.tree.column('value', width=460)
        y = ttk.Scrollbar(middle, command=self.tree.yview)
        self.tree.configure(yscrollcommand=y.set)
        y.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.error = tk.StringVar(self.win)
        ttk.Label(self.win, textvariable=self.error, foreground='#ee8b80', wraplength=650).pack(fill='x', padx=12)
        from .studio_windows import line, button
        tools = line(self.win)
        for label, action in [('Add', self.add), ('Edit', self.edit), ('Duplicate', self.duplicate), ('Remove', self.remove), ('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1))]:
            b = button(tools, label, action)
            if self.mapping and label.startswith('Move'):
                b.state(['disabled'])
        foot = line(self.win)
        button(foot, 'Apply changes', self.apply)
        button(foot, 'Cancel', self.win.destroy)
        self.tree.bind('<Double-Button-1>', lambda e: self.edit())
        self.tree.bind('<Return>', lambda e: self.edit())
        self.tree.bind('<Delete>', lambda e: self.remove())
        self.search.trace_add('write', lambda *_: self.refresh())
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        self.refresh()

    def _infer_template(self):
        values = list(self.data.values()) if self.mapping else self.data
        return copy.deepcopy(values[0]) if values else ''

    def refresh(self, select=None):
        self.tree.delete(*self.tree.get_children())
        self.keys = list(self.data) if self.mapping else list(range(len(self.data)))
        query = self.search.get().casefold()
        for i, key in enumerate(self.keys):
            value = self.data[key]
            title = str(key) if self.mapping else str(i + 1)
            details = summary(value)
            if query in (title + ' ' + details).casefold():
                self.tree.insert('', 'end', iid=str(i), text=title, values=(details,))
        if select is not None and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))

    def selected(self):
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _editor(self, value, accept, *, mapping_key=None, is_new=False):
        context = self.context
        if self.mapping:
            key_spec = Field('Keyboard shortcut' if context == 'shortcuts' else 'Name / phrase', required=True)
            values = {'name': mapping_key or '', 'value': copy.deepcopy(value)}
            specs = {'name': key_spec}
            if context == 'shortcuts':
                from .studio_desk import COMMANDS
                specs['value'] = Field('Action', choices=choices(*COMMANDS))
            elif context == 'sounds':
                specs['value'] = Field('Local recording', 'file', required=True)
            elif context == 'speakers':
                specs['value'] = Field('Character name')
            elif context in ('style', 'learned'):
                specs['name'] = Field('Original wording', required=True)
                specs['value'] = Field('Preferred wording')
            def save(row):
                name = row['name'].strip()
                if name != mapping_key and name in self.data:
                    raise ValueError('An entry with that name already exists.')
                if context == 'shortcuts' and not re.fullmatch(r'<[A-Za-z0-9_-]{1,50}>', name):
                    raise ValueError('Record a keyboard shortcut first.')
                if context == 'shortcuts':
                    try:
                        self.win.bind(name, lambda e: None)
                        self.win.unbind(name)
                    except tk.TclError:
                        raise ValueError('Choose a valid key combination.') from None
                accept(name, row['value'])
            form = FormEditor(self.win, 'Add entry' if is_new else 'Edit entry', values, save, fields=specs)
            if context == 'shortcuts':
                entry = form.controls['name'].widget
                form.controls['name'].spec = Field('Keyboard shortcut')
                def record(e):
                    if e.keysym in ('Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R', 'Meta_L', 'Meta_R'):
                        return 'break'
                    modifiers = ('Control-' if e.state & 4 else '') + ('Alt-' if e.state & 8 else '') + ('Shift-' if e.state & 1 else '')
                    form.controls['name'].variable.set('<' + modifiers + e.keysym + '>')
                    return 'break'
                entry.bind('<KeyPress>', record)
        elif isinstance(value, dict):
            FormEditor(self.win, 'Add item' if is_new else 'Edit item', value, lambda d: accept(d), context=context, fields=self.item_fields)
        elif isinstance(value, list):
            names = ['Left', 'Top', 'Right', 'Bottom'] if context == 'panels' else ['Time (seconds)', 'Volume multiplier'] if context == 'curve' else [f'Value {i + 1}' for i in range(len(value))]
            FormEditor(self.win, 'Edit point' if context == 'curve' else 'Edit area', {str(i): n for i, n in enumerate(value)},
                lambda d: accept([d[str(i)] for i in range(len(value))]), fields={str(i): Field(names[i], 'number') for i in range(len(value))},
                validator=(lambda d: validate_record({'box': [d[str(i)] for i in range(4)]})) if context == 'panels' else None)
        else:
            spec = field_for('value', value)
            if context in ('folders', 'toolbar', 'engines'):
                if context == 'folders':
                    spec = Field('Working folder', 'folder', required=True)
                else:
                    from .studio_desk import COMMANDS
                    options = COMMANDS if context == 'toolbar' else ('context', 'duplicates', 'agreement')
                    spec = Field('Action' if context == 'toolbar' else 'Editorial check', choices=choices(*options))
            FormEditor(self.win, 'Add item' if is_new else 'Edit item', {'value': value}, lambda d: accept(d['value']), fields={'value': spec})

    def add(self):
        def accept(*args):
            if self.mapping:
                self.data[args[0]] = args[1]
            else:
                self.data.append(args[0])
            self.refresh(len(self.data) - 1)
        self._editor(copy.deepcopy(self.template), accept, is_new=True)

    def edit(self):
        i = self.selected()
        if i is None:
            self.error.set('Select an item to edit.')
            return
        key = self.keys[i]
        def accept(*args):
            if self.mapping:
                items = [(args[0], args[1]) if k == key else (k, v) for k, v in self.data.items()]
                self.data = dict(items)
            else:
                self.data[key] = args[0]
            self.refresh(i)
        self._editor(copy.deepcopy(self.data[key]), accept, mapping_key=key if self.mapping else None)

    def duplicate(self):
        i = self.selected()
        if i is None:
            return
        key = self.keys[i]
        if self.mapping:
            base = str(key) + ' copy'
            name, n = base, 2
            while name in self.data:
                name, n = f'{base} {n}', n + 1
            self.data[name] = copy.deepcopy(self.data[key])
            self.refresh(len(self.data) - 1)
        else:
            self.data.insert(key + 1, copy.deepcopy(self.data[key]))
            self.refresh(key + 1)

    def remove(self):
        i = self.selected()
        if i is not None:
            key = self.keys[i]
            if self.mapping:
                del self.data[key]
            else:
                self.data.pop(key)
            self.refresh(max(0, i - 1))

    def move(self, direction):
        i = self.selected()
        if self.mapping or i is None:
            return
        j = i + direction
        if 0 <= j < len(self.data):
            self.data.insert(j, self.data.pop(i))
            self.refresh(j)

    def apply(self):
        try:
            if self.context == 'curve' and self.data:
                from .sound_studio import envelope
                envelope(self.data, 2592000)
            self.save(copy.deepcopy(self.data))
        except Exception as exc:
            self.error.set(str(exc))
            return False
        self.win.destroy()
        return True


def edit_settings(parent, title, data, save, **kwargs):
    return FormEditor(parent, title, data, save, **kwargs).win


def readable_lines(value, path=()):
    if isinstance(value, dict):
        if not value:
            yield ' / '.join(path), 'No entries'
        for k, v in value.items():
            yield from readable_lines(v, (*path, label_for(k)))
    elif isinstance(value, (list, tuple)):
        if not value:
            yield ' / '.join(path), 'No entries'
        for i, v in enumerate(value, 1):
            yield from readable_lines(v, (*path, str(i)))
    else:
        yield ' / '.join(path), summary(value)


def report_text(value):
    return '\n'.join(f'{name}: {detail}' if name else detail for name, detail in readable_lines(value)) + '\n'


def show_report(parent, title, value):
    """Searchable hierarchical reports, with plain text and spreadsheet export."""
    win = tk.Toplevel(parent)
    win.title(title)
    theme_window(win)
    fit_window(win, 900, 620, 400, 330)
    ttk.Label(win, text=title, font=ui_font(win,16,True)).pack(anchor='w', padx=14, pady=12)
    query = tk.StringVar(win)
    row = ttk.Frame(win, padding=(12, 0))
    row.pack(fill='x')
    ttk.Label(row, text='Filter results').pack(side='left', padx=(0, 8))
    ttk.Entry(row, textvariable=query).pack(fill='x', expand=True)
    middle = ttk.Frame(win, padding=12)
    middle.pack(fill='both', expand=True)
    tree = ttk.Treeview(middle, columns=('value',), show='tree headings', selectmode='browse')
    tree.heading('#0', text='Section / item')
    tree.heading('value', text='Result')
    tree.column('#0', width=300)
    tree.column('value', width=480)
    y = ttk.Scrollbar(middle, command=tree.yview)
    tree.configure(yscrollcommand=y.set)
    y.pack(side='right', fill='y')
    tree.pack(fill='both', expand=True)
    detail = tk.Text(win, height=4, wrap='word', state='disabled', padx=10, pady=6)
    theme_text(detail)
    detail.pack(fill='x', padx=12)
    def refresh(*_):
        tree.delete(*tree.get_children())
        cache = {}
        for path, text in readable_lines(value):
            if query.get().casefold() not in (path + ' ' + text).casefold():
                continue
            parts = path.split(' / ') if path else ['Result']
            parent_id = ''
            for i, part in enumerate(parts):
                key = tuple(parts[:i + 1])
                if key not in cache:
                    cache[key] = tree.insert(parent_id, 'end', text=part, values=(text if i == len(parts) - 1 else '',), open=True)
                parent_id = cache[key]
    def selected(_=None):
        ids = tree.selection()
        if ids:
            item = tree.item(ids[0])
            detail.configure(state='normal')
            detail.delete('1.0', 'end')
            detail.insert('1.0', item['text'] + '\n' + str(item['values'][0] if item['values'] else ''))
            detail.configure(state='disabled')
    def save():
        path = filedialog.asksaveasfilename(parent=win, defaultextension='.txt', filetypes=[('Readable report', '*.txt'), ('Spreadsheet table', '*.csv')])
        if not path:
            return
        from .security_tools import staged_file
        with staged_file(path) as stage:
            if Path(path).suffix.lower() == '.csv':
                with stage.open('w', encoding='utf-8-sig', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Item', 'Result'])
                    writer.writerows(readable_lines(value))
            else:
                stage.write_text(title + '\n\n' + report_text(value), encoding='utf-8')
    from .studio_windows import line, button, guarded
    bar = line(win)
    button(bar, 'Save report…', save)
    button(bar, 'Copy report', lambda: (win.clipboard_clear(), win.clipboard_append(report_text(value))))
    button(bar, 'Expand all', lambda: [tree.item(i, open=True) for i in walk_tree(tree)])
    button(bar, 'Collapse all', lambda: [tree.item(i, open=False) for i in walk_tree(tree)])
    button(bar, 'Close', win.destroy)
    query.trace_add('write', refresh)
    tree.bind('<<TreeviewSelect>>', selected)
    win.bind('<Escape>', lambda e: win.destroy())
    win.report_tree = tree
    refresh()
    return win


def walk_tree(tree, parent=''):
    for child in tree.get_children(parent):
        yield child
        yield from walk_tree(tree, child)


def theme_window(win):
    win.configure(background=ttk.Style(win).lookup('TFrame', 'background') or '#111827')


def theme_text(widget):
    style = ttk.Style(widget)
    bg = style.lookup('TEntry', 'fieldbackground') or '#0f172a'
    fg = style.lookup('TLabel', 'foreground') or '#e5e7eb'
    widget.configure(background=bg, foreground=fg, insertbackground=fg, selectbackground='#256c72',
                     relief='flat', highlightthickness=1, highlightbackground='#334155')


def ui_font(parent,size=11,bold=False):
    family=font.nametofont('TkDefaultFont',root=parent).actual()['family']
    return (family,size,'bold' if bold else 'normal')
