"""Regression coverage for character discovery, tags, and language workflow."""
import re
import tempfile
import unittest
from pathlib import Path

from openvoice.dialogue_analysis import analyze_dialogue, human_names
from openvoice.character_voices import (
    CharacterProfile, VoiceProject, auto_profiles, detect_characters,
    detect_language, detected_languages, parse_passages,
)


class DialogueAnalysisTests(unittest.TestCase):
    def test_bundled_names_are_multilingual_and_not_a_required_dictionary(self):
        names=human_names()
        self.assertGreaterEqual(len(names), 50000)
        self.assertIn('alice',names)
        self.assertIn('aarav',names)
        self.assertIn('lúcia', names)
        self.assertIn('Zeraphine', detect_characters('Zeraphine whispered, "Go."'))

    def test_speaker_is_assigned_on_both_sides_of_quotes(self):
        text='"Good morning," Alice said. "How are you?" Bob asked.'
        result=analyze_dialogue(text)
        self.assertEqual([q.speaker for q in result.quotations],['Alice','Bob'])
        self.assertIn('[Alice] "Good morning," [Narrator]',result.tagged_text)
        self.assertIn('[Bob] "How are you?" [Narrator]',result.tagged_text)

    def test_separated_dialogue_and_narration_preserve_original(self):
        source='The road was quiet. Alice called, “Hello!” Bob replied, “Hi.” Then rain fell.'
        project=auto_profiles(source)
        stripped=re.sub(r'\[(?:Narrator|Alice|Bob)\] ?', '', project.script)
        self.assertEqual(' '.join(stripped.split()), ' '.join(source.split()))
        passages=parse_passages(project.script,project.profiles)
        self.assertEqual([p.speaker for p in passages],['Narrator','Alice','Narrator','Bob','Narrator'])
        self.assertIn('Then rain fell.',passages[-1].text)
        self.assertEqual(analyze_dialogue(project.script).tagged_text,project.script)

    def test_interrupted_dialogue_and_nested_curly_punctuation(self):
        source='“Hi,” Alice said, “the child yelled ‘Go!’ just now.”'
        a=analyze_dialogue(source)
        self.assertEqual(len(a.quotations),2)
        self.assertEqual([q.speaker for q in a.quotations],['Alice','Alice'])

    def test_cjk_and_dash_form(self):
        self.assertIn('[花子] 「こんにちは」',analyze_dialogue('「こんにちは」と花子は言った。').tagged_text)
        script='— Leave now! shouted Elara\n— I refuse! answered Kolven'
        a=analyze_dialogue(script)
        self.assertEqual([q.speaker for q in a.quotations],['Elara','Kolven'])
        self.assertIn('[Narrator] shouted Elara',a.tagged_text)

    def test_uncertain_quotes_stay_narrated(self):
        source='It was a “beautiful” room. “What?” came a distant cry.'
        a=analyze_dialogue(source)
        self.assertEqual(a.tagged_text,source)
        self.assertEqual([q.speaker for q in a.quotations],['Narrator','Narrator'])

    def test_manual_tags_are_not_replaced(self):
        source='[Narrator] It was quiet.\n[Alice] Don’t move.\n[Narrator] The door opened.'
        self.assertEqual(analyze_dialogue(source).tagged_text,source)
        self.assertEqual([p.speaker for p in parse_passages(source,[CharacterProfile('Narrator'),CharacterProfile('Alice')])],['Narrator','Alice','Narrator'])

    def test_character_clues_and_voice_assignments(self):
        src='Alice, a teenage girl, whispered, "Hello." Bob, an elderly man, shouted, "Welcome."'
        p=auto_profiles(src,installed=['en_US-amy-medium','en_US-ryan-medium','de_DE-thorsten-medium'])
        profiles={item.name:item for item in p.profiles}
        self.assertEqual(profiles['Alice'].gender,'Female')
        self.assertEqual(profiles['Alice'].age,'Teen')
        self.assertEqual(profiles['Bob'].age,'Senior')
        self.assertEqual(profiles['Alice'].characteristics,'whispery')
        self.assertEqual(profiles['Bob'].characteristics,'energetic')
        self.assertEqual(profiles['Alice'].voice,'en_US-ryan-medium' if profiles['Narrator'].voice=='en_US-amy-medium' else 'en_US-amy-medium')
        self.assertNotEqual(profiles['Alice'].voice,'de_DE-thorsten-medium')

    def test_language_multi_script_and_project_backward_compatibility(self):
        text='This is an English text that tells a story.\nこんにちは、みんな。'
        langs=dict(detected_languages(text))
        self.assertIn('en',langs)
        self.assertIn('ja',langs)
        self.assertEqual(detect_language('こんにちは、世界')[0],'ja')
        self.assertEqual(detect_language('नमस्ते दुनिया')[0],'hi')
        p=auto_profiles('Zeraphine said, "We should leave."')
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'voices.json'
            p.save(target)
            loaded=VoiceProject.load(target)
            self.assertEqual(loaded.script,p.script)
            self.assertEqual(loaded.profiles[1].volume,100)


if __name__=='__main__':
    unittest.main()
