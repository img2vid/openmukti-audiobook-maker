import json
import tempfile
import unittest
from pathlib import Path

from openvoice.cli import main


class NewCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.book = self.root / 'book.txt'
        self.book.write_text('Chapter 1\nIt was a bright cold day in April.\n\n'
                             'Chapter 2\nThe clocks were striking thirteen.\n', encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *argv):
        return main(list(argv))

    def test_library_roundtrip(self):
        index = self.root / 'lib.json'
        self.assertEqual(self.run_cli('library', 'add', str(self.book), '--index', str(index),
                                      '--category', 'fiction', '--tags', 'classic,dystopia'), 0)
        self.assertEqual(self.run_cli('library', 'favorite', 'book', '--index', str(index)), 0)
        self.assertEqual(self.run_cli('library', 'note', 'book', '--index', str(index),
                                      '--note', 'Re-record chapter 2'), 0)
        self.assertEqual(self.run_cli('library', 'bookmark', 'book', 'Fix intro',
                                      '--index', str(index)), 0)
        self.assertEqual(self.run_cli('library', 'search', '--index', str(index),
                                      '--query', 'dystopia'), 0)
        self.assertEqual(self.run_cli('library', 'health', str(self.book)), 0)
        self.assertEqual(self.run_cli('library', 'duplicates', '--index', str(index)), 0)
        data = json.loads(index.read_text())
        entry = data['projects'][0]
        self.assertEqual(entry['category'], 'fiction')
        self.assertTrue(entry['favorite'])
        self.assertEqual(entry['bookmarks'][0]['name'], 'Fix intro')
        self.assertEqual(self.run_cli('library', 'rename', '--index', str(index),
                                      '--pattern', 'book', '--replacement', 'novel',
                                      '--dry-run'), 0)

    def test_chapters_commands(self):
        self.assertEqual(self.run_cli('chapters', 'detect', '-f', str(self.book)), 0)
        self.assertEqual(self.run_cli('chapters', 'toc', '-f', str(self.book)), 0)
        self.assertEqual(self.run_cli('chapters', 'estimate', '-f', str(self.book)), 0)
        status = self.root / 'status.json'
        self.assertEqual(self.run_cli('chapters', 'set-status', '--status-file', str(status),
                                      '--chapter', 'Chapter 1', '--status', 'completed'), 0)
        self.assertEqual(self.run_cli('chapters', 'status-summary', '--status-file', str(status)), 0)
        summary = json.loads(status.read_text())
        self.assertEqual(summary['chapters']['Chapter 1'], 'completed')

    def test_proofread_commands(self):
        for action in ('names', 'dialogue', 'ocr-artifacts', 'readability', 'terminology',
                       'pronunciation-audit'):
            self.assertEqual(self.run_cli('proofread', action, '-f', str(self.book)), 0, action)

    def test_transform_speech_tools_registered(self):
        out = self.root / 'spoken.txt'
        self.assertEqual(self.run_cli('transform', '-f', str(self.book), '-w', str(out),
                                      '--apply', 'expand-abbreviations', '--apply', 'speak-numbers'), 0)
        self.assertIn('thirteen', out.read_text())

    def test_captions_ass(self):
        cues = self.root / 'cues.json'
        cues.write_text(json.dumps([{'start': 0.0, 'end': 1.0, 'text': 'Hi'}]))
        target = self.root / 'out.ass'
        self.assertEqual(self.run_cli('captions', str(cues), str(target)), 0)
        self.assertIn('Dialogue: 0,0:00:00.00,0:00:01.00', target.read_text())

    def test_name_files(self):
        self.assertEqual(self.run_cli('name-files', '{title}-{number:02}-{chapter}',
                                      'Start', 'End', '--title', 'Book'), 0)

    def test_release_notes_attribution(self):
        changes = self.root / 'changes.json'
        changes.write_text(json.dumps([{'kind': 'added', 'text': 'Library command'}]))
        notes = self.root / 'notes.md'
        self.assertEqual(self.run_cli('release-notes', str(changes), '--version', '1.0.29',
                                      '-w', str(notes)), 0)
        self.assertIn('Library command', notes.read_text())
        assets = self.root / 'assets.json'
        assets.write_text(json.dumps([{'name': 'Voice', 'type': 'voice',
                                       'attribution': 'By Example'}]))
        credits = self.root / 'credits.md'
        self.assertEqual(self.run_cli('attribution', str(assets), '--project', 'Book',
                                      '-w', str(credits)), 0)
        self.assertIn('By Example', credits.read_text())

    def test_transcript(self):
        target = self.root / 'transcript.pdf'
        self.assertEqual(self.run_cli('transcript', '-f', str(self.book), '-w', str(target)), 0)
        self.assertTrue(target.read_bytes().startswith(b'%PDF-1.4'))

    def test_production_commands(self):
        board = self.root / 'board.json'
        self.assertEqual(self.run_cli('production', 'stage', '--board', str(board),
                                      '--chapter', 'Chapter 1', '--stage', 'narrated'), 0)
        self.assertEqual(self.run_cli('production', 'checkpoint', '--board', str(board),
                                      '--chapter', 'Chapter 1', '--checkpoint', 'listen',
                                      '--passed'), 0)
        self.assertEqual(self.run_cli('production', 'approve', '--board', str(board),
                                      '--chapter', 'Chapter 1'), 0)
        self.assertEqual(self.run_cli('production', 'dashboard', '--board', str(board)), 0)
        self.assertEqual(self.run_cli('production', 'estimate', '-f', str(self.book)), 0)
        self.assertEqual(self.run_cli('production', 'forecast', '-f', str(self.book),
                                      '--format', 'mp3'), 0)
        log = self.root / 'prod.jsonl'
        self.assertEqual(self.run_cli('production', 'log', '--log-file', str(log),
                                      '--event', 'render-start', '--detail', 'chapter=One'), 0)
        self.assertEqual(self.run_cli('production', 'log-summary', '--log-file', str(log)), 0)


if __name__ == '__main__':
    unittest.main()
