"""Visual production workflows for authors, narrators and audiobook editors."""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .gui_forms import (CHOICES, CollectionEditor, Field, FormEditor, choices,
                        edit_settings, label_for, show_report, validate_record, theme_window, theme_text, ui_font)
from .studio_windows import async_job, button, guarded, line
from .voice_library import _atomic_json
from .windowing import fit_window, scrollable_area


PREFERENCE_GROUPS = {
    'Appearance': ['language', 'font', 'font_size', 'interface_scale', 'high_contrast', 'touch', 'left_handed', 'reduced_motion'],
    'Quick access': ['toolbar', 'shortcuts', 'show_home_on_start'],
    'Production': ['gpu_mode', 'cpu_profile', 'audio_format', 'render_cache', 'import_preset'],
    'Access': ['permissions', 'model_lock'],
    'Translation': ['translate_missing', 'translation_file'],
}


def preferences(parent, cfg, save):
    # Internal onboarding state, history and future settings survive but need not
    # be exposed as configuration fields.
    visible = {k: copy.deepcopy(cfg[k]) for keys in PREFERENCE_GROUPS.values() for k in keys if k in cfg}
    def accept(data):
        merged = copy.deepcopy(cfg)
        merged.update(data)
        save(merged)
    fields = {
        'language': Field('Interface language', choices={'en': 'English', 'bn': 'Bengali', 'es': 'Spanish'}),
        'show_home_on_start': Field('Show the task hub when the app starts', 'boolean'),
    }
    return FormEditor(parent, 'Preferences', visible, accept, fields=fields, groups=PREFERENCE_GROUPS).win


def setup(studio):
    app = studio.app
    cfg = {'cpu_profile': 'balanced', 'gpu_mode': studio.prefs.get('gpu_mode', 'auto'),
           'audio_format': app.book_export_settings.get('audio_format', 'wav'),
           'render_cache': studio.prefs.get('render_cache', ''),
           'font_size': app.font_size, 'high_contrast': studio.prefs.get('high_contrast', False),
           'show_home_on_start': studio.prefs.get('show_home_on_start', True)}
    def apply(data):
        from .hardware import apply_cpu_profile, gpu_preference
        from . import desktop_prefs
        apply_cpu_profile(data['cpu_profile'])
        gpu_preference(data['gpu_mode'] != 'cpu')
        app.cpu_profile_var.set(data['cpu_profile'])
        app.gpu_var.set(data['gpu_mode'] != 'cpu')
        app.book_export_settings['audio_format'] = data['audio_format']
        if data['render_cache']:
            os.environ['OPENMUKTI_RENDER_CACHE'] = data['render_cache']
        studio.prefs = desktop_prefs.write(**data, welcome_seen=True)
        studio.apply_prefs()
        studio.status.set('Setup saved. Choose a voice, then preview a short passage.')
    return FormEditor(studio.root, 'Set up your audiobook workspace', cfg, apply,
        description='Choose how you want to work. Voice downloads are available separately in Voices.',
        groups={'Performance': ['cpu_profile', 'gpu_mode', 'render_cache'],
                'Audio': ['audio_format'], 'Comfort': ['font_size', 'high_contrast', 'show_home_on_start']},
        apply_label='Save setup').win


def remember_recent(path, kind='project'):
    from . import desktop_prefs
    filename = str(Path(path).expanduser().resolve())
    rows = [r for r in desktop_prefs.read().get('recent_files', []) if isinstance(r, dict) and r.get('path') != filename]
    rows.insert(0, {'path': filename, 'kind': kind})
    desktop_prefs.write(recent_files=rows[:12])


def project_wizard(app):
    if app.active:
        messagebox.showinfo('New project', 'Finish or stop the current job first.', parent=app.root)
        return
    data = {'title': '', 'author': '', 'manuscript': '', 'template_file': '', 'project_file': '', 'open_project': True}
    def save(d):
        from .documents import read_document
        from .project_archive import ProjectData, load_project, project_template, save_project
        target = Path(d['project_file']).expanduser()
        if target.suffix.lower() != '.oamproj':
            raise ValueError('Choose a project filename ending in .oamproj.')
        if target.exists() and not messagebox.askyesno('Replace project', 'Replace the existing project ' + target.name + '?', parent=app.root):
            raise ValueError('Choose another project filename.')
        with tempfile.TemporaryDirectory(prefix='openmukti-project-') as stage:
            project = project_template(load_project(d['template_file'], stage)) if d['template_file'] else ProjectData()
            project.settings['production'] = {**project.settings.get('production', {}), 'title': d['title'].strip(), 'author': d['author'].strip()}
            if d['manuscript']:
                project.text = read_document(d['manuscript'])
                project.current_filename = Path(d['manuscript']).name
            save_project(target, project)
        remember_recent(target)
        app.status_var.set('Created project: ' + str(target))
        if d['open_project']:
            app.open_entire_project(str(target))
    return FormEditor(app.root, 'Create an audiobook project', data, save,
        fields={'title': Field('Book title', required=True), 'author': Field('Author / creator'),
                'template_file': Field('Optional saved project template', 'file'),
                'project_file': Field('Save project as', 'savefile', required=True, extension='.oamproj'),
                'open_project': Field('Open the project after creating it', 'boolean')},
        description='Name the book, optionally choose a manuscript and template, then pick where to save it.', apply_label='Create project').win


def caption_designer(studio):
    app = studio.app
    data = {'caption_preset': app.video_options.get('caption_preset', 'white on black'),
            'safe_margin': app.video_options.get('safe_margin', .09)}
    def save(d):
        app.video_options.update(d)
        studio.status.set('Caption design applied to audiobook video.')
    form = FormEditor(studio.root, 'Caption design', data, save,
        description='Preview caption contrast and the safe area before exporting a video.')
    preview = tk.Canvas(form.body, height=190, background='#31475d', highlightthickness=0)
    preview.pack(side='bottom', fill='x', padx=16, pady=8)
    def draw(*_):
        width, height = max(280, preview.winfo_width()), 190
        try:
            margin = float(form.controls['safe_margin'].get())
            preset = form.controls['caption_preset'].get()
        except ValueError:
            return
        colors = {'white on black': ('#ffffff', '#000000'), 'yellow on black': ('#ffff00', '#000000'),
                  'black on white': ('#000000', '#ffffff'), 'custom': ('#ffffff', '#182636')}
        fg, bg = colors[preset]
        preview.delete('all')
        x = width * margin
        preview.create_rectangle(x, height * margin, width - x, height * (1 - margin), outline='#8de4c1', dash=(5, 4))
        preview.create_rectangle(x, 112, width - x, 155, fill=bg, outline=bg)
        preview.create_text(width / 2, 134, text='A new chapter begins.', fill=fg, font=ui_font(form.win,16), width=max(120, width - 2 * x - 14))
        preview.create_text(12, 17, text='Safe area preview', fill='white', anchor='w')
    for c in form.controls.values():
        if c.variable:
            c.variable.trace_add('write', draw)
    preview.bind('<Configure>', draw)
    draw()
    return form.win


def job_arguments(data):
    """Translate friendly job controls to the existing durable renderer protocol."""
    source = Path(data['manuscript']).expanduser().resolve(strict=True)
    output = Path(data['output']).expanduser().resolve()
    if not source.is_file() or source == output:
        raise ValueError('Choose a manuscript file and a different audio output.')
    if output.suffix.lower() not in {'.wav', '.mp3', '.m4a', '.flac', '.ogg', '.opus'}:
        raise ValueError('Choose WAV, MP3, M4A, FLAC, OGG or Opus output.')
    task_type=data.get('task_type','render')
    if task_type=='project-render':
        if source.suffix.lower()!='.oamproj':
            raise ValueError('Choose a saved .oamproj file for a complete project render.')
        argv=['project-render',str(source),'-w',str(output)]
    elif task_type=='render':
        argv = ['render', '-f', str(source), '-w', str(output), '--engine', data.get('engine', 'auto')]
        for key in ('voice', 'model', 'language'):
            if data.get(key):
                argv += ['--' + key, str(data[key])]
        if data.get('speaker_id') is not None:
            argv += ['--speaker-id', str(int(data['speaker_id']))]
        for key in ('rate', 'pitch', 'volume'):
            if key in data:
                argv += ['--' + key, str(data[key])]
        for key,flag in [('dictionary','--dictionary'),('ipa_dictionary','--ipa-dictionary')]:
            if data.get(key):argv += [flag,str(data[key])]
        if data.get('repair_ocr'):argv.append('--repair-ocr')
    else:
        raise ValueError('Choose a document or a saved project to render.')
    ready = 0
    if data.get('at', '').strip():
        try:
            ready = dt.datetime.fromisoformat(data['at'].strip()).timestamp()
        except ValueError:
            raise ValueError('Enter a local date and time, for example 2026-11-05 18:30.') from None
    return argv, int(data.get('priority', 0)), ready


def queue_job(parent, app, save, source='', output=''):
    from .piper_models import speaker_id_from_label
    data = {'task_type':'render','manuscript': source, 'output': output, 'engine': app.engine_var.get(),
            'voice': app.voice_var.get(), 'model': app.model_var.get(),
            'language': app.tts_language_var.get(), 'speaker_id': speaker_id_from_label(app.speaker_var.get()),
            'rate': app.rate_var.get(), 'pitch': app.pitch_var.get(), 'volume': app.volume_var.get(),
            'dictionary':app.dict_var.get(),'ipa_dictionary':app.ipa_dict_var.get(),'repair_ocr':app.ocr_var.get(),
            'priority': 0, 'at': ''}
    def accept(data):
        save(*job_arguments(data))
    return FormEditor(parent, 'Add audiobook to the production queue', data, accept,
        fields={'output': Field('Save audio as', 'savefile',required=True),
                'manuscript':Field('Source document or saved project','file',required=True),
                'task_type':Field('Render from',choices={'render':'A document with one voice','project-render':'A saved project with its complete cast'}),
                'dictionary':Field('Word substitutions','file'),'ipa_dictionary':Field('IPA pronunciation dictionary','file')},
        groups={'Files': ['task_type','manuscript', 'output'], 'Document voice': ['engine', 'voice', 'model', 'language', 'speaker_id', 'rate', 'pitch', 'volume','dictionary','ipa_dictionary','repair_ocr'], 'Schedule': ['priority', 'at']},
        description='A saved project uses its own cast and settings. Document jobs use the controls in Document voice.', apply_label='Add to queue').win


def friendly_job(row):
    try:
        args = json.loads(row['arguments']) if isinstance(row['arguments'], str) else row['arguments']
        def arg(*names):
            return next((args[i + 1] for i, v in enumerate(args[:-1]) if v in names), '')
        name = Path(arg('-f', '--file', '--input') or (args[1] if args[0]=='project-render' else '')).name or label_for(args[0])
        target = Path(arg('-w', '--output', '--output-dir')).name
        return f'{name} → {target}' if target else name
    except (ValueError, TypeError, IndexError):
        return 'Production task'


def current_cast(app):
    from .piper_models import speaker_id_from_label
    cast = {'Narrator': {'engine': app.engine_var.get(), 'voice': app.voice_var.get(),
                        'model': app.model_var.get(), 'language': app.tts_language_var.get(),
                        'speaker_id': speaker_id_from_label(app.speaker_var.get()),
                        'rate':app.rate_var.get(),'pitch':app.pitch_var.get(),'volume':app.volume_var.get()}}
    default=copy.deepcopy(cast['Narrator'])
    for p in app.voice_project.profiles:
        fallback=p.engine=='auto' and not (p.voice or p.model)
        name='Narrator' if p.name.casefold()=='narrator' else p.name
        cast[name] = {'engine': default['engine'] if fallback else 'piper' if p.engine=='auto' and p.voice else p.engine,
                        'voice':default['voice'] if fallback else p.voice,
                        'model':default['model'] if fallback else p.model,
                        'language':default['language'] if p.language=='auto' else p.language,
                        'speaker_id':default['speaker_id'] if fallback else p.speaker_id,
                        'rate':default['rate'] if p.name.casefold()=='narrator' and fallback else p.rate,
                        'pitch':default['pitch'] if p.name.casefold()=='narrator' and fallback else p.pitch,
                        'volume':default['volume'] if p.name.casefold()=='narrator' and fallback else p.volume}
    return cast


class TimedManuscriptError(ValueError):
    pass


def score_from_text(text, cast=None):
    from .timeline_tags import has_timeline_tags
    if has_timeline_tags(text):
        raise TimedManuscriptError('Your manuscript uses timed audio cues. Export audio preserves them. This separate planner starts empty; open a plan or add passages here.')
    cast=copy.deepcopy(cast or {'Narrator':{'engine':'auto'}})
    from .character_voices import CharacterProfile,parse_passages
    tagged=bool(re.search(r'\[[^\[\]\n]+\]',text)) or bool(re.search(r'(?m)^\s*('+ '|'.join(re.escape(n) for n in cast)+r'):\s',text))
    source=[(p.speaker,p.text) for p in parse_passages(text,[CharacterProfile(n) for n in cast])] if tagged else [('Narrator',p) for p in re.split(r'\n\s*\n',text)]
    passages = [{'text': paragraph.strip(), 'profile': name, 'emotion': 'neutral',
                 'pace': 1.0, 'semitones': 0.0, 'gain_db': 0.0}
                for name,paragraph in source if paragraph.strip()]
    return {'profiles': cast,
            'sounds': {}, 'scenes': [{'title': 'Scene 1', 'narrator': 'Narrator', 'passages': passages}]}


class NarrationDesk:
    """A scene and passage editor over the complete existing performance engine."""
    def __init__(self, app):
        self.app = app
        notice='Arrange speech, pauses and sounds. Double-click a passage to edit it.'
        try:
            initial=score_from_text(app._get_text(), current_cast(app))
        except TimedManuscriptError as exc:
            initial=score_from_text('',current_cast(app))
            notice=str(exc)
        self.win = tk.Toplevel(app.root)
        theme_window(self.win)
        self.win.title('Narration planner')
        fit_window(self.win, 1000, 680, 460, 350)
        self.path = None
        self.spec = initial
        self.dirty = False
        self.control = None
        self.scene_index = 0
        self.status = tk.StringVar(self.win, value=notice)
        bar = line(self.win)
        for title, action in [('Open plan', self.open), ('Save plan', self.save), ('Character voices', self.cast), ('Approved sounds', self.sounds)]:
            button(bar, title, action)
        scene_bar = line(self.win)
        ttk.Label(scene_bar, text='Scene').pack(side='left')
        self.scene_var = tk.StringVar(self.win)
        self.scenes = ttk.Combobox(scene_bar, textvariable=self.scene_var, state='readonly', width=28)
        self.scenes.pack(side='left')
        self.scenes.bind('<<ComboboxSelected>>', lambda e: self.change_scene())
        for title, action in [('Add scene', self.add_scene), ('Rename', self.rename_scene), ('Remove scene', self.remove_scene)]:
            button(scene_bar, title, action)
        middle = ttk.Frame(self.win, padding=8)
        middle.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(middle, columns=('kind', 'voice', 'text'), show='headings', selectmode='browse')
        for name, label, width in [('kind', 'Type', 100), ('voice', 'Character / emotion', 190), ('text', 'Passage / timing', 500)]:
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width)
        scroll = ttk.Scrollbar(middle, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<Double-Button-1>', lambda e: self.edit())
        self.tree.bind('<Return>', lambda e: self.edit())
        bar = line(self.win)
        for title, action in [('Add speech', self.add_speech), ('Add pause', self.add_pause), ('Add sound', self.add_sound),
                              ('Edit', self.edit), ('Duplicate', self.duplicate), ('Remove', self.remove),
                              ('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1))]:
            button(bar, title, action)
        bar = line(self.win)
        button(bar, 'Render audio…', self.render)
        button(bar, 'Stop rendering', self.stop)
        button(bar, 'Check plan', self.check)
        button(bar, 'Close', self.close)
        ttk.Label(self.win, textvariable=self.status, wraplength=820).pack(fill='x', padx=12, pady=6)
        self.win.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()

    def rows(self):
        return self.spec['scenes'][self.scene_index].setdefault('passages', [])

    def refresh(self, selected=None):
        names = [str(s.get('title') or f'Scene {i + 1}') for i, s in enumerate(self.spec['scenes'])]
        self.scenes.configure(values=[f'{i + 1}. {name}' for i, name in enumerate(names)])
        self.scenes.current(self.scene_index)
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows()):
            kind = 'Speech' if 'text' in row else 'Pause' if 'pause' in row else 'Sound' if 'sound' in row else 'Marker'
            detail = row.get('text', f'{row["pause"]:g} seconds' if 'pause' in row else row.get('sound', row.get('mark', '')))
            self.tree.insert('', 'end', iid=str(i), values=(kind, row.get('profile', '') + (' · ' + row.get('emotion', 'neutral') if kind == 'Speech' else ''), str(detail).replace('\n', ' ')))
        if selected is not None and self.tree.exists(str(selected)):
            self.tree.selection_set(str(selected))
            self.tree.see(str(selected))
        self.win.title('Narration planner' + (' · Unsaved changes' if self.dirty else ''))

    def selected(self):
        ids = self.tree.selection()
        return int(ids[0]) if ids else None

    def change_scene(self):
        self.scene_index = self.scenes.current()
        self.refresh()

    def update(self, rows):
        self.spec['scenes'][self.scene_index]['passages'] = rows
        self.dirty = True
        self.refresh()

    def edit_row(self, row, accept):
        fields = {'profile': Field('Character voice', choices={n: n for n in self.spec['profiles']})}
        if 'sound' in row:
            fields['sound'] = Field('Approved sound', choices={n: n for n in self.spec.get('sounds', {})})
        FormEditor(self.win, 'Speech direction' if 'text' in row else 'Pause' if 'pause' in row else 'Sound or marker', row, accept, fields=fields)

    def add_speech(self):
        self.edit_row({'text': '', 'profile': next(iter(self.spec['profiles'])), 'emotion': 'neutral', 'pace': 1.0, 'semitones': 0.0, 'gain_db': 0.0}, self.append)

    def append(self, row):
        if 'text' in row and not row['text'].strip():
            raise ValueError('Enter the words to speak.')
        self.rows().append(row)
        self.dirty = True
        self.refresh(len(self.rows()) - 1)

    def add_pause(self):
        self.edit_row({'pause': .5}, self.append)

    def add_sound(self):
        if not self.spec.get('sounds'):
            self.sounds()
            return
        self.edit_row({'sound': next(iter(self.spec['sounds']))}, self.append)

    def edit(self):
        i = self.selected()
        if i is None:
            return
        scene = self.spec['scenes'][self.scene_index]
        original = copy.deepcopy(scene['passages'][i])
        def save(row):
            if not any(s is scene for s in self.spec['scenes']) or i >= len(scene['passages']) or scene['passages'][i] != original:
                raise ValueError('This passage changed. Reopen its editor.')
            if 'text' in row and not row['text'].strip():
                raise ValueError('Enter the words to speak.')
            scene['passages'][i] = row
            self.dirty = True
            self.refresh(i)
        self.edit_row(original, save)

    def duplicate(self):
        i = self.selected()
        if i is not None:
            self.rows().insert(i + 1, copy.deepcopy(self.rows()[i]))
            self.dirty = True
            self.refresh(i + 1)

    def remove(self):
        i = self.selected()
        if i is not None:
            self.rows().pop(i)
            self.dirty = True
            self.refresh(max(0, i - 1))

    def move(self, delta):
        i = self.selected()
        if i is not None and 0 <= i + delta < len(self.rows()):
            self.rows().insert(i + delta, self.rows().pop(i))
            self.dirty = True
            self.refresh(i + delta)

    def add_scene(self):
        def save(d):
            self.spec['scenes'].append({'title': d['title'], 'narrator': 'Narrator', 'passages': []})
            self.scene_index = len(self.spec['scenes']) - 1
            self.dirty = True
            self.refresh()
        FormEditor(self.win, 'New scene', {'title': f'Scene {len(self.spec["scenes"]) + 1}'}, save, fields={'title': Field('Scene title', required=True)})

    def rename_scene(self):
        scene = self.spec['scenes'][self.scene_index]
        def save(d):
            scene['title'] = d['title']
            self.dirty = True
            self.refresh()
        FormEditor(self.win, 'Rename scene', {'title': scene.get('title', '')}, save, fields={'title': Field('Scene title', required=True)})

    def remove_scene(self):
        if len(self.spec['scenes']) == 1:
            self.status.set('Keep at least one scene. Remove individual passages to clear it.')
        elif messagebox.askyesno('Remove scene', 'Remove this scene and its passages?', parent=self.win):
            self.spec['scenes'].pop(self.scene_index)
            self.scene_index = max(0, self.scene_index - 1)
            self.dirty = True
            self.refresh()

    def cast(self):
        def save(data):
            if not data or 'Narrator' not in data:
                raise ValueError('Keep the Narrator voice profile.')
            for scene in self.spec['scenes']:
                for row in scene.get('passages', []):
                    if 'text' in row and row.get('profile', scene.get('narrator', 'Narrator')) not in data:
                        raise ValueError('A passage still uses a removed voice profile.')
            self.spec['profiles'] = data
            self.dirty = True
            self.refresh()
        CollectionEditor(self.win, 'Narration voice profiles', self.spec['profiles'], save, context='profiles')

    def sounds(self):
        def save(data):
            for name, path in data.items():
                if not Path(path).is_file():
                    raise ValueError('Choose an existing local recording for ' + name)
            for scene in self.spec['scenes']:
                if any('sound' in row and row['sound'] not in data for row in scene.get('passages',[])):
                    raise ValueError('A passage still uses a removed sound. Change that passage first.')
            self.spec['sounds'] = data
            self.dirty = True
        editor = CollectionEditor(self.win, 'Approved local sounds', self.spec.get('sounds', {}), save, context='sounds')
        return editor

    def discard_ok(self):
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel('Unsaved narration plan', 'Save your narration plan before continuing?', parent=self.win)
        return False if answer is None else self.save() if answer else True

    def open(self):
        if not self.discard_ok():
            return
        path = filedialog.askopenfilename(parent=self.win, filetypes=[('Narration plans', '*.oamscore *.json *.ssml *.xml')])
        if not path:
            return
        from .performance import read_score, parse_ssml, plan_score
        data = read_score(path)
        data.setdefault('profiles', current_cast(self.app))
        for scene in data['scenes']:
            if scene.get('ssml'):
                scene['passages'] = parse_ssml(scene.pop('ssml'), {'profile': scene.get('narrator', 'Narrator')})
        plan_score(data)
        for profile in data['profiles'].values():
            if profile.get('model') and (Path(path).parent / profile['model']).is_file():
                profile['model'] = str((Path(path).parent / profile['model']).resolve())
        data['sounds'] = {k: str((Path(path).parent / v).resolve()) for k, v in data.get('sounds', {}).items()}
        self.spec, self.path, self.scene_index, self.dirty = data, Path(path), 0, False
        self.refresh()

    def save(self):
        path = filedialog.asksaveasfilename(parent=self.win, initialfile=self.path.stem+'.oamscore' if self.path else 'narration.oamscore', defaultextension='.oamscore', filetypes=[('Narration plan', '*.oamscore')])
        if not path:
            return False
        if Path(path).suffix.lower()!='.oamscore':
            raise ValueError('Save this narration plan with the .oamscore extension.')
        _atomic_json(Path(path), self.spec)
        self.path, self.dirty = Path(path), False
        self.refresh()
        self.status.set('Saved ' + self.path.name)
        return True

    def check(self):
        from .performance import plan_score
        plan = plan_score(self.spec)
        for row in plan:
            if 'text' in row:
                validate_record(row)
            if 'sound' in row and row['sound'] not in self.spec.get('sounds', {}):
                raise ValueError('Choose an approved recording for ' + row['sound'])
        show_report(self.win, 'Narration plan check', {'speech_passages': sum('text' in r for r in plan), 'pauses': sum('pause' in r for r in plan),
                    'sound_cues': sum('sound' in r for r in plan), 'words': sum(len(r.get('text', '').split()) for r in plan), 'voice_profiles': list(self.spec['profiles'])})

    def render(self):
        if getattr(self.win, '_studio_busy', False):
            return
        from .performance import plan_score, render_score
        from .engines import RunControl
        plan_score(self.spec)
        if not confirm_cast(self.app, self.spec['profiles'], '\n'.join(r.get('text', '') for s in self.spec['scenes'] for r in s.get('passages', [])), self.win):
            return
        out = filedialog.asksaveasfilename(parent=self.win, defaultextension='.wav', filetypes=[('Audio', '*.wav *.mp3 *.flac *.m4a *.ogg *.opus')])
        if not out:
            return
        self.control = RunControl()
        spec, control = copy.deepcopy(self.spec), self.control
        def work():
            with tempfile.TemporaryDirectory(prefix='openmukti-narration-') as tmp:
                path = Path(tmp) / 'plan.json'
                _atomic_json(path, spec)
                return render_score(path, out, control=control)
        async_job(self.win, self.status, work, lambda p: self.status.set('Saved audio: ' + str(p)))

    def stop(self):
        if self.control:
            self.control.stop()
            self.status.set('Stopping after the current operation…')

    def close(self):
        if getattr(self.win, '_studio_busy', False):
            self.stop()
            self.status.set('Stopping. Close this window when rendering has stopped.')
            return
        if self.discard_ok():
            self.win.destroy()


def confirm_cast(app, cast, text, parent):
    from .engines import SpeechSettings
    from .performance import profiles
    # Performance profiles use normal engine selection. In particular a system
    # voice under Auto must not be mistaken for a legacy Auto/Piper character.
    for row in profiles({'profiles':cast}).values():
        settings=SpeechSettings(voice=row.get('voice',''),model=row.get('model',''),language=row.get('language','auto'),speaker_id=row.get('speaker_id'))
        if not app._confirm_piper_downloads(row.get('engine','auto'),settings,parent=parent):
            return False
    return True


def auditions(app):
    cast = current_cast(app)
    data = {'test_text': 'The first chapter begins on a quiet morning.', 'profiles': cast, 'output_folder': ''}
    def accept(d):
        if not d['test_text'].strip() or not d['profiles'] or not d['output_folder']:
            raise ValueError('Enter a sample passage, choose voices and select an output folder.')
        if not confirm_cast(app, d['profiles'], d['test_text'], app.root):
            raise ValueError('Voice download was cancelled. Choose installed voices or try again.')
        from .local_speech import audition
        spec = copy.deepcopy(d)
        def work():
            with tempfile.TemporaryDirectory(prefix='openmukti-audition-') as tmp:
                p = Path(tmp) / 'cast.json'
                _atomic_json(p, spec)
                return audition(p, spec['output_folder'])
        async_job(app.root, app.status_var, work, lambda p: webbrowser.open(Path(p).as_uri()))
    return FormEditor(app.root, 'Compare character voices', data, accept,
        description='Use your existing cast, edit the sample, and generate a local listening page.', apply_label='Create listening comparison').win


class PronunciationDesk:
    def __init__(self, app):
        self.app = app
        self.path = app.dict_var.get()
        self.rows = []
        if self.path:
            from .processing import load_replacements
            self.rows = load_replacements([self.path])
        self.editor = CollectionEditor(app.root, 'Word substitutions', self.rows, self.save, context='rules',
            template={'find': '', 'replace': '', 'case_sensitive': False},
            item_fields={'find': Field('Written word or phrase', required=True), 'replace': Field('Speak as')})
        self.win = self.editor.win
        bar = line(self.win)
        button(bar, 'Import dictionary…', self.open)
        button(bar, 'Try on current manuscript', self.preview)
        button(bar, 'Clear dictionary from narration', lambda: (app.dict_var.set(''), self.win.destroy()))

    def open(self):
        path = filedialog.askopenfilename(parent=self.win, filetypes=[('Pronunciation dictionary', '*.json *.tsv *.txt *.dic')])
        if path:
            from .processing import load_replacements
            self.editor.data = load_replacements([path])
            self.path = path
            self.editor.refresh()

    def preview(self):
        from .processing import apply_replacements
        before = self.app._get_text()
        after = apply_replacements(before, self.editor.data)
        win = tk.Toplevel(self.win)
        win.title('Pronunciation preview')
        fit_window(win, 800, 500, 360, 280)
        pane = ttk.Panedwindow(win, orient='horizontal')
        pane.pack(fill='both', expand=True)
        for title, text in [('Written manuscript', before), ('Words sent to the voice', after)]:
            panel = ttk.Frame(pane)
            pane.add(panel, weight=1)
            ttk.Label(panel, text=title).pack(anchor='w')
            box = tk.Text(panel, wrap='word')
            box.pack(fill='both', expand=True)
            box.insert('1.0', text)
            box.configure(state='disabled')
        button(line(win), 'Close', win.destroy)

    def save(self, rows):
        from .processing import apply_replacements
        for row in rows:
            if not row.get('find'):
                raise ValueError('Every substitution needs a word or phrase to find.')
        apply_replacements(self.app._get_text(), rows)
        path = filedialog.asksaveasfilename(parent=self.win, initialfile=Path(self.path).name if self.path else 'pronunciations.json',
            defaultextension='.json', filetypes=[('Pronunciation dictionary', '*.json')])
        if not path:
            raise ValueError('Choose a file to save and use these substitutions.')
        _atomic_json(Path(path), rows)
        self.app.dict_var.set(path)
        self.app.status_var.set('Word substitutions saved and enabled for narration.')


AUDIO_OPERATIONS = {
    'convert': 'Change audio format', 'join': 'Join recordings in order', 'trim': 'Keep a time range',
    'speed': 'Change speaking speed', 'gain': 'Change volume', 'normalize': 'Normalize loudness',
    'reverse': 'Reverse audio', 'fade-in': 'Fade in', 'fade-out': 'Fade out',
    'mono': 'Convert to mono', 'stereo': 'Convert to stereo', 'resample': 'Change sample rate',
    'denoise': 'Reduce noise', 'compress': 'Compress dynamic range', 'deess': 'Reduce harsh S sounds',
    'equalize': 'Adjust a frequency band', 'pan': 'Position sound left / right', 'trim-silence': 'Remove silence',
}


def audio_processor(app):
    if app.active:
        messagebox.showinfo('Audio processing', 'Finish or stop the current job first.', parent=app.root)
        return
    win = tk.Toplevel(app.root)
    theme_window(win)
    win.title('Audio processor')
    fit_window(win, 750, 610, 420, 330)
    operation = tk.StringVar(win, value=AUDIO_OPERATIONS['normalize'])
    ttk.Label(win, text='What would you like to do?', font=ui_font(win,16,True)).pack(anchor='w', padx=12, pady=10)
    ttk.Combobox(win, textvariable=operation, values=list(AUDIO_OPERATIONS.values()), state='readonly').pack(fill='x', padx=12)
    filenames = []
    lb = tk.Listbox(win, height=6, exportselection=False)
    lb.pack(fill='both', expand=True, padx=12, pady=8)
    def refresh():
        lb.delete(0, 'end')
        for name in filenames:
            lb.insert('end', Path(name).name)
    def add():
        filenames.extend(filedialog.askopenfilenames(parent=win, title='Choose audio files'))
        refresh()
    def remove():
        if lb.curselection():
            filenames.pop(lb.curselection()[0])
            refresh()
    def move(delta):
        if lb.curselection():
            i = lb.curselection()[0]
            if 0 <= i + delta < len(filenames):
                filenames.insert(i + delta, filenames.pop(i))
                refresh()
                lb.selection_set(i + delta)
    bar = line(win)
    for text, action in [('Add audio', add), ('Remove', remove), ('Move up', lambda: move(-1)), ('Move down', lambda: move(1))]:
        button(bar, text, action)
    params = {
        'trim': {'start': 0.0, 'duration': 10.0}, 'speed': {'speed': 1.25}, 'gain': {'gain': 3.0},
        'fade-in': {'fade_seconds': 1.0}, 'fade-out': {'fade_seconds': 1.0}, 'resample': {'sample_rate': 44100},
        'equalize': {'eq_frequency': 1000.0, 'eq_gain': 3.0}, 'pan': {'pan': 0.0},
        'trim-silence': {'silence_db': -45.0, 'silence_duration': .3}, 'compress': {'compression': 0},
    }
    def process():
        op = next(k for k, v in AUDIO_OPERATIONS.items() if v == operation.get())
        if not filenames or (op == 'join' and len(filenames) < 2) or (op != 'join' and len(filenames) != 1):
            raise ValueError('Select at least two recordings to join, or one recording for other operations.')
        def run(options):
            if app.active:
                raise ValueError('Finish or stop the current job first.')
            output = filedialog.asksaveasfilename(parent=win, defaultextension='.wav', filetypes=[('Audio', '*.wav *.mp3 *.flac *.ogg *.m4a *.opus')])
            if not output:
                raise ValueError('Choose an output file to continue.')
            from .audiofx import process_audio
            sources = list(filenames)
            async_job(app.root, app.status_var, lambda: process_audio(sources, output, operation=op, **options), lambda p: app.status_var.set('Saved audio: ' + str(p)))
            win.destroy()
        values = params.get(op, {})
        if values:
            limits = {'speed': (.25, 4), 'gain': (-60, 30), 'fade_seconds': (0, 60), 'eq_frequency': (20, 20000), 'eq_gain': (-24, 24), 'silence_db': (-90, -10), 'silence_duration': (.05, 30), 'compression': (0, 100)}
            specs = {key: Field({'speed': 'Speed multiplier', 'gain': 'Volume change (dB)', 'eq_frequency': 'Frequency (Hz)', 'eq_gain': 'Band gain (dB)'}.get(key, label_for(key)), 'integer' if isinstance(v, int) else 'number', minimum=limits[key][0], maximum=limits[key][1]) for key, v in values.items() if key in limits}
            FormEditor(win, AUDIO_OPERATIONS[op], values, run, fields=specs, apply_label='Choose output and process')
        else:
            run({})
    ttk.Label(win, text='For joining, files play in the displayed order. Other operations use one file.', wraplength=630).pack(anchor='w', padx=12, pady=4)
    bar = line(win)
    button(bar, 'Continue…', process)
    button(bar, 'Cancel', win.destroy)
    return win


class TaskHub:
    def __init__(self, studio):
        self.studio, self.app = studio, studio.app
        self.win = tk.Toplevel(studio.root)
        theme_window(self.win)
        self.win.title('Openmukti · Start creating')
        fit_window(self.win, 1040, 720, 460, 360)
        self.win.task_hub = self
        self.search = tk.StringVar(self.win)
        self.category = tk.StringVar(self.win, value='All tools')
        self.categories = ['All tools', 'Write & review', 'Voices & narration', 'Art & sound', 'Produce & export', 'Workspace']
        self.actions = [
            ('New audiobook project', 'Create a named project and import a manuscript.', 'Write & review', self.app.project_wizard),
            ('Open a project', 'Continue a complete audiobook project.', 'Write & review', self.app.open_entire_project),
            ('Import a document', 'Bring a document into the manuscript editor.', 'Write & review', self.app.open_file),
            ('Import scanned pages', 'Recognize text from images and scanned books.', 'Write & review', self.app.import_scans),
            ('Project workspace', 'Work with tabs, chapter order and review rules.', 'Write & review', studio.actions['Project tabs']),
            ('Find and replace', 'Find words or change wording throughout the text.', 'Write & review', self.app.find_replace),
            ('Text tools', 'Clean up and transform a manuscript.', 'Write & review', self.app.tools_dialog),
            ('Editorial review', 'Inspect names, dialogue, readability and OCR artifacts.', 'Write & review', self.app.editorial_reports),
            ('Character voices', 'Find speakers and assign individual voices.', 'Voices & narration', self.app.character_voice_studio),
            ('Download voices', 'Choose Piper voices and download them explicitly.', 'Voices & narration', self.app.voice_downloader),
            ('More neural voices', 'Manage Kokoro, Kitten, Pocket and Coqui voices.', 'Voices & narration', self.app.neural_voice_downloader),
            ('Word substitutions', 'Teach the narrator how to say words and names.', 'Voices & narration', lambda: PronunciationDesk(self.app)),
            ('IPA pronunciations', 'Set precise pronunciations using a dictionary table.', 'Voices & narration', self.app.ipa_editor),
            ('Narration planner', 'Arrange scenes, speech directions, pauses and sounds.', 'Voices & narration', lambda: NarrationDesk(self.app)),
            ('Compare voices', 'Create listening samples from your existing cast.', 'Voices & narration', lambda: auditions(self.app)),
            ('Read along', 'Follow highlighted text as it is narrated.', 'Voices & narration', studio.read_along),
            ('Cover designer', 'Arrange titles, artwork and overlays visually.', 'Art & sound', studio.actions['Cover designer']),
            ('Comic panel tour', 'Draw panels and choose the reading order.', 'Art & sound', lambda: self.panel_tour()),
            ('Sound timeline', 'Mix narration, music, ambience and effects.', 'Art & sound', studio.actions['Sound timeline']),
            ('Waveform editor', 'Select, extract and preview audio ranges.', 'Art & sound', studio.actions['Waveform editor']),
            ('Audio processor', 'Convert, trim, join and enhance recordings.', 'Art & sound', lambda: audio_processor(self.app)),
            ('Subtitle editor', 'Edit caption text and timing in a table.', 'Art & sound', studio.cues),
            ('Caption design', 'Choose caption colors and safe margins.', 'Art & sound', studio.caption_design),
            ('Export audio', 'Turn the manuscript into an audio recording.', 'Produce & export', self.app.export),
            ('Make audiobook video', 'Combine narration, artwork and animated text.', 'Produce & export', self.app.video_dialog),
            ('Combine chapters', 'Assemble chapters and covers into audiobooks.', 'Produce & export', self.app.book_studio),
            ('Batch documents', 'Render several documents using the selected voice.', 'Produce & export', self.app.batch),
            ('Production queue', 'Schedule and manage audiobook rendering jobs.', 'Produce & export', studio.jobs),
            ('Export transcript', 'Save a readable PDF, HTML or text transcript.', 'Produce & export', self.app.export_transcript_dialog),
            ('Publishing check', 'Review finished book files before distribution.', 'Produce & export', self.app.publication_preflight_dialog),
            ('Preferences', 'Set appearance, shortcuts, language and access.', 'Workspace', studio.preferences),
            ('Guided setup', 'Choose production and accessibility defaults.', 'Workspace', studio.setup),
            ('Hardware check', 'See CPU and graphics capabilities in a readable report.', 'Workspace', self.app.hardware_diagnostics),
            ('User guide', 'Learn the production workflow.', 'Workspace', studio.help),
        ]
        self.actions.extend(studio.utilities)
        head = ttk.Frame(self.win, padding=16)
        head.pack(fill='x')
        heading=ttk.Label(head, text='What would you like to create?', font=ui_font(self.win,21,True),wraplength=950)
        heading.pack(anchor='w')
        head.bind('<Configure>',lambda e:heading.configure(wraplength=max(240,e.width-32)))
        from .texttools import text_stats
        stats = text_stats(self.app._get_text())
        ttk.Label(head, text=f'{stats["words"]:,} words in your manuscript  ·  About {stats["estimated_seconds"] / 60:.1f} minutes of narration',wraplength=550).pack(anchor='w', pady=5)
        search = ttk.Frame(self.win, padding=(14, 0))
        search.pack(fill='x')
        ttk.Label(search, text='Find a tool').pack(side='left', padx=(0, 7))
        entry = ttk.Entry(search, textvariable=self.search)
        entry.pack(side='left', fill='x', expand=True)
        combo = ttk.Combobox(search, textvariable=self.category, values=self.categories, state='readonly', width=23)
        combo.pack(side='left', padx=(8, 0))
        shell, self.panel, _ = scrollable_area(self.win)
        shell.pack(fill='both', expand=True, padx=4)
        self.search.trace_add('write', lambda *_: self.refresh())
        combo.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        footer = line(self.win)
        button(footer, 'Recent files', self.recent)
        button(footer, 'Production checklist', self.checklist)
        button(footer, 'Return to manuscript', self.win.destroy)
        from . import desktop_prefs
        show = tk.BooleanVar(self.win, value=desktop_prefs.read().get('show_home_on_start', True))
        ttk.Checkbutton(self.win, text='Show this window when Openmukti starts', variable=show,
                        command=lambda: desktop_prefs.write(show_home_on_start=show.get())).pack(anchor='w', padx=14, pady=5)
        self.win.bind('<Escape>', lambda e: self.win.destroy())
        entry.bind('<Return>', lambda e: self.run_first())
        self.refresh()
        entry.focus_set()

    def refresh(self):
        for child in self.panel.winfo_children():
            child.destroy()
        query = self.search.get().casefold()
        self.visible = [a for a in self.actions if query in ' '.join(a[:3]).casefold() and (self.category.get() == 'All tools' or a[2] == self.category.get())]
        for title, hint, category, action in self.visible:
            row = ttk.Frame(self.panel, padding=(8, 9))
            row.pack(fill='x', pady=2)
            row.columnconfigure(1,weight=1)
            launch=ttk.Button(row, text=title, width=26, command=guarded(self.win, action))
            launch.grid(row=0,column=0,sticky='w',padx=(0,12))
            description=ttk.Label(row,text=hint,wraplength=490)
            description.grid(row=0,column=1,sticky='w')
            def resize(event,frame=row,label=description):
                narrow=event.width<680
                label.grid_configure(row=1 if narrow else 0,column=0 if narrow else 1,columnspan=2 if narrow else 1,pady=(6,0) if narrow else 0)
                label.configure(wraplength=max(180,event.width-(25 if narrow else 265)))
            row.bind('<Configure>',resize)
        if not self.visible:
            ttk.Label(self.panel, text='No matching tools. Try another word or category.').pack(pady=25)

    def run_first(self):
        if self.visible:
            guarded(self.win, self.visible[0][3])()

    def panel_tour(self):
        from .media_windows import CanvasDesigner
        designer = CanvasDesigner(self.app)
        designer.panels()

    def checklist(self):
        checks = {'Manuscript contains text': bool(self.app._get_text().strip()),
                  'At least one character profile': bool(self.app.voice_project.profiles),
                  'Project has a saved file': bool(self.app.project_file),
                  'Video images chosen (optional)': bool(self.app.video_images)}
        show_report(self.win, 'Production checklist', {'completed_steps': sum(checks.values()), 'steps': checks,
                    'next_steps': ['Preview a short passage with your chosen voice.', 'Check names and pronunciations.', 'Export a short sample before rendering a full book.', 'Run the publishing check on your finished export folder.']})

    def recent(self):
        from . import desktop_prefs
        rows = desktop_prefs.read().get('recent_files', [])
        win = tk.Toplevel(self.win)
        win.title('Recent projects and documents')
        fit_window(win, 760, 400, 360, 260)
        lb = tk.Listbox(win, exportselection=False)
        lb.pack(fill='both', expand=True, padx=10, pady=10)
        for row in rows:
            p = Path(row['path'])
            lb.insert('end', f'{p.name}  ·  {p.parent}' + ('' if p.is_file() else '  (unavailable)'))
        if not rows:
            lb.insert('end', 'Your recently opened projects and documents will appear here.')
        def open_selected():
            if not rows or not lb.curselection():
                return
            row = rows[lb.curselection()[0]]
            path = Path(row['path'])
            if not path.is_file():
                raise ValueError('This file has moved or is unavailable. Use Open to locate it.')
            if row['kind'] == 'project':
                self.app.open_entire_project(str(path))
            else:
                self.app.open_file(str(path))
            win.destroy()
        button(line(win), 'Open selected', open_selected)
        button(line(win), 'Close', win.destroy)
        lb.bind('<Double-Button-1>', guarded(win, lambda e: open_selected()))


class PanelTour:
    """Draw normalized comic-panel crops on an image in reading order."""
    def __init__(self, parent, image_path, save):
        from PIL import Image, ImageOps, ImageTk
        self.ImageTk, self.save = ImageTk, save
        self.win = tk.Toplevel(parent)
        theme_window(self.win)
        self.win.title('Comic panel tour')
        fit_window(self.win, 1000, 680, 460, 340)
        with Image.open(image_path) as source:
            self.image = ImageOps.exif_transpose(source).convert('RGB')
        self.panels, self.anchor = [], None
        self.seconds = tk.StringVar(self.win, value='3')
        ttk.Label(self.win, text='Drag rectangles over the page in reading order. Select a panel to reorder it.').pack(anchor='w', padx=10, pady=8)
        pane = ttk.Panedwindow(self.win, orient='horizontal')
        pane.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(pane, background='#142536', highlightthickness=0)
        pane.add(self.canvas, weight=4)
        self.listing = tk.Listbox(pane, exportselection=False, width=24)
        pane.add(self.listing, weight=1)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.listing.bind('<<ListboxSelect>>', lambda e: self.draw())
        bar = line(self.win)
        ttk.Label(bar, text='Seconds per panel').pack(side='left')
        ttk.Spinbox(bar, from_=.15, to=3600, increment=.5, textvariable=self.seconds, width=7).pack(side='left')
        for label, cmd in [('Move up', lambda: self.move(-1)), ('Move down', lambda: self.move(1)), ('Remove', self.remove), ('Clear', self.clear), ('Add panel tour', self.apply), ('Cancel', self.win.destroy)]:
            button(bar, label, cmd)
        self.error = tk.StringVar(self.win)
        ttk.Label(self.win, textvariable=self.error, foreground='#ee8b80').pack(fill='x', padx=10)

    def draw(self):
        from PIL import ImageOps
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        preview = ImageOps.contain(self.image, (w, h))
        self.photo = self.ImageTk.PhotoImage(preview, master=self.win)
        self.bounds = ((w - preview.width) / 2, (h - preview.height) / 2, preview.width, preview.height)
        self.canvas.delete('all')
        x, y, iw, ih = self.bounds
        self.canvas.create_image(x, y, image=self.photo, anchor='nw')
        chosen = self.listing.curselection()
        for i, (l, t, r, b) in enumerate(self.panels):
            color = '#20c997' if chosen and chosen[0] == i else '#ffdf75'
            self.canvas.create_rectangle(x + l * iw, y + t * ih, x + r * iw, y + b * ih, outline=color, width=3)
            self.canvas.create_text(x + l * iw + 9, y + t * ih + 12, text=str(i + 1), fill=color, font=ui_font(self.win,16,True))

    def point(self, e):
        x, y, w, h = self.bounds
        return max(0, min(1, (e.x - x) / w)), max(0, min(1, (e.y - y) / h))

    def press(self, e):
        self.anchor = self.point(e)

    def drag(self, e):
        if self.anchor:
            x, y, w, h = self.bounds
            a, b = self.anchor
            c, d = self.point(e)
            self.canvas.delete('draft')
            self.canvas.create_rectangle(x + a * w, y + b * h, x + c * w, y + d * h, outline='#20c997', width=2, tags='draft')

    def release(self, e):
        if self.anchor:
            a, b = self.anchor
            c, d = self.point(e)
            if abs(a - c) > .01 and abs(b - d) > .01:
                self.panels.append([min(a, c), min(b, d), max(a, c), max(b, d)])
                self.refresh(len(self.panels) - 1)
            self.anchor = None
            self.draw()

    def refresh(self, index=None):
        self.listing.delete(0, 'end')
        for i in range(len(self.panels)):
            self.listing.insert('end', f'Panel {i + 1}')
        if index is not None and self.panels:
            self.listing.selection_set(min(index, len(self.panels) - 1))
        self.draw()

    def move(self, delta):
        ids = self.listing.curselection()
        if ids and 0 <= ids[0] + delta < len(self.panels):
            i = ids[0]
            self.panels.insert(i + delta, self.panels.pop(i))
            self.refresh(i + delta)

    def remove(self):
        ids = self.listing.curselection()
        if ids:
            self.panels.pop(ids[0])
            self.refresh()

    def clear(self):
        self.panels.clear()
        self.refresh()

    def apply(self):
        try:
            from .sound_studio import number
            if not self.panels:
                raise ValueError('Draw at least one panel first.')
            self.save({'panels': copy.deepcopy(self.panels), 'seconds': number(self.seconds.get(), .15, 3600, 'seconds per panel')})
        except Exception as exc:
            self.error.set(str(exc))
            return
        self.win.destroy()
