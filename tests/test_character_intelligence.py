"""Integration regressions for identities, discourse, inference and persistence."""

import gzip
import json
import re
import tempfile
import unittest
from pathlib import Path

from openvoice.dialogue_analysis import analyze_dialogue, human_names
from openvoice.character_voices import (
    CharacterProfile,
    VoiceProject,
    auto_profiles,
    merge_auto_profiles,
    parse_passages,
    profile_aliases,
    read_name_list,
    PROFILE_FIELDS,
)
from openvoice.voice_design import design_for_profile


def speakers(text, **kwargs):
    return [q.speaker for q in analyze_dialogue(text, **kwargs).quotations]


def profile(text, name):
    return next(p for p in auto_profiles(text).profiles if p.name == name)


class IdentityTests(unittest.TestCase):
    def test_common_noun_repeats_have_one_identity(self):
        text = (
            '"Go," said the old man. "Stop," the old man replied. "Wait," said the man.'
        )
        a = analyze_dialogue(text)
        self.assertEqual(a.characters, ("The old man",))
        self.assertEqual([q.speaker for q in a.quotations], ["The old man"] * 3)

    def test_talking_animal_later_reveal_merges_earlier_speech(self):
        text = '"Sit," the talking dog said. The talking dog was called Rex. "Stay," Rex barked.'
        a = analyze_dialogue(text)
        self.assertEqual(a.characters, ("Rex",))
        self.assertEqual([q.speaker for q in a.quotations], ["Rex", "Rex"])
        self.assertEqual(a.aliases["The talking dog"], "Rex")
        self.assertNotIn("angry", profile(text, "Rex").characteristics)

    def test_reversed_and_regular_appositions(self):
        for source in [
            '"Go," the old man, Elias, said.',
            'Elias, an old man, said, "Go."',
        ]:
            with self.subTest(source=source):
                a = analyze_dialogue(source)
                self.assertEqual(a.characters, ("Elias",))
                self.assertEqual(a.quotations[0].speaker, "Elias")
                self.assertEqual(profile(source, "Elias").age, "Senior")

    def test_descriptive_synonym_alias_survives_future_scans(self):
        first = auto_profiles(
            '"Go," the old man said. "Wait," the elderly gentleman said.'
        )
        p = next(p for p in first.profiles if p.name == "The old man")
        self.assertTrue(any("elderly gentleman" in a for a in p.aliases))
        again = auto_profiles(
            '"Go," the elderly gentleman said.', existing_profiles=first.profiles
        )
        self.assertEqual([p.name for p in again.profiles], ["Narrator", "The old man"])

    def test_identity_revelation_variants(self):
        for identity in [
            "The old man was named Elias.",
            "The old man was called Elias.",
            "The old man was actually Elias.",
            "Elias was the old man.",
        ]:
            with self.subTest(identity=identity):
                a = analyze_dialogue('"Go," the old man said. ' + identity)
                self.assertEqual(a.characters, ("Elias",))
                self.assertEqual(a.quotations[0].speaker, "Elias")

    def test_self_identification_is_attributed_not_merely_a_name_in_quote(self):
        a = analyze_dialogue(
            '"My name is Elias," the old man said. "I met Bob," the old man said.'
        )
        self.assertEqual(a.characters, ("Elias",))
        self.assertEqual([q.speaker for q in a.quotations], ["Elias", "Elias"])

    def test_synonyms_and_additional_name_revelations(self):
        a = analyze_dialogue(
            '"Go," the old man said. "Stop," the elderly gentleman said.'
        )
        self.assertEqual(a.characters, ("The old man",))
        for ending in [
            'The old man named Elias said, "Stay."',
            "The old man’s name was Elias.",
            "The old man introduced himself as Elias.",
        ]:
            with self.subTest(ending=ending):
                b = analyze_dialogue('"Go," the old man said. ' + ending)
                self.assertEqual(b.characters, ("Elias",))
                self.assertTrue(all(q.speaker == "Elias" for q in b.quotations))

    def test_separate_indefinite_people_are_not_arbitrarily_collapsed(self):
        a = analyze_dialogue(
            '"Yes," said a man. "No," said another man. "Maybe," said the man.'
        )
        self.assertEqual(len(a.characters), 2)
        self.assertNotEqual(a.quotations[0].speaker, a.quotations[1].speaker)
        self.assertEqual(a.quotations[2].speaker, "Narrator")

    def test_scene_local_descriptions_and_idempotent_rerun(self):
        source = '"Go," said the old man.\n***\n"Stop," said the old man.'
        first = auto_profiles(source)
        self.assertNotEqual(
            first.analysis.quotations[0].speaker, first.analysis.quotations[1].speaker
        )
        again = auto_profiles(first.script, existing_profiles=first.profiles)
        self.assertEqual(first.script, again.script)
        self.assertEqual(
            [p.name for p in first.profiles], [p.name for p in again.profiles]
        )

    def test_unique_name_forms_merge_but_shared_surnames_do_not(self):
        a = analyze_dialogue(
            '"One," Mr. Bennett said. "Two," John Bennett said. "Three," Bennett said.'
        )
        self.assertEqual(a.characters, ("John Bennett",))
        b = analyze_dialogue(
            '"One," John Smith said. "Two," Mary Smith said. "Three," Smith said.'
        )
        self.assertEqual(len(b.characters), 3)

    def test_names_with_particles_unicode_and_fictional_names(self):
        names = [
            "Juan de la Cruz",
            "Zeraphine",
            "Élodie",
            "李明",
            "राम",
            "Åsa",
            "O’Connor",
        ]
        for name in names:
            with self.subTest(name=name):
                self.assertIn(
                    name, analyze_dialogue(f'{name} said, "Hello."').characters
                )
        self.assertGreaterEqual(len(human_names()), 54000)

    def test_custom_aliases_and_alias_passage_parsing(self):
        profiles = [
            CharacterProfile("Narrator"),
            CharacterProfile("Elias", aliases=["The old man"]),
        ]
        a = analyze_dialogue(
            '"Go," the old man said.',
            known_names=[p.name for p in profiles],
            known_aliases=profile_aliases(profiles),
        )
        self.assertEqual(a.quotations[0].speaker, "Elias")
        self.assertEqual(
            parse_passages("[The old man] Hello.", profiles)[0].speaker, "Elias"
        )

    def test_late_revelation_updates_existing_tags_and_removes_duplicate_profile(self):
        first = auto_profiles('"Go," said the old man.')
        old = next(p for p in first.profiles if p.name != "Narrator")
        old.volume = 64
        old.locked_fields = ["volume"]
        next_source = first.script + " The old man was named Elias."
        second = auto_profiles(next_source, existing_profiles=first.profiles)
        merged = merge_auto_profiles(first.profiles, second.profiles)
        self.assertEqual([p.name for p in merged], ["Narrator", "Elias"])
        self.assertEqual(merged[1].volume, 64)
        self.assertIn("[Elias]", second.script)
        self.assertNotIn("[The old man]", second.script)


class AttributionTests(unittest.TestCase):
    def test_pronouns_match_author_descriptions(self):
        text = 'Alice, a teenage girl, said, "Hello." Bob, an old man, said, "Hi." "Go," she whispered.'
        self.assertEqual(speakers(text), ["Alice", "Bob", "Alice"])

    def test_ambiguous_pronouns_offer_candidates(self):
        a = analyze_dialogue('Alice and Bob entered. "Hello," they said.')
        self.assertEqual(a.quotations[0].speaker, "Narrator")
        self.assertTrue(a.quotations[0].alternatives)

    def test_pronoun_only_identity_stays_consistent_and_can_be_named(self):
        a = analyze_dialogue(
            '"Hello," she said. "Goodbye," she said. Her name was Elara.'
        )
        self.assertEqual(a.characters, ("Elara",))
        self.assertEqual([q.speaker for q in a.quotations], ["Elara", "Elara"])

    def test_action_beats_and_adjacent_turns(self):
        text = (
            'Alice smiled. "Hello."\nBob nodded. "Good day."\n"How are you?"\n"Fine."'
        )
        self.assertEqual(speakers(text), ["Alice", "Bob", "Alice", "Bob"])

    def test_named_direct_address_establishes_reply(self):
        self.assertEqual(
            speakers('Alice said, "Bob, are you ready?"\n"Yes!"'), ["Alice", "Bob"]
        )

    def test_action_does_not_turn_a_lowercase_scare_quote_into_speech(self):
        a = analyze_dialogue("Alice smiled. It was a “beautiful” room.")
        self.assertEqual(a.quotations[0].speaker, "Narrator")

    def test_long_names_remain_control_tags_in_video_and_audio(self):
        from openvoice.animated_video import visible_book_text

        name = "A" + ("b" * 100)
        source = f"[{name}] Hello."
        self.assertEqual(visible_book_text(source), "Hello.")
        self.assertEqual(
            parse_passages(source, [CharacterProfile(name)])[0].speaker, name
        )

    def test_quote_contents_do_not_invent_speakers(self):
        a = analyze_dialogue('Alice said, "Bob said that John shouted."')
        self.assertEqual(a.characters, ("Alice",))
        self.assertEqual(a.quotations[0].speaker, "Alice")

    def test_short_commands_do_not_become_vocative_names(self):
        a = analyze_dialogue('"Go," Alice said. "Stop, now!" Bob said.')
        self.assertEqual(a.characters, ("Alice", "Bob"))

    def test_attribution_does_not_swallow_sentence_periods(self):
        self.assertEqual(
            speakers(
                '"Sit," the talking dog said. The talking dog was called Rex. "Stay," Rex barked.'
            ),
            ["Rex", "Rex"],
        )

    def test_apostrophes_and_nested_quotes(self):
        self.assertEqual(
            speakers("'Don’t go,' Alice said. 'I won't,' Bob replied."),
            ["Alice", "Bob"],
        )
        self.assertEqual(speakers("“She said ‘Go!’ yesterday,” Alice said."), ["Alice"])

    def test_multiline_speech_and_attribution_lead(self):
        a = analyze_dialogue("Alice said, “First paragraph.\n\n“Second paragraph.”")
        self.assertEqual(len(a.quotations), 1)
        self.assertEqual(a.quotations[0].speaker, "Alice")
        self.assertEqual(speakers('Alice said:\n"Hello."'), ["Alice"])

    def test_cjk_hindi_and_cyrillic(self):
        self.assertEqual(
            speakers("「こんにちは」と花子は言った。「你好」小明说。"), ["花子", "小明"]
        )
        self.assertEqual(speakers("“नमस्ते,” राम ने कहा।"), ["राम"])
        self.assertEqual(speakers("«Привет», Анна сказала."), ["Анна"])

    def test_screenplay_labels_are_not_spoken(self):
        p = auto_profiles("Alice: Hello.\nBob: Welcome.")
        parts = parse_passages(p.script, p.profiles)
        self.assertEqual(
            [(s.speaker, s.text) for s in parts],
            [("Alice", "Hello."), ("Bob", "Welcome.")],
        )

    def test_tags_are_idempotent_and_manual_speaker_wins(self):
        source = '[Bob] "Hello," Alice said.\n[Narrator] Rain fell.'
        a = analyze_dialogue(source)
        self.assertEqual(a.tagged_text, source)
        self.assertEqual(a.quotations[0].speaker, "Bob")

    def test_source_characters_and_quote_offsets_are_preserved(self):
        source = "The room was quiet. “Go,” said the old man.\n— Wait! replied Alice\nAlice: Hello."
        a = analyze_dialogue(source)
        stripped = re.sub(r"\[(?:Narrator|The old man|Alice)\] ?", "", a.tagged_text)
        self.assertEqual(" ".join(stripped.split()), " ".join(source.split()))
        for q in a.quotations:
            self.assertTrue(source[q.start : q.end])


class ProfileInferenceTests(unittest.TestCase):
    SOURCE = 'Elara, a 14-year-old girl, had a high-pitched, quiet voice and a shy, gentle personality. Elara whispered slowly, "We should go." Tor, a 70-year-old man, had a deep voice and a confident personality. Tor boomed quickly, "Stay!"'

    def test_all_controls_are_inferred_with_evidence(self):
        project = auto_profiles(
            self.SOURCE,
            installed=["en_US-f-medium", "en_US-m-medium"],
            voice_metadata={
                "en_US-f-medium": {"gender": "Female"},
                "en_US-m-medium": {"gender": "Male"},
            },
        )
        p = next(p for p in project.profiles if p.name == "Elara")
        self.assertEqual(p.language, "en")
        self.assertEqual(p.voice, "en_US-f-medium")
        self.assertEqual((p.gender, p.age, p.rate, p.pitch), ("Female", "Teen", -2, 3))
        self.assertLess(p.volume, 100)
        self.assertIn("shy", p.characteristics)
        self.assertTrue(0 < p.design_strength <= 100)
        self.assertTrue(all(field in p.inference for field in PROFILE_FIELDS))
        design = design_for_profile(p)
        self.assertNotEqual(design.semitones, 0)

    def test_numeric_and_word_ages_include_12_and_19(self):
        for age, expected in [
            ("12-year-old", "Child"),
            ("thirteen-year-old", "Teen"),
            ("19 years old", "Teen"),
            ("27 years old", "Young adult"),
            ("37-year-old", "Adult"),
            ("aged 55", "Middle aged"),
            ("age 75", "Senior"),
        ]:
            with self.subTest(age=age):
                self.assertEqual(
                    profile(f'Alice was {age}. Alice said, "Hello."', "Alice").age,
                    expected,
                )

    def test_other_characters_and_quoted_descriptions_do_not_leak(self):
        p = profile(
            'Alice saw an old man. Alice said, "You are an elderly man with a gruff voice."',
            "Alice",
        )
        self.assertEqual(
            (p.age, p.gender, p.characteristics),
            ("Unspecified", "Unspecified", "natural"),
        )

    def test_negation_and_conflicts_are_not_asserted(self):
        p = profile('Alice was not angry. Alice said, "I am not an old man."', "Alice")
        self.assertEqual(
            (p.age, p.gender, p.characteristics),
            ("Unspecified", "Unspecified", "natural"),
        )
        p = profile('Alice was a man. Alice was a woman. Alice said, "Hello."', "Alice")
        self.assertEqual(p.gender, "Unspecified")

    def test_no_name_based_demographic_guess(self):
        p = profile('Alice said, "Hello."', "Alice")
        self.assertEqual(
            (p.age, p.gender, p.design_strength), ("Unspecified", "Unspecified", 0)
        )

    def test_narrator_is_neutral_and_not_given_character_demographics(self):
        p = auto_profiles(self.SOURCE).profiles[0]
        self.assertEqual(p.name, "Narrator")
        self.assertEqual(
            (p.gender, p.age, p.characteristics, p.design_strength),
            ("Unspecified", "Unspecified", "natural", 0),
        )

    def test_unknown_language_does_not_assign_a_wrong_language_model(self):
        p = auto_profiles("花子: こんにちは。", installed=["en_US-amy-medium"])
        self.assertEqual(next(p for p in p.profiles if p.name == "花子").voice, "")

    def test_model_path_and_explicit_local_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "unconventional.onnx"
            path.write_bytes(b"model fixture")
            Path(str(path) + ".json").write_text(
                json.dumps(
                    {"language": {"code": "en_US"}, "openmukti": {"gender": "Female"}}
                )
            )
            p = auto_profiles('Alice, a girl, said, "Hello."', installed=[str(path)])
            self.assertEqual(
                next(p for p in p.profiles if p.name == "Alice").voice, str(path)
            )

    def test_manual_fields_survive_and_automatic_fields_refresh(self):
        first = auto_profiles('Alice said, "Hello."')
        old = next(p for p in first.profiles if p.name == "Alice")
        old.pitch = 7
        old.locked_fields = ["pitch"]
        proposal = auto_profiles(
            'Alice, a 14-year-old girl, whispered slowly, "Hello."',
            existing_profiles=first.profiles,
        )
        merged = merge_auto_profiles(first.profiles, proposal.profiles)
        p = next(p for p in merged if p.name == "Alice")
        self.assertEqual(p.pitch, 7)
        self.assertEqual(
            (p.age, p.gender, p.rate, p.volume), ("Teen", "Female", -2, 82)
        )
        again = merge_auto_profiles(merged, proposal.profiles)
        self.assertEqual(
            p.__dict__, next(x for x in again if x.name == "Alice").__dict__
        )

    def test_legacy_custom_settings_survive(self):
        existing = [
            CharacterProfile("Narrator"),
            CharacterProfile(
                "Alice", voice="my-model", rate=3, volume=63, design_strength=41
            ),
        ]
        proposal = auto_profiles('Alice, a girl, whispered, "Hello."')
        p = merge_auto_profiles(existing, proposal.profiles)[1]
        self.assertEqual(
            (p.voice, p.rate, p.volume, p.design_strength), ("my-model", 3, 63, 41)
        )
        self.assertEqual(p.gender, "Female")

    def test_repeat_scan_retains_pronoun_profile_evidence(self):
        source = 'Alice entered. "Hello," she said.'
        first = auto_profiles(source)
        again = auto_profiles(first.script, existing_profiles=first.profiles)
        before = next(p for p in first.profiles if p.name == "Alice")
        after = next(p for p in again.profiles if p.name == "Alice")
        self.assertEqual(before.gender, "Female")
        self.assertEqual(after.gender, before.gender)
        self.assertEqual(again.script, first.script)

    def test_plain_and_archive_project_roundtrip(self):
        from openvoice.project_archive import ProjectData, save_project, load_project

        p = auto_profiles('"Hello," the old man said. The old man was called Elias.')
        p.profiles[1].locked_fields = ["volume"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "profiles.json"
            p.save(path)
            restored = VoiceProject.load(path)
            self.assertEqual(
                [v.__dict__ for v in p.profiles],
                [v.__dict__ for v in restored.profiles],
            )
            archive = Path(d) / "project.oamproj"
            save_project(archive, ProjectData(text=p.script, voice_project=p))
            restored_archive = load_project(archive, Path(d) / "unpacked")
            self.assertEqual(
                restored_archive.voice_project.profiles[1].aliases,
                p.profiles[1].aliases,
            )
            self.assertEqual(
                restored_archive.voice_project.profiles[1].inference,
                p.profiles[1].inference,
            )

    def test_invalid_profile_values_fail_cleanly(self):
        for values in [
            {"name": "[Bad]"},
            {"name": "Bad\nName"},
            {"name": "A", "rate": "bad"},
            {"name": "A", "volume": float("nan")},
            {"name": "A", "aliases": "bad"},
        ]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                CharacterProfile(**values)

    def test_name_import_text_csv_json_and_gzip(self):
        with tempfile.TemporaryDirectory() as d:
            for filename, content in [
                ("names.txt", "# names\nZeraphine\nराम\nZeraphine\n"),
                ("names.csv", "name,region\nZeraphine,fantasy\nराम,India\n"),
                ("names.json", json.dumps(["Zeraphine", "राम"])),
            ]:
                path = Path(d) / filename
                path.write_text(content, encoding="utf-8")
                self.assertEqual(set(read_name_list(path)), {"Zeraphine", "राम"})
            path = Path(d) / "names.txt.gz"
            with gzip.open(path, "wt", encoding="utf-8") as f:
                f.write("Zeraphine\nराम\n")
            self.assertEqual(set(read_name_list(path)), {"Zeraphine", "राम"})

    def test_extra_names_support_lowercase_attribution(self):
        a = analyze_dialogue('xyzzzy said, "Hello."', extra_names=["xyzzzy"])
        self.assertEqual(a.quotations[0].speaker, "xyzzzy")


if __name__ == "__main__":
    unittest.main()
