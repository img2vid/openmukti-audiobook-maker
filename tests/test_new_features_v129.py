import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openvoice.project_library import (ProjectLibrary, LibraryEntry, health_check,
                                       read_project_text, Bookmark)
from openvoice.book_structure import (Section, detect_chapters, table_of_contents,
                                      detect_scene_breaks, detect_headers_footers,
                                      remove_page_numbers, estimate_durations,
                                      reorder_sections, split_section, merge_sections,
                                      hierarchy, set_status, completion_summary)
from openvoice.proofreading import (proper_name_consistency, dialogue_punctuation_issues,
                                    ocr_punctuation_report, readability,
                                    terminology_consistency, pronunciation_audit)
from openvoice.narration_text import (expand_abbreviations, number_to_words,
                                      ordinal_to_words, year_to_words, speak_numbers,
                                      speak_dates_times, interpret_pauses)
from openvoice.publishing import (ass_export, render_name, name_chapters, release_notes,
                                  attribution_document, export_transcript,
                                  write_transcript_pdf, transcript_html)
from openvoice.production import (ProductionBoard, ProductionLog, estimate_render_seconds,
                                  forecast_resources)


MANUSCRIPT = """Chapter 1
The rain started before dawn. Elias watched it from the window.

Chapter 2
"Come here," said Maria. "Now."

Chapter Three
Later, the old man returned. Elais was gone.
"""


class ProjectLibraryTests(unittest.TestCase):
    def test_add_search_tags_favorites(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            book = root / 'novel.oamproj'
            book.write_bytes(b'not a real project')
            lib = ProjectLibrary(root / 'library.json')
            lib.add(book, category='fiction', tags=['Fantasy', ' wip '], favorite=True)
            lib.save()
            loaded = ProjectLibrary(root / 'library.json')
            self.assertEqual(len(loaded.entries), 1)
            entry = loaded.entries[0]
            self.assertEqual(entry.tags, ['fantasy', 'wip'])
            self.assertTrue(entry.favorite)
            self.assertEqual(loaded.search('fantasy')[0].name, 'novel')
            self.assertEqual(loaded.search(tag='wip')[0].category, 'fiction')
            self.assertEqual(loaded.search(favorites_only=True)[0].name, 'novel')
            self.assertEqual(loaded.categories(), ['fiction'])
            self.assertEqual(loaded.all_tags(), ['fantasy', 'wip'])

    def test_reject_duplicate_and_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            book = root / 'a.txt'
            book.write_text('x')
            lib = ProjectLibrary(root / 'lib.json')
            lib.add(book)
            with self.assertRaises(ValueError):
                lib.add(book)
            with self.assertRaises(FileNotFoundError):
                lib.add(root / 'missing.txt')
            with self.assertRaises(ValueError):
                lib.find('nothing')

    def test_notes_bookmarks_and_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('draft-one.txt', 'draft-two.txt'):
                (root / name).write_text(name)
            lib = ProjectLibrary(root / 'lib.json')
            lib.add(root / 'draft-one.txt')
            lib.add(root / 'draft-two.txt')
            lib.set_notes('draft-one', 'Record chapter 3 again')
            lib.add_bookmark('draft-one', 'Fix intro', note='too fast', position=120)
            changes = lib.batch_rename('draft', 'book')
            self.assertEqual(changes, [('draft-one', 'book-one'), ('draft-two', 'book-two')])
            self.assertEqual(lib.find('book-one').notes, 'Record chapter 3 again')
            self.assertEqual(lib.find('book-one').bookmarks[0].position, 120)
            preview = lib.batch_rename('book', 'volume', dry_run=True)
            self.assertEqual(preview, [('book-one', 'volume-one'), ('book-two', 'volume-two')])
            self.assertEqual(lib.find('book-one').name, 'book-one')  # dry run changed nothing
            lib.save()
            reloaded = ProjectLibrary(root / 'lib.json')
            self.assertEqual(reloaded.find('book-two').name, 'book-two')

    def test_rename_collision_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a-x.txt').write_text('1')
            (root / 'a-y.txt').write_text('2')
            lib = ProjectLibrary(root / 'lib.json')
            lib.add(root / 'a-x.txt', name='keep')
            lib.add(root / 'a-y.txt', name='change-me')
            with self.assertRaises(ValueError):
                lib.batch_rename('change-me', 'keep')

    def test_duplicates_storage_health(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'one.txt').write_bytes(b'identical')
            (root / 'two.txt').write_bytes(b'identical')
            (root / 'three.txt').write_bytes(b'different')
            (root / 'audio.wav').write_bytes(b'RIFF' + b'\0' * 100)
            lib = ProjectLibrary(root / 'lib.json')
            for name in ('one.txt', 'two.txt', 'three.txt'):
                lib.add(root / name)
            groups = lib.duplicates()
            self.assertEqual(len(groups), 1)
            self.assertEqual({e.name for e in groups[0]}, {'one', 'two'})
            storage = lib.storage_analysis(root)
            self.assertGreater(storage['bytes_by_group']['audio'], 0)
            self.assertGreater(storage['bytes_by_group']['text'], 0)
            report = health_check(root / 'three.txt')
            self.assertTrue(report['healthy'])
            self.assertFalse(health_check(root / 'gone.txt')['healthy'])

    def test_health_check_oamproj(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / 'book.oamproj'
            manifest = {'format': 'openmukti-project', 'version': 1, 'text': 'Hello world',
                        'resources': {}}
            with zipfile.ZipFile(project, 'w') as archive:
                archive.writestr('project.json', json.dumps(manifest))
            self.assertTrue(health_check(project)['healthy'])
            self.assertEqual(read_project_text(project), 'Hello world')
            bad = Path(temp) / 'bad.oamproj'
            bad.write_bytes(b'not a zip')
            self.assertFalse(health_check(bad)['healthy'])


class BookStructureTests(unittest.TestCase):
    def test_detect_keyword_and_numbered(self):
        sections = detect_chapters(MANUSCRIPT)
        titles = [s.title for s in sections]
        self.assertEqual(titles, ['Chapter 1', 'Chapter 2', 'Chapter Three'])
        self.assertIn('rain', sections[0].text)

    def test_markdown_and_custom_rules(self):
        text = '# Part I\n\nWords.\n\n## Day one\n\nMore words here.\n'
        sections = detect_chapters(text)
        self.assertEqual([s.title for s in sections], ['Part I', 'Day one'])
        self.assertEqual(sections[1].level, 3)
        custom = detect_chapters('CONTINUED\n\nBody text.\n', custom_rules=[r'(CONTINUED)'])
        self.assertEqual(custom[0].title, 'CONTINUED')
        with self.assertRaises(ValueError):
            detect_chapters('x', custom_rules=['(['])

    def test_toc_hierarchy_and_estimate(self):
        sections = detect_chapters(MANUSCRIPT)
        toc = table_of_contents(sections)
        self.assertIn('Chapter 1', toc)
        tree = hierarchy([Section('Part I', 'x', level=1), Section('Ch 1', 'y', level=2)])
        self.assertEqual(tree[0]['children'][0]['section'].title, 'Ch 1')
        estimate = estimate_durations(sections, wpm=160)
        self.assertGreater(estimate['total_estimated_seconds'], 0)
        self.assertEqual(len(estimate['sections']), 3)

    def test_scene_breaks_headers_page_numbers(self):
        text = 'Page one text.\n\fPage two text.\n\fPage three text.\n'
        breaks = detect_scene_breaks('First scene.\n\n* * *\n\nSecond scene.\n')
        self.assertEqual(len(breaks), 1)
        headered = 'My Book\nText a.\n\fMy Book\nText b.\n\fMy Book\nText c.\n'
        found = detect_headers_footers(headered)
        self.assertEqual(found['pages'], 3)
        self.assertTrue(found['headers'])
        cleaned = remove_page_numbers('Text.\n\n42\n\nMore text.\n\nPage 43\n\nEnd.')
        self.assertNotIn('\n42\n', cleaned)
        self.assertIn('End.', cleaned)

    def test_reorder_split_merge_status(self):
        sections = detect_chapters(MANUSCRIPT)
        reordered = reorder_sections(sections, [3, 1, 2])
        self.assertEqual(reordered[0].title, 'Chapter Three')
        with self.assertRaises(ValueError):
            reorder_sections(sections, [1, 1, 2])
        first, second = split_section(sections[0], 10, second_title='Part two')
        self.assertEqual(second.title, 'Part two')
        merged = merge_sections(first, second)
        self.assertIn('rain', merged.text)
        with tempfile.TemporaryDirectory() as temp:
            status_file = Path(temp) / 'status.json'
            set_status(status_file, 'Chapter 1', 'completed')
            summary = completion_summary(status_file)
            self.assertEqual(summary['completed'], 1)
            with self.assertRaises(ValueError):
                set_status(status_file, 'Chapter 2', 'bogus')


class ProofreadingTests(unittest.TestCase):
    def test_proper_name_variants(self):
        text = ('Elias went home. Elias slept. ' * 3) + 'Elais returned. Elais spoke.'
        clusters = proper_name_consistency(text)
        self.assertTrue(any({v['name'] for v in c['variants']} == {'Elias', 'Elais'} for c in clusters))
        self.assertEqual(clusters[0]['suggestion'], 'Elias')

    def test_dialogue_punctuation(self):
        issues = dialogue_punctuation_issues('"Come here," said Maria.\n\n"Unclosed quote\n\nFine.')
        kinds = [i['issue'] for i in issues]
        self.assertTrue(any('unbalanced' in k for k in kinds))

    def test_ocr_report_and_readability(self):
        findings = ocr_punctuation_report('Word , another word. He1lo world. Test!!!')
        labels = [f['issue'] for f in findings]
        self.assertIn('space before punctuation', labels)
        self.assertIn('digit inside a word', labels)
        scores = readability('The cat sat on the mat. It was a very sunny day indeed.')
        self.assertGreater(scores['flesch_reading_ease'], 50)
        self.assertEqual(scores['sentences'], 2)
        with self.assertRaises(ValueError):
            readability('')

    def test_terminology_and_pronunciation_audit(self):
        chapters = {'One': 'The Order of the Moon met. The Order voted. The Order left.',
                    'Two': 'the order was late. the order argued. the order slept.'}
        report = terminology_consistency(chapters)
        self.assertTrue(any(r['term'] == 'the order' or 'order' in r['term'] for r in report))
        audit = pronunciation_audit('Supercalifragilisticexpialidocious appeared twice. ' * 2,
                                    override_words={'supercalifragilisticexpialidocious'})
        self.assertEqual(audit['unique_covered'], 1)
        self.assertEqual(audit['unique_difficult'], 0)


class NarrationTextTests(unittest.TestCase):
    def test_abbreviations(self):
        self.assertEqual(expand_abbreviations('Dr. Smith arrived.'), 'Doctor Smith arrived.')
        self.assertEqual(expand_abbreviations('etc.'), 'et cetera')
        self.assertEqual(expand_abbreviations('mr. darcy'), 'Mister darcy')
        custom = expand_abbreviations('Use OTP here.', rules={'OTP': 'one time password'})
        self.assertIn('one time password', custom)

    def test_numbers(self):
        self.assertEqual(number_to_words(0), 'zero')
        self.assertEqual(number_to_words(42), 'forty-two')
        self.assertEqual(number_to_words(115), 'one hundred fifteen')
        self.assertEqual(number_to_words(1000001), 'one million one')
        self.assertEqual(ordinal_to_words(1), 'first')
        self.assertEqual(ordinal_to_words(21), 'twenty-first')
        self.assertEqual(ordinal_to_words(100), 'one hundredth')
        self.assertEqual(year_to_words(1999), 'nineteen ninety-nine')
        self.assertEqual(year_to_words(2007), 'two thousand seven')
        self.assertEqual(year_to_words(2026), 'twenty twenty-six')

    def test_speak_numbers_modes(self):
        self.assertIn('forty-two', speak_numbers('Room 42 ready.'))
        self.assertIn('four two', speak_numbers('Room 42 ready.', mode='digits'))
        self.assertIn('first', speak_numbers('She came 1st.', mode='ordinal-aware'))
        self.assertIn('five dollars', speak_numbers('It costs $5.'))
        self.assertIn('twenty percent', speak_numbers('About 20% left.'))
        self.assertIn('three point one four', speak_numbers('Pi is 3.14.'))
        self.assertIn('nineteen eighty-four', speak_numbers('Written in 1984.'))
        with self.assertRaises(ValueError):
            speak_numbers('x', mode='nonsense')

    def test_dates_times(self):
        self.assertEqual(speak_dates_times('Born 2026-11-04.'), 'Born the fourth of November, twenty twenty-six.')
        self.assertIn('the fourth of November', speak_dates_times('On 11/4/2026.'))
        self.assertIn('the fourth of November', speak_dates_times('On 4/11/2026.', day_first=True))
        self.assertIn('two thirty P M', speak_dates_times('At 2:30 PM.'))
        self.assertIn("seven o'clock", speak_dates_times('At 7:00.'))

    def test_pauses(self):
        tagged = interpret_pauses('Wait... maybe—no.')
        self.assertIn('[p:0.7s]', tagged)
        self.assertIn('[p:0.4s]', tagged)
        plain = interpret_pauses('Wait... maybe—no.', style='punctuation')
        self.assertNotIn('—', plain)
        self.assertEqual(interpret_pauses('Keep... this.', style='keep'), 'Keep... this.')
        with self.assertRaises(ValueError):
            interpret_pauses('x', style='wild')


class PublishingTests(unittest.TestCase):
    def _cues(self, folder: Path) -> Path:
        cues = folder / 'cues.json'
        cues.write_text(json.dumps([{'start': 0.0, 'end': 1.5, 'text': 'Hello'},
                                    {'start': 1.5, 'end': 3.0, 'text': 'World'}]))
        return cues

    def test_ass_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = ass_export(self._cues(root), root / 'subs.ass', font='Georgia', size=40)
            content = out.read_text(encoding='utf-8')
            self.assertIn('[V4+ Styles]', content)
            self.assertIn('Dialogue: 0,0:00:00.00,0:00:01.50,Default,,0,0,0,,Hello', content)
            self.assertIn('Georgia,40', content)
            with self.assertRaises(ValueError):
                ass_export(self._cues(root), root / 'subs.srt')
            with self.assertRaises(ValueError):
                ass_export(self._cues(root), root / 'x.ass', primary='red')

    def test_naming_rules(self):
        self.assertEqual(render_name('{title} - {number:03} - {chapter}',
                                     {'title': 'My Book', 'number': 7, 'chapter': 'The End'}),
                         'My Book - 007 - The End')
        with self.assertRaises(ValueError):
            render_name('{unknown}', {})
        with self.assertRaises(ValueError):
            render_name('   ', {'title': 'x'})
        names = name_chapters('{chapter}', ['Same', 'Same', 'Other'], {})
        self.assertEqual(names, ['Same', 'Same-2', 'Other'])
        safe = render_name('{title}', {'title': 'a/b:c*d'})
        self.assertNotIn('/', safe)

    def test_release_notes_and_attribution(self):
        notes = release_notes('1.0.29', [{'kind': 'added', 'text': 'ASS export'},
                                         {'kind': 'fixed', 'text': 'Chapter 3 timing',
                                          'chapters': ['Chapter 3']}])
        self.assertIn('## Added', notes)
        self.assertIn('(chapters: Chapter 3)', notes)
        with self.assertRaises(ValueError):
            release_notes('1', [{'kind': 'weird', 'text': 'x'}])
        credits = attribution_document('My Book', [
            {'name': 'Calm Voice', 'type': 'voice', 'license': 'CC-BY-4.0',
             'attribution': 'Voice by Example Project'},
            {'name': 'Rain loop', 'type': 'sound', 'source': 'local'}], author='A. Writer')
        self.assertIn('Required attributions', credits)
        self.assertIn('Voice by Example Project', credits)
        self.assertIn('Rain loop', credits)

    def test_transcript_txt_html_pdf(self):
        chapters = [('Chapter 1', 'First paragraph here.\n\nSecond paragraph follows.')]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            txt = export_transcript(root / 'book.txt', 'My Book', chapters, author='Me')
            self.assertIn('CHAPTER 1', txt.read_text())
            html = export_transcript(root / 'book.html', 'My Book', chapters)
            self.assertIn('<h2>Chapter 1</h2>', html.read_text())
            pdf = write_transcript_pdf(root / 'book.pdf', 'My Book', chapters, author='Me')
            data = pdf.read_bytes()
            self.assertTrue(data.startswith(b'%PDF-1.4'))
            self.assertIn(b'/Helvetica', data)
            self.assertTrue(data.rstrip().endswith(b'%%EOF'))
            # Long manuscripts must paginate rather than overflow one page.
            long_chapters = [('Long', '\n\n'.join(f'Paragraph {i} with several words in it.'
                                                  for i in range(200)))]
            big = write_transcript_pdf(root / 'big.pdf', 'Big', long_chapters)
            self.assertGreater(big.read_bytes().count(b'/Type /Page '), 2)
            with self.assertRaises(ValueError):
                export_transcript(root / 'book.docx', 'My Book', chapters)


class ProductionTests(unittest.TestCase):
    def test_board_stages_checkpoints_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            board = ProductionBoard(Path(temp) / 'board.json')
            board.set_stage('Chapter 1', 'narrated')
            board.set_checkpoint('Chapter 1', 'listen-through', True)
            board.approve('Chapter 1')
            board.set_stage('Chapter 2', 'imported')
            board.save()
            loaded = ProductionBoard(Path(temp) / 'board.json')
            self.assertTrue(loaded.chapters['Chapter 1']['approved'])
            dash = loaded.dashboard()
            self.assertEqual(dash['total_chapters'], 2)
            self.assertEqual(dash['chapters_by_stage']['narrated'], 1)
            board.set_checkpoint('Chapter 2', 'audio-quality', False)
            with self.assertRaises(ValueError):
                board.approve('Chapter 2')
            with self.assertRaises(ValueError):
                board.set_stage('Chapter 3', 'printed')

    def test_estimates_and_forecast(self):
        estimate = estimate_render_seconds(8000, realtime_factor=0.5)
        self.assertEqual(estimate['estimated_audio_seconds'], 3000.0)
        self.assertGreater(estimate['estimated_render_seconds'], 1400)
        with self.assertRaises(ValueError):
            estimate_render_seconds(-1)
        forecast = forecast_resources([{'title': 'A', 'words': 1600}], audio_format='mp3')
        self.assertEqual(forecast['chapters'][0]['estimated_bytes'], 600 * 16000)
        with self.assertRaises(ValueError):
            forecast_resources([], audio_format='xyz')

    def test_production_log(self):
        with tempfile.TemporaryDirectory() as temp:
            log = ProductionLog(Path(temp) / 'log.jsonl', redact=['path', 'user'])
            log.record('render-start', chapter='One', path='/home/alice/secret.wav')
            log.record('render-failed', level='error', reason='engine crashed')
            rows = log.entries()
            self.assertEqual(rows[0]['path'], '[redacted]')
            self.assertEqual(len(log.entries(level='error')), 1)
            summary = log.summary()
            self.assertEqual(summary['error'], 1)
            self.assertEqual(summary['total'], 2)
            with self.assertRaises(ValueError):
                log.record('x', level='shout')


if __name__ == '__main__':
    unittest.main()
