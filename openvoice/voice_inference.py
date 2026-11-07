"""Explainable character-scoped voice inference, using standard-library CPU code.

These are synthesis suggestions, not claims about a real person's voice. Names
alone never determine gender, age, language, or personality. Every non-default
choice has an author description, attribution, or actual dialogue as evidence.
"""

from __future__ import annotations

import re
from collections import defaultdict
from .character_identity import key, presentation, description
from .dialogue_analysis import VERB_PATTERN, _outside_text

# Persistent author descriptions and transient delivery verbs are scored
# separately. Negated traits are excluded and conflicts stay unspecified.
STYLE_WORDS = {
    "warm": "warm|kind|kindly|kindhearted|affectionate|welcoming|reassuring|motherly|fatherly",
    "calm": "calm|composed|peaceful|serene|unhurried|levelheaded|tranquil|measured",
    "expressive": "expressive|animated|lively|enthusiastic|emotional|passionate",
    "serious": "serious|solemn|stern|grave|formal|businesslike|authoritative",
    "cheerful": "cheerful|happy|joyful|jovial|merry|bubbly|upbeat|playful|laughed|chuckled|quipped",
    "dramatic": "dramatic|theatrical|melodramatic|grandiose|declamatory",
    "gentle": "gentle|tender|soothing|delicate|comforting|patient",
    "soft": "soft|quiet|hushed|subdued|softspoken|soft-spoken",
    "energetic": "energetic|excitable|hyperactive|vigorous|boisterous|shouted|yelled|exclaimed|screamed|bellowed",
    "mysterious": "mysterious|enigmatic|secretive|cryptic|eerie",
    "gruff": "gruff|gravelly|raspy|hoarse|rough|gruffly|rasped|croaked|rumbled",
    "whispery": "whispery|breathy|whispered|whispers|murmured|muttered|hissed|breathed",
    "angry": "angry|furious|irate|irritable|hotheaded|snapped|growled|barked|demanded",
    "sad": "sad|sorrowful|mournful|melancholy|dejected|tearful|sobbed",
    "shy": "shy|timid|bashful|nervous|hesitant|diffident|stammered|stuttered",
    "confident": "confident|assertive|self-assured|resolute|bold|commanding|assured",
    "robotic": "robotic|mechanical|monotone|monotonous|synthetic|emotionless|android",
    "villainous": "villainous|sinister|malevolent|menacing|wicked|malicious|evil",
}
AGE_WORDS = {
    "Child": r"child|toddler|infant|baby|little (?:girl|boy)|young (?:girl|boy|child)",
    "Teen": r"teenager|teenage|teen|adolescent|schoolgirl|schoolboy|eighth.grader|class 8",
    "Young adult": r"young adult|young woman|young man|in (?:his|her|their) twenties",
    "Adult": r"adult|grown.up",
    "Middle aged": r"middle.aged|in (?:his|her|their) (?:forties|fifties)",
    "Senior": r"elderly|old|aged|senior|grandmother|grandfather|grandma|grandpa|in (?:his|her|their) (?:seventies|eighties|nineties)",
}
NUMBERS = dict(
    zip(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split(),
        range(21),
    )
)


def _positive_matches(expr: str, context: str):
    for m in re.finditer(r"\b(?:" + expr + r")\b", context, re.I):
        prefix = context[max(0, m.start() - 24) : m.start()]
        if re.search(
            r"\b(?:not|never|isn't|wasn't|no longer|neither|without)(?:\s+\w+){0,2}\s*$",
            prefix,
            re.I,
        ):
            continue
        yield m


def _contexts(text, name, analysis):
    entity = next((e for e in analysis.entities if key(e.name) == key(name)), None)
    aliases = {name, *(entity.aliases if entity else ())}
    masked = _outside_text(text, [(q.start, q.end) for q in analysis.quotations])
    contexts = []
    # Only subject-attached text, not an arbitrary radius that can contain a
    # different character's description. Limit repetitions, not name support.
    for alias in sorted(aliases, key=len, reverse=True):
        if description(alias):
            contexts.append((alias, 0.9, "descriptive speaker identity"))
        pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.I)
        for m in list(pattern.finditer(masked))[:80]:
            tail = masked[m.end() : m.end() + 200]
            tail = re.split(r"[.!?。！？\n\x00;]", tail, maxsplit=1)[0]
            # Stop at another named actor, even in the same sentence.
            for other in analysis.characters:
                if key(other) == key(name):
                    continue
                other_match = re.search(
                    r"(?<!\w)" + re.escape(other) + r"(?!\w)", tail, re.I
                )
                if other_match:
                    tail = tail[: other_match.start()]
            prefix = masked[max(0, m.start() - 90) : m.start()]
            prefix = re.split(r"[.!?。！？\n;]", prefix)[-1]
            if re.search(
                r"\b(?:\d{1,3}|" + "|".join(NUMBERS) + r")[ -]years?[ -]old\b",
                prefix,
                re.I,
            ) and not any(
                re.search(r"(?<!\w)" + re.escape(other) + r"(?!\w)", prefix, re.I)
                for other in analysis.characters
                if key(other) != key(name)
            ):
                contexts.append((prefix, 0.9, "age description before the name"))
            remainder = masked[m.end() : m.end() + 300]
            continuation = re.match(
                r"[^.!?。！？\n;]*[.!?][ \t]+(?:He|She|They)[ \t]+(?:was|is|had|has|spoke|speaks|always|usually)[ \t]+([^.!?。！？\n;\x00]+)",
                remainder,
            )
            if continuation and not any(
                re.search(
                    r"(?<!\w)" + re.escape(other) + r"(?!\w)",
                    remainder[: continuation.start(1)],
                    re.I,
                )
                for other in analysis.characters
                if key(other) != key(name)
            ):
                contexts.append(
                    (
                        continuation.group(1),
                        0.8,
                        "unambiguous following pronoun description",
                    )
                )
            # An object in "Alice saw an old man" is not Alice's age.
            if re.match(
                r"\s+(?:saw|met|noticed|watched|helped|liked|loved|hated|heard|told|asked|greeted|thanked|visited|called)\b",
                tail,
                re.I,
            ):
                # A delivery adverb remains usable; the object does not.
                speech = re.match(
                    r"\s+(" + VERB_PATTERN + r")(?:\s+([\w-]+ly))?", tail, re.I
                )
                if speech:
                    contexts.append((speech.group(0), 0.55, "speech delivery"))
                continue
            if tail.strip():
                direct = bool(
                    re.match(
                        r"\s*(?:,|—|(?:was|is|had|has|speaks|spoke|always|usually)\b)",
                        tail,
                        re.I,
                    )
                )
                contexts.append(
                    (
                        tail.strip(" ,—"),
                        0.9 if direct else 0.55,
                        "author description" if direct else "speech delivery",
                    )
                )
    if entity:
        for evidence in entity.evidence:
            if re.fullmatch(r"(?:he|she)\s+\w+", evidence, re.I):
                continue
            # Identity descriptions are evidence; bare proper names are not.
            if any(
                w in key(evidence).split()
                for w in (
                    "man",
                    "woman",
                    "boy",
                    "girl",
                    "dog",
                    "cat",
                    "robot",
                    "elderly",
                    "teenage",
                )
            ):
                contexts.append((evidence, 0.85, "verified identity description"))
    # First-person biographical declarations are attributed only to this
    # character. Quoted descriptions of other people are excluded.
    for q in analysis.quotations:
        if key(q.speaker) != key(name):
            continue
        speech = text[q.start : q.end].strip("“”\"‘’'«»「」『』 ")
        for m in re.finditer(
            r"\b(?:I am|I'm|I’m)\s+([^.!?。！？]{1,90})", speech, re.I
        ):
            contexts.append((m.group(1), 0.85, "attributed first-person description"))
        # Pronoun attributions supply presentation evidence, never name guesses.
        if q.reason.startswith("resolved pronoun:"):
            nearby = text[q.end : q.end + 60]
            p = re.match(r"\s*[,—-]?\s*(he|she)\s+", nearby, re.I)
            if p:
                contexts.append(
                    (
                        "male" if p.group(1).casefold() == "he" else "female",
                        0.75,
                        "resolved pronoun",
                    )
                )
    return contexts, entity


def infer_profile(text: str, name: str, analysis) -> tuple[dict, dict]:
    result = {
        "gender": "Unspecified",
        "age": "Unspecified",
        "characteristics": "natural",
        "rate": 0,
        "pitch": 0,
        "volume": 100,
        "design_strength": 0,
    }
    evidence = {}
    if key(name) == "narrator":
        evidence["design_strength"] = {
            "confidence": 1.0,
            "evidence": ["Narrator retains a neutral original voice."],
        }
        return result, evidence
    contexts, entity = _contexts(text, name, analysis)
    votes = defaultdict(lambda: defaultdict(float))
    snippets = defaultdict(lambda: defaultdict(list))

    def vote(field, value, weight, snippet):
        votes[field][value] += weight
        if snippet not in snippets[field][value]:
            snippets[field][value].append(snippet[:180])

    title = key(name).split()[0].rstrip(".") if name.split() else ""
    if title in {
        "ms",
        "mrs",
        "miss",
        "lady",
        "queen",
        "princess",
        "madame",
        "señora",
        "frau",
    }:
        vote("gender", "Female", 0.65, "Honorific: " + title)
    elif title in {"mr", "sir", "lord", "king", "prince", "señor", "herr"}:
        vote("gender", "Male", 0.65, "Honorific: " + title)
    if entity and entity.presentation:
        vote(
            "gender",
            entity.presentation,
            0.75,
            "Descriptive identity / resolved pronoun",
        )
    for context, weight, origin in contexts:
        positive = " ".join(
            m.group(0)
            for m in _positive_matches(
                r"woman|girl|mother|sister|daughter|grandmother|aunt|wife|queen|princess|female|man|boy|father|brother|son|grandfather|uncle|husband|king|prince|male",
                context,
            )
        )
        gender = presentation(positive)
        if gender:
            vote("gender", gender, weight, context)
        for term, value in (
            (r"non.?binary", "Nonbinary"),
            (r"androgynous", "Androgynous"),
        ):
            if list(_positive_matches(term, context)):
                vote("gender", value, weight + 1, context)
        ages = []
        for m in re.finditer(
            r"\b(\d{1,3}|"
            + "|".join(NUMBERS)
            + r")[ -](?:years?[ -]old|year[ -]old)\b|\b(?:aged?|age of)\s+(\d{1,3})\b",
            context,
            re.I,
        ):
            raw = m.group(1) or m.group(2)
            age = NUMBERS.get(raw.casefold(), int(raw) if raw.isdigit() else -1)
            if 0 <= age <= 120:
                ages.append(age)
        for age in ages:
            value = (
                "Child"
                if age < 13
                else "Teen"
                if age < 20
                else "Young adult"
                if age < 30
                else "Adult"
                if age < 45
                else "Middle aged"
                if age < 65
                else "Senior"
            )
            vote("age", value, weight + 1.2, context)
        if not ages:
            for value, expr in AGE_WORDS.items():
                if list(_positive_matches(expr, context)):
                    # "young adult" shouldn't simultaneously vote Adult.
                    if value == "Adult" and re.search(r"young adult", context, re.I):
                        continue
                    vote("age", value, weight, context)
        for style, words in STYLE_WORDS.items():
            if (
                style == "angry"
                and entity
                and any(
                    re.search(r"\b(?:dog|wolf|fox)\b", a, re.I) for a in entity.aliases
                )
            ):
                words = words.replace("|barked", "")
            if list(_positive_matches(words, context)):
                vote("characteristics", style, weight, context)
        for field, value, expr in (
            (
                "rate",
                2,
                r"quickly|rapidly|hurriedly|fast.talking|speaks? fast|speaks? quickly",
            ),
            ("rate", -2, r"slowly|drawled|unhurried|slow.talking|speaks? slowly"),
            ("pitch", 3, r"high.pitched|squeaky|shrill|squeaked|squealed|high voice"),
            (
                "pitch",
                -3,
                r"low.pitched|deep voice|deep baritone|bass voice|booming voice",
            ),
            ("volume", 82, r"whispered|whispers|whispery|barely audible"),
            ("volume", 90, r"quiet voice|soft voice|soft.spoken|softly|quietly"),
            ("volume", 100, r"shouted|yelled|boomed|bellowed|loud voice|booming voice"),
        ):
            if list(_positive_matches(expr, context)):
                vote(field, value, weight, context)
    strongest = 0.0
    for field, options in votes.items():
        ranked = sorted(options, key=lambda x: (-options[x], str(x)))
        if field == "characteristics":
            selected = ranked[:3]
            result[field] = ", ".join(selected)
            confidence = min(0.96, max(options[x] for x in selected))
            reasons = [s for x in selected for s in snippets[field][x]][:6]
        else:
            top = ranked[0]
            # If competing descriptions have similar support, do not silently
            # assert one character's age/presentation/voice over the other.
            if len(ranked) > 1 and options[top] < options[ranked[1]] * 1.4:
                evidence[field] = {
                    "confidence": 0.0,
                    "evidence": ["Conflicting clues; left at default."]
                    + [s for v in ranked[:2] for s in snippets[field][v]][:4],
                }
                continue
            result[field] = top
            confidence = min(0.97, options[top])
            reasons = snippets[field][top][:4]
        strongest = max(strongest, confidence)
        evidence[field] = {"confidence": round(confidence, 2), "evidence": reasons}
    if strongest:
        result["design_strength"] = (
            80 if strongest >= 0.85 else 65 if strongest >= 0.7 else 50
        )
    evidence["design_strength"] = {
        "confidence": round(strongest, 2),
        "evidence": [
            "Transformation scaled to the strongest character-specific evidence."
        ],
    }
    return result, evidence
