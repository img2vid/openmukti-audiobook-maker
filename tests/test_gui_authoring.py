"""Behavioral tests for the visual authoring layer. Tk tests require a display."""
import copy
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from openvoice.gui_forms import (CollectionEditor, Field, FormEditor, coerce,
                                  field_for, report_text, validate_record)
from openvoice.gui_workflows import friendly_job, job_arguments, score_from_text


class FormValues(unittest.TestCase):
    def test_audition_confirmation_keeps_auto_system_voices_and_resolves_inheritance(self):
        from openvoice.gui_workflows import confirm_cast
        from unittest.mock import Mock
        app=Mock()
        app._confirm_piper_downloads.return_value=True
        self.assertTrue(confirm_cast(app,{'Narrator':{'engine':'auto','voice':'slt'},'Mira':{'extends':'Narrator'}},'Hello',None))
        self.assertEqual(app._confirm_piper_downloads.call_count,2)
        engine,settings=app._confirm_piper_downloads.call_args.args
        self.assertEqual((engine,settings.voice),('auto','slt'))

    def test_graphical_build_selection_uses_existing_native_builder(self):
        from build_gui import build_command
        with patch('build_select.host_formats',return_value=['zip','tar']), patch('build_select.selected_profile',return_value='system'):
            args=build_command(['zip'],auto_dependencies=False,plan_only=True)
            self.assertIn('--no-auto-deps',args)
            self.assertIn('--deps-plan',args)
            self.assertEqual(args[args.index('--formats')+1],'zip')
            with self.assertRaises(ValueError):build_command(['exe'])

    def test_number_fields_reject_non_finite_and_out_of_range(self):
        for value in ('nan', 'inf', '-inf', '-1', '301', 'not a number'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                coerce(value, Field('Interface size', 'number', minimum=50, maximum=300))

    def test_integer_and_optional_speaker(self):
        self.assertEqual(coerce('125', Field('Size', 'integer')), 125)
        with self.assertRaises(ValueError):
            coerce('12.5', Field('Size', 'integer'))
        self.assertIsNone(coerce('', Field('Speaker', 'optional_integer')))
        self.assertEqual(field_for('gain', 1).kind, 'number')

    def test_boxes_and_subtitle_times(self):
        for data in ({'box': [0, 0, 0, 1]}, {'crop': [0, 1, 1, 0]}, {'box': [0, 0, float('nan'), 1]},
                     {'start': 2, 'end': 1}, {'loop': True}, {'duration': 2, 'fade_out': 3}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_record(data)
        self.assertEqual(validate_record({'box': [0, 0, 1, 1]}), {'box': [0, 0, 1, 1]})

    def test_bad_automation_order_rejected(self):
        with self.assertRaises(ValueError):
            validate_record({'duration': 10, 'curve': [[2, 1], [1, .5]]})

    def test_report_is_readable_and_preserves_unicode(self):
        text = report_text({'gpu_enabled': True, 'script': 'বাংলা', 'problems': [], 'speaker': None})
        self.assertIn('Gpu enabled: Yes', text)
        self.assertIn('Script: বাংলা', text)
        self.assertIn('Problems: No entries', text)
        self.assertIn('Speaker: Automatic', text)
        self.assertNotIn('{', text)

    def test_job_controls_generate_complete_render_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'my manuscript.txt'
            source.write_text('Hello', encoding='utf-8')
            data = {'manuscript': str(source), 'output': str(Path(folder) / 'book.wav'),
                    'engine': 'auto', 'voice': 'My voice', 'model': '', 'language': 'bn', 'speaker_id': 3,
                    'rate': 2, 'pitch': -1, 'volume': 85, 'priority': 8, 'at': '2026-11-05 18:30'}
            argv, priority, ready = job_arguments(data)
            self.assertEqual(priority, 8)
            self.assertGreater(ready, 0)
            self.assertEqual(argv[argv.index('--voice') + 1], 'My voice')
            self.assertEqual(argv[argv.index('--speaker-id') + 1], '3')
            self.assertEqual(argv[argv.index('--volume') + 1], '85')
            self.assertNotIn('render', friendly_job({'arguments': json.dumps(argv)}))
            data['at'] = 'tomorrow evening'
            with self.assertRaises(ValueError):
                job_arguments(data)
            data.update(at='', output=str(source))
            with self.assertRaises(ValueError):
                job_arguments(data)

    def test_saved_project_jobs_use_project_cast_and_not_document_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'book.oamproj'
            p.write_bytes(b'project')
            argv,_,_=job_arguments({'task_type':'project-render','manuscript':str(p),'output':str(Path(folder)/'book.mp3'),'engine':'piper'})
            self.assertEqual(argv[0],'project-render')
            self.assertNotIn('--engine',argv)
            self.assertIn('book.oamproj',friendly_job({'arguments':argv}))

    def test_narration_plan_keeps_paragraphs_and_cast_independent(self):
        cast = {'Narrator': {'engine': 'auto'}}
        data = score_from_text('First paragraph.\n\nবাংলা বই।', cast)
        self.assertEqual([r['text'] for r in data['scenes'][0]['passages']], ['First paragraph.', 'বাংলা বই।'])
        data['profiles']['Narrator']['engine'] = 'changed'
        self.assertEqual(cast['Narrator']['engine'], 'auto')
        from openvoice.performance import plan_score
        self.assertEqual(len(plan_score(data)), 2)

    def test_known_character_tags_become_visual_assignments(self):
        data=score_from_text('[Mira] Hello! [Narrator] She smiled.',{'Narrator':{'engine':'auto'},'Mira':{'engine':'auto'}})
        rows=data['scenes'][0]['passages']
        self.assertEqual([r['profile'] for r in rows],['Mira','Narrator'])
        self.assertEqual(rows[0]['text'],'Hello!')
        self.assertNotIn('[Mira]',rows[0]['text'])

    def test_timed_manuscripts_are_not_flattened_into_plain_speech(self):
        from openvoice.gui_workflows import TimedManuscriptError
        with self.assertRaises(TimedManuscriptError):score_from_text('[pause 1s] Hello.')


class VisualForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            probe = tk.Tk()
            probe.destroy()
        except tk.TclError:
            raise unittest.SkipTest('Desktop display is unavailable')

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.geometry('950x740')
        self.addCleanup(self.root.destroy)

    def test_cancel_and_nested_cancel_do_not_mutate_project(self):
        data = {'permissions': {'network': True}, 'markers': [{'time': 0.0, 'label': 'Start'}]}
        original = copy.deepcopy(data)
        saved = []
        form = FormEditor(self.root, 'Preferences', data, saved.append)
        form.controls['permissions'].edit_collection()
        child = [w for w in form.win.winfo_children() if hasattr(w, 'form_editor')][0]
        child.form_editor.controls['network'].variable.set(False)
        child.destroy()
        self.assertEqual(form.collect(), original)
        form.win.destroy()
        self.assertEqual(data, original)
        self.assertFalse(saved)

    def test_fractional_coordinates_and_dropdown_round_trip(self):
        saved = []
        form = FormEditor(self.root, 'Layer', {'box': [0, 0, 1, 1], 'gain': 1, 'space': 'dry', 'future': {'new_flag': True}}, saved.append)
        form.controls['box'].parts[0][0].set('.125')
        form.controls['gain'].variable.set('.5')
        form.controls['space'].variable.set('Small room')
        self.assertTrue(form.apply())
        self.assertEqual(saved[0]['box'][0], .125)
        self.assertEqual(saved[0]['gain'], .5)
        self.assertEqual(saved[0]['space'], 'small room')
        self.assertEqual(saved[0]['future'], {'new_flag': True})

    def test_invalid_input_keeps_dialog_open_and_preserves_old_value(self):
        saved = []
        form = FormEditor(self.root, 'Caption', {'safe_margin': .09}, saved.append)
        form.controls['safe_margin'].variable.set('nan')
        self.assertFalse(form.apply())
        self.assertTrue(form.win.winfo_exists())
        self.assertFalse(saved)
        self.assertIn('finite', form.error.get())
        form.reset()
        self.assertEqual(form.collect()['safe_margin'], .09)

    def test_readonly_choices_store_backend_ids(self):
        form = FormEditor(self.root, 'Settings', {'gpu_mode': 'auto', 'speaker_id': None}, lambda d: None)
        self.assertEqual(str(form.controls['gpu_mode'].widget['state']), 'readonly')
        form.controls['gpu_mode'].variable.set('Use processor only')
        self.assertEqual(form.collect()['gpu_mode'], 'cpu')
        self.assertIsNone(form.collect()['speaker_id'])

    def test_list_reorder_duplicate_remove_and_apply(self):
        source = [{'time': 0., 'label': 'Start'}, {'time': 2., 'label': 'End'}]
        saved = []
        ed = CollectionEditor(self.root, 'Markers', source, saved.append, context='markers')
        ed.tree.selection_set('0')
        ed.move(1)
        self.assertEqual(ed.data[1]['label'], 'Start')
        ed.duplicate()
        self.assertEqual(len(ed.data), 3)
        ed.remove()
        self.assertEqual(len(ed.data), 2)
        self.assertTrue(ed.apply())
        self.assertEqual(source[0]['label'], 'Start')
        self.assertEqual(saved[0][0]['label'], 'End')

    def test_search_uses_real_indices_when_editing(self):
        ed = CollectionEditor(self.root, 'Markers', [{'time': 0., 'label': 'Start'}, {'time': 2., 'label': 'Finish'}], lambda d: None, context='markers')
        ed.search.set('Finish')
        self.assertEqual(ed.tree.get_children(), ('1',))
        ed.tree.selection_set('1')
        ed.edit()
        child = next(w for w in ed.win.winfo_children() if hasattr(w, 'form_editor'))
        child.form_editor.controls['label'].variable.set('Changed')
        self.assertTrue(child.form_editor.apply())
        self.assertEqual(ed.data[1]['label'], 'Changed')
        self.assertEqual(ed.data[0]['label'], 'Start')

    def test_dictionary_table_and_duplicate_names(self):
        saved = []
        ed = CollectionEditor(self.root, 'Rules', {'colour': 'color'}, saved.append, context='style')
        ed.add()
        child = next(w for w in ed.win.winfo_children() if hasattr(w, 'form_editor'))
        form = child.form_editor
        form.controls['name'].variable.set('colour')
        form.controls['value'].variable.set('new')
        self.assertFalse(form.apply())
        self.assertIn('already exists', form.error.get())
        form.controls['name'].variable.set('theatre')
        self.assertTrue(form.apply())
        self.assertTrue(ed.apply())
        self.assertEqual(saved[0], {'colour': 'color', 'theatre': 'new'})

    def test_preferences_preserve_hidden_state(self):
        from openvoice.gui_workflows import preferences
        saved = []
        cfg = {'language': 'en', 'font_size': 12, 'recent_files': [{'path': '/example'}], 'welcome_seen': True, 'new_future_setting': {'a': 1}}
        win = preferences(self.root, cfg, saved.append)
        win.form_editor.controls['font_size'].variable.set('16')
        self.assertTrue(win.form_editor.apply())
        self.assertEqual(saved[0]['font_size'], 16)
        self.assertEqual(saved[0]['recent_files'], cfg['recent_files'])
        self.assertTrue(saved[0]['welcome_seen'])
        self.assertEqual(saved[0]['new_future_setting'], {'a': 1})

    def test_panel_drawing_normalizes_to_original_image(self):
        from types import SimpleNamespace
        from PIL import Image
        from openvoice.gui_workflows import PanelTour
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'page.png'
            Image.new('RGB', (600, 900), 'white').save(path)
            saved = []
            ed = PanelTour(self.root, path, saved.append)
            self.root.update()
            x, y, w, h = ed.bounds
            ed.press(SimpleNamespace(x=x + w * .1, y=y + h * .2))
            ed.release(SimpleNamespace(x=x + w * .8, y=y + h * .9))
            ed.apply()
            self.assertAlmostEqual(saved[0]['panels'][0][0], .1)
            self.assertAlmostEqual(saved[0]['panels'][0][3], .9)

    def test_readable_report_filter_and_copy(self):
        from openvoice.gui_forms import show_report
        win = show_report(self.root, 'Check', {'voices': [{'name': 'বাংলা', 'installed': True}], 'errors': []})
        self.root.update()
        self.assertTrue(win.report_tree.get_children())

    def test_reset_does_not_leave_wheel_callbacks_on_destroyed_canvas(self):
        form = FormEditor(self.root, 'Settings', {'start': 0., 'end': 2.}, lambda d: None)
        for _ in range(3):
            form.reset()
        self.root.update()
        form.win.event_generate('<MouseWheel>', delta=-120)
        self.root.update()


class NarrationIntegration(unittest.TestCase):
    def test_visual_plan_renders_real_audio_with_pause(self):
        import shutil
        if not shutil.which('ffmpeg'):
            self.skipTest('FFmpeg is unavailable')
        from test_studio_workflows import Demo
        from openvoice.performance import render_score
        spec = score_from_text('First passage.\n\nSecond passage.')
        spec['scenes'][0]['passages'].insert(1, {'pause': .25})
        spec['scenes'][0]['passages'][0]['emotion'] = 'calm'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'narration.oamscore'
            path.write_text(json.dumps(spec), encoding='utf-8')
            with patch('openvoice.performance.get_engine', return_value=Demo()):
                out = render_score(path, Path(folder) / 'book.wav')
            with wave.open(str(out)) as audio:
                self.assertGreater(audio.getnframes() / audio.getframerate(), .4)


class CompleteDesktop(unittest.TestCase):
    def test_desktop_workflows_and_project_creation(self):
        import tkinter as tk
        try:
            probe=tk.Tk();probe.destroy()
        except tk.TclError:
            self.skipTest('Desktop display is unavailable')
        from openvoice import gui,desktop_prefs
        from openvoice.gui_workflows import TaskHub,current_cast,queue_job
        from openvoice.project_archive import load_project
        failures=[]
        def ready(app):
            app.root.report_callback_exception=lambda typ,value,tb:failures.append(value)
            def exercise():
                try:
                    self.assertEqual(app._get_text(),'')
                    home=app.studio.home()
                    hub=home.task_hub
                    self.assertGreaterEqual(len(hub.actions),47)
                    hub.search.set('Narration planner')
                    self.assertEqual(len(hub.visible),1)
                    home.destroy()
                    app.voice_var.set('selected-main-voice')
                    app.rate_var.set(3)
                    cast=current_cast(app)
                    self.assertEqual(cast['Narrator']['voice'],'selected-main-voice')
                    self.assertEqual(cast['Narrator']['rate'],3)
                    app._replace_text('First passage.\n\nSecond passage.')
                    desk=app.studio.score()
                    desk.add_pause()
                    form=next(w.form_editor for w in desk.win.winfo_children() if hasattr(w,'form_editor'))
                    form.controls['pause'].variable.set('.35')
                    self.assertTrue(form.apply())
                    self.assertEqual(desk.rows()[-1]['pause'],.35)
                    path=Path(tmp)/'narration.oamscore'
                    with patch('openvoice.gui_workflows.filedialog.asksaveasfilename',return_value=str(path)):
                        self.assertTrue(desk.save())
                    self.assertEqual(json.loads(path.read_text())['profiles']['Narrator']['voice'],'selected-main-voice')
                    desk.win.destroy()
                    win=app.studio.preferences()
                    form=win.form_editor
                    self.assertEqual(len(form.notebook.tabs()),5)
                    form.controls['font_size'].variable.set('15')
                    form.controls['gpu_mode'].variable.set('Use processor only')
                    self.assertTrue(form.apply(),form.error.get())
                    self.assertEqual(app.font_size,15)
                    self.assertEqual(desktop_prefs.read()['gpu_mode'],'cpu')
                    win=app.studio.caption_design()
                    win.form_editor.controls['safe_margin'].variable.set('.12')
                    self.assertTrue(win.form_editor.apply())
                    self.assertEqual(app.video_options['safe_margin'],.12)
                    wizard=app.project_wizard()
                    form=wizard.form_editor
                    form.controls['title'].variable.set('My first audiobook')
                    project=Path(tmp)/'new-book.oamproj'
                    form.controls['project_file'].variable.set(str(project))
                    form.controls['open_project'].variable.set(False)
                    self.assertTrue(form.apply(),form.error.get())
                    with tempfile.TemporaryDirectory() as unpack:
                        data=load_project(project,unpack)
                        self.assertEqual(data.settings['production']['title'],'My first audiobook')
                    self.assertTrue(desktop_prefs.read()['recent_files'])
                    with patch('tkinter.messagebox.askyesnocancel',return_value=None):
                        app.close()
                    self.assertTrue(app.root.winfo_exists())
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    app._saved_text=app._get_text()
                    app.close()
            app.root.after(400,exercise)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'OPENMUKTI_NEURAL_HOME':str(Path(tmp)/'engines'),'OPENMUKTI_GPU_MODE':'cpu'}):
            desktop_prefs.write(show_home_on_start=False,welcome_seen=True)
            with patch('openvoice.gui.fetch_catalog',return_value=[]):
                self.assertEqual(gui.main(on_ready=ready),0)
        if failures:
            raise failures[0]


if __name__ == '__main__':
    unittest.main()
