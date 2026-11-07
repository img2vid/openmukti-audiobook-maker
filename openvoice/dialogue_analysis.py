"""Offline evidence-based dialogue attribution with persistent entity aliases.

The recognizer combines lexical, syntactic, identity, discourse, action-beat,
pronoun, vocative and turn-taking evidence. It never deletes source text or
pretends ambiguous prose is certain. All positions refer to the input script.
"""

from __future__ import annotations

import bisect
import gzip
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources

from .character_identity import (
    TAG_PATTERN,
    WORD,
    PHRASE,
    Identities,
    Entity,
    PRONOUNS,
    BAD_NAMES,
    NOUNS,
    key,
    proper_name,
    description,
)


@lru_cache(maxsize=1)
def human_names() -> frozenset[str]:
    with (
        resources.files("openvoice")
        .joinpath("resources/human_names.txt.gz")
        .open("rb") as stream
    ):
        with gzip.GzipFile(fileobj=stream) as source:
            return frozenset(
                key(row)
                for row in source.read().decode("utf-8").splitlines()
                if row and not row.startswith("#")
            )


SPEECH_VERBS = tuple(
    """said says say asked asks answered answers replied replies
whispered whispers murmured murmurs muttered mutters shouted shouts yelled yells
cried cries exclaimed exclaims called calls remarked observed snapped sighed
laughed screamed stammered stuttered hissed growled barked begged demanded
insisted admitted confessed added continued responded protested argued warned
explained announced declared mused wondered inquired retorted scoffed chuckled
sobbed grumbled sang shrieked shrieks spoke began told repeated whined rasped
croaked gasped blurted pleaded jeered quipped echoed agreed urged suggested
responds uttered sneered drawled boomed thundered bellowed roared squeaked
squealed cooed purred breathed mumbled intoned chirped rumbled""".split()
) + tuple(
    """dijo dice preguntó respondió exclamó susurró
 dit demanda répondit murmura s'exclama répondu
 sagte fragte antwortete flüsterte rief
 disse perguntou respondeu sussurrou chiese rispose sussurrò
 сказал сказала спросил спросила ответил ответила прошептал прошептала
 বলল বললেন জিজ্ঞেস করল উত্তর দিল
 قال قالت سأل سألت أجاب أجابت""".split()
)
VERB_PATTERN = (
    "(?:"
    + "|".join(re.escape(v) for v in sorted(set(SPEECH_VERBS), key=len, reverse=True))
    + ")"
)
# Horizontal whitespace prevents distant paragraphs from becoming one subject.
ADVERB = r"(?:(?:[\w-]+ly|very[ \t]+softly)[ \t]+){0,3}"
SUBJECT_VERB = re.compile(
    rf"(?P<subject>{PHRASE})[ \t]+{ADVERB}(?P<verb>{VERB_PATTERN})\b", re.I
)
VERB_SUBJECT = re.compile(
    rf"\b(?P<verb>{VERB_PATTERN})\b[ \t]+{ADVERB}(?P<subject>{PHRASE})", re.I
)
APPOSITION_VERB = re.compile(
    rf"(?P<subject>{PHRASE})[ \t]*[,—][ \t]*(?P<description>(?:an?|the)[ \t]+[^,.\n“”\"]{{2,100}})[,—][ \t]*{ADVERB}(?P<verb>{VERB_PATTERN})\b",
    re.I,
)
DESCRIPTOR_NAME = re.compile(
    rf"(?P<description>(?:the|an?)[ \t]+{PHRASE})[ \t]*[,—][ \t]*(?P<name>{PHRASE})[ \t]*[,—][ \t]*{ADVERB}(?P<verb>{VERB_PATTERN})\b",
    re.I,
)
ACTOR_PATTERN = re.compile(
    rf"(?P<subject>{PHRASE})[ \t]+(?:quietly[ \t]+|slowly[ \t]+|suddenly[ \t]+)?(?P<verb>entered|walked|looked|smiled|stepped|ran|turned|approached|arrived|appeared|nodded|sat|stood|reached|stared|waved|rushed|paused|hurried|listened|knocked|jumped|opened|watched|grinned|shook|folded|pointed|leaned)\b",
    re.I,
)
DIALOGUE_LINE = re.compile(rf"^[ \t]*(?P<subject>{PHRASE})[ \t]*:[ \t]*(?P<speech>.+)$")
SCENE = re.compile(
    r"(?mi)^[ \t]*(?:\*\s*\*\s*\*|---+|#{1,3}[ \t]+.+|(?:chapter|scene|part|book)[ \t]+[\wivx\d][^\n]*|第[^\n]{1,20}[章幕])[ \t]*$"
)
LINE_TAG = TAG_PATTERN
OPEN_CLOSE = {
    "“": "”",
    "„": "“",
    "«": "»",
    "「": "」",
    "『": "』",
    "‘": "’",
    "‹": "›",
    '"': '"',
    "'": "'",
}


@dataclass(frozen=True)
class Quote:
    start: int
    end: int
    speaker: str = "Narrator"
    confidence: float = 0.0
    reason: str = "unattributed"
    alternatives: tuple[str, ...] = ()


@dataclass(frozen=True)
class DialogueAnalysis:
    tagged_text: str
    characters: tuple[str, ...]
    quotations: tuple[Quote, ...]
    entities: tuple[Entity, ...] = ()
    aliases: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Mention:
    start: int
    end: int
    entity: int
    verb: str
    kind: str = "speech"
    pronoun: str = ""
    text: str = ""


def _quotation_spans(text: str) -> list[tuple[int, int]]:
    stack: list[tuple[str, int]] = []
    spans = []
    # A chapter separator also ends a malformed/unclosed quotation.
    boundaries = {m.start() for m in SCENE.finditer(text)}
    delimiters = set(OPEN_CLOSE) | set(OPEN_CLOSE.values())
    for pos, char in enumerate(text):
        if pos in boundaries:
            stack.clear()
        if char not in delimiters:
            continue
        before = text[pos - 1] if pos else ""
        after = text[pos + 1] if pos + 1 < len(text) else ""
        if char in ("'", "’") and before.isalnum() and after.isalnum():
            continue  # contractions, possessives inside a word
        if (
            char == '"'
            and before.isdigit()
            and (not after or after.isspace())
            and not stack
        ):
            continue  # 12" measurements
        if stack and char == stack[-1][0]:
            _, start = stack.pop()
            if not stack:
                spans.append((start, pos + 1))
            continue
        if char in OPEN_CLOSE:
            if char in ("'", "‘") and before.isalnum():
                continue
            # A repeated opener at the beginning of a new paragraph is the
            # conventional continuation of one multi-paragraph speech.
            line_start = text.rfind("\n", 0, pos) + 1
            if (
                stack
                and OPEN_CLOSE[char] == stack[-1][0]
                and pos > stack[-1][1]
                and not text[line_start:pos].strip()
            ):
                continue
            if char in ('"', "'") and after.isspace() and not stack:
                continue
            stack.append((OPEN_CLOSE[char], pos))
    return spans


def _outside_text(text: str, spans) -> str:
    chunks = []
    cursor = 0
    for start, end in spans:
        chunks.append(text[cursor:start])
        # Preserve offsets and line boundaries, but block subject regexes from
        # matching across a quote or treating words spoken inside it as actors.
        chunks.append("".join("\n" if c == "\n" else "\x00" for c in text[start:end]))
        cursor = end
    chunks.append(text[cursor:])
    return "".join(chunks)


def _trim_subject(raw: str, inverse: bool) -> str:
    if not inverse:
        return raw.strip()
    # "said Alice to Bob" and "asked the man with a sigh": recipient and
    # adjunct are not part of the speaker's name.
    value = re.split(
        r"\s+(?:to|at|with|as|while|before|after|who|whose|and|but|in|on|from|for|then|that|when)\b",
        raw,
        maxsplit=1,
        flags=re.I,
    )[0]
    tokens = value.split()
    if tokens and key(tokens[0]) in PRONOUNS:
        return tokens[0]
    if tokens and key(tokens[0]) in {"the", "a", "an", "another", "this", "that"}:
        # Drop an adverb or verb after the recognized noun.
        ends = [i for i, w in enumerate(tokens) if key(w) in NOUNS]
        return " ".join(tokens[: ends[-1] + 1]) if ends else value
    result = []
    for token in tokens:
        if (
            result
            and not token[0].isupper()
            and key(token) not in {"de", "da", "del", "van", "von", "al", "bin", "ibn"}
        ):
            break
        result.append(token)
    return " ".join(result)


def _speaker_mentions(text: str, offset=0) -> list[tuple[int, int, str, str, float]]:
    # Backward-compatible lightweight API used by extensions.
    out = []
    for pattern, inverse in (
        (SUBJECT_VERB, False),
        (VERB_SUBJECT, True),
        (APPOSITION_VERB, False),
    ):
        for m in pattern.finditer(text):
            raw = _trim_subject(m.group("subject"), inverse)
            name = description(raw) or proper_name(raw)
            if name:
                out.append(
                    (
                        offset + m.start(),
                        offset + m.end(),
                        name,
                        m.group("verb").casefold(),
                        0.97,
                    )
                )
    return out


def _name_or_description(raw, registry, scene, new=False):
    return registry.resolve(raw, scene, new=new)


def analyze_dialogue(
    text: str,
    *,
    known_names=(),
    annotate: bool = True,
    known_aliases: dict[str, str] | None = None,
    extra_names=(),
    speaker_rules=None,
) -> DialogueAnalysis:
    """Return editable tags, attribution confidence and canonical identities.

    Explicit speaker tags win over inference. Unresolved quotes remain narrated.
    Descriptive labels are scene-local until an explicit identity links them to a
    name. Name dictionaries improve recognition but never limit invented names.
    """
    registry = Identities(known_names, known_aliases)
    quote_spans = _quotation_spans(text)
    outside = _outside_text(text, quote_spans)
    boundaries = [m.start() for m in SCENE.finditer(outside)]
    scene_at = lambda pos: bisect.bisect_right(boundaries, pos)
    mentions: list[Mention] = []
    tags = []
    # Parse tags before inferred subjects, so a manual identity is reusable.
    for m in TAG_PATTERN.finditer(text):
        value = m.group(1).strip()
        if key(value) == "narrator":
            tags.append((m.start(), m.end(), -1))
        elif (
            value
            and not key(value).startswith(("chapter ", "page ", "note "))
            and not value.isdigit()
        ):
            if (
                proper_name(value, known_names)
                or description(value)
                or key(value) in registry.manual
            ):
                idx = registry.tagged(value, scene_at(m.start()))
                if idx >= 0:
                    tags.append((m.start(), m.end(), idx))
    # Name lexicons are hints for unconventional lowercase screenplay names.
    hints = {key(n) for n in extra_names}
    seen = set()
    for pattern, inverse in (
        (APPOSITION_VERB, False),
        (SUBJECT_VERB, False),
        (VERB_SUBJECT, True),
    ):
        for m in pattern.finditer(outside):
            raw = _trim_subject(m.group("subject"), inverse)
            verb = m.group("verb").casefold()
            # The full regex can include narration preceding the actual noun.
            raw_start = m.start("subject") + max(0, m.group("subject").rfind(raw))
            start, end = (
                min(raw_start, m.start("verb")),
                max(raw_start + len(raw), m.end("verb")),
            )
            if (start, end) in seen:
                continue
            norm = key(raw)
            pronoun = norm if norm in PRONOUNS else ""
            # For "then he said" the final pronoun is still the subject.
            if not pronoun and raw.split() and key(raw.split()[-1]) in PRONOUNS:
                pronoun = key(raw.split()[-1])
            idx = (
                -1
                if pronoun
                else registry.resolve(
                    raw,
                    scene_at(start),
                    new=bool(re.match(r"(?i)(?:another|a different|a new)\b", raw)),
                )
            )
            if (
                idx < 0
                and not pronoun
                and norm not in BAD_NAMES
                and (norm in hints or norm in human_names())
            ):
                idx = registry.named(raw, scene_at(start))
            if idx < 0 and not pronoun:
                continue
            if pattern is APPOSITION_VERB and idx >= 0:
                desc = description(m.group("description"))
                if desc:
                    other = registry.described(desc, scene_at(start))
                    idx = registry.merge(idx, other, m.group(0).strip())
                    end = m.end()
            mentions.append(
                Mention(start, end, idx, verb, "speech", pronoun, m.group(0).strip())
            )
            seen.add((start, end))
    # Non-Latin speech syntax. Subject is scoped to its grammatical particle;
    # punctuation and quote content are already masked.
    for expr in (
        r"(?P<subject>[\u4e00-\u9fff]{1,12})(?:は|が)(?P<verb>言った|話した|尋ねた|答えた|叫んだ)",
        r"(?P<subject>[\u4e00-\u9fff]{1,12})(?P<verb>说道|說道|回答|喊道|说|說|问|問)",
        rf"(?P<subject>{WORD})[ \t]+(?:ने[ \t]+)?(?P<verb>कहा|पूछा|बोला|बोली|चिल्लाया)",
    ):
        for m in re.finditer(expr, outside):
            idx = registry.named(m.group("subject"), scene_at(m.start()))
            mentions.append(
                Mention(m.start(), m.end(), idx, m.group("verb"), text=m.group(0))
            )
    # "the old man, Elias, said" is the reverse apposition.
    for m in DESCRIPTOR_NAME.finditer(outside):
        desc, name = description(m.group("description")), proper_name(m.group("name"))
        if desc and name:
            a = registry.described(desc, scene_at(m.start()))
            b = registry.named(name, scene_at(m.start()))
            idx = registry.merge(a, b, m.group(0).strip())
            mentions.append(
                Mention(
                    m.start(),
                    m.end(),
                    idx,
                    m.group("verb").casefold(),
                    text=m.group(0).strip(),
                )
            )
    # Narrative actors also support names that never occur in an attribution.
    for m in ACTOR_PATTERN.finditer(outside):
        for raw in re.split(r"\s+and\s+", m.group("subject")):
            idx = registry.resolve(raw, scene_at(m.start()))
            if idx >= 0:
                mentions.append(
                    Mention(
                        m.start(),
                        m.end(),
                        idx,
                        m.group("verb").casefold(),
                        "action",
                        text=m.group(0).strip(),
                    )
                )
    # Explicit identity statements. Never merge on mere proximity or similarity.
    identity_patterns = (
        rf"(?P<desc>(?:the|an?)[ \t]+{PHRASE})[ \t]+(?:was|is)[ \t]+(?:(?:actually|really|in fact)[ \t]+)?(?:(?:named|called|known as)[ \t]+)?(?P<name>{PHRASE})",
        rf"(?P<name>{PHRASE})[ \t]+(?:was|is)[ \t]+(?P<desc>(?:the|an?)[ \t]+{PHRASE})",
        rf"(?P<desc>(?:the|an?)[ \t]+{PHRASE})[ \t]*,[ \t]*(?:whose name was|named|called)[ \t]+(?P<name>{PHRASE})",
        rf"(?P<desc>(?:the|an?)[ \t]+{PHRASE})[ \t]+(?:named|called|known as|introduced (?:himself|herself|itself|themselves) as)[ \t]+(?P<name>{PHRASE})",
        rf"(?P<desc>(?:the|an?)[ \t]+{PHRASE})[’']s[ \t]+name[ \t]+(?:was|is)[ \t]+(?P<name>{PHRASE})",
    )
    for expr in identity_patterns:
        for m in re.finditer(expr, outside, re.I):
            desc = description(m.group("desc"))
            name = proper_name(_trim_subject(m.group("name"), True))
            if desc and name:
                a = registry.described(desc, scene_at(m.start()))
                b = registry.named(name, scene_at(m.start()))
                registry.merge(a, b, m.group(0).strip())
    # Screenplay and em-dash dialogue, preserving narration after speech.
    spans = [(a, b, "quote", -1) for a, b in quote_spans]
    quote_starts = [a for a, _ in quote_spans]
    replaced_quotes = set()
    mentions.sort(key=lambda m: m.start)
    line_mention_starts = [m.start for m in mentions]
    for line in re.finditer(r"[^\n]+", text):
        source = line.group(0)
        label = DIALOGUE_LINE.match(source)
        if label:
            raw = label.group("subject").strip()
            # Reject book headings, times, and prose such as "Note: ...".
            idx = (
                registry.resolve(raw, scene_at(line.start()))
                if key(raw).split()[0] not in BAD_NAMES
                else -1
            )
            if (
                idx < 0
                and key(raw).split()[0] not in BAD_NAMES
                and (key(raw) in hints or key(raw) in human_names())
            ):
                idx = registry.named(raw, scene_at(line.start()))
            if idx >= 0:
                # A quote inside a labelled line is one passage, not overlapping
                # spans with contradictory insertions.
                replaced_quotes.update(
                    quote_starts[
                        bisect.bisect_left(
                            quote_starts, line.start()
                        ) : bisect.bisect_left(quote_starts, line.end())
                    ]
                )
                spans.append(
                    (
                        line.start() + label.start("speech"),
                        line.end(),
                        "screenplay",
                        idx,
                    )
                )
                continue
        qindex = bisect.bisect_left(quote_starts, line.start())
        if qindex < len(quote_starts) and quote_starts[qindex] < line.end():
            continue
        dash = re.match(r"^[ \t]*[—–][ \t]+", source)
        if dash:
            a = line.start() + source.index(source.lstrip()[0])
            speech_tags = [
                m
                for m in mentions[
                    bisect.bisect_left(line_mention_starts, a) : bisect.bisect_left(
                        line_mention_starts, line.end()
                    )
                ]
                if m.kind == "speech"
            ]
            b = min((m.start for m in speech_tags), default=line.end())
            if b > a + 2:
                spans.append((a, b, "dash", -1))
    spans = [s for s in spans if s[2] != "quote" or s[0] not in replaced_quotes]
    spans.sort()
    registry.merge_name_forms()
    mentions.sort(key=lambda m: (m.start, m.kind != "speech"))
    mstarts = [m.start for m in mentions]
    tag_starts = [t[0] for t in tags]
    span_starts = [s[0] for s in spans]
    results: list[Quote] = []
    selected_ids = []
    manual_flags = []
    addressed_ids = []

    def antecedent(event: Mention, qstart: int):
        # Bound the search by scene and distance. A named subject in the
        # current clause outranks a previous turn; gender is used only when
        # the author supplied it, never inferred from a person's name.
        candidates = {}
        left = bisect.bisect_left(mstarts, event.start - 700)
        for previous in mentions[left : bisect.bisect_left(mstarts, event.start)]:
            if (
                previous.entity < 0
                or previous.end > event.start
                or scene_at(previous.start) != scene_at(qstart)
            ):
                continue
            idx = registry.root(previous.entity)
            entity = registry.entities[idx]
            gender = PRONOUNS.get(event.pronoun, "")
            if gender and entity.presentation and gender != entity.presentation:
                continue
            distance = event.start - previous.end
            score = 2.0 - distance / 250 + (0.6 if previous.kind == "action" else 0)
            if gender and entity.presentation == gender:
                score += 1.3
            candidates[idx] = max(candidates.get(idx, -99), score)
        # Previous resolved dialogue may establish a single salient speaker.
        if (
            selected_ids
            and selected_ids[-1] >= 0
            and results
            and qstart - results[-1].end < 450
            and scene_at(results[-1].start) == scene_at(qstart)
        ):
            idx = registry.root(selected_ids[-1])
            entity = registry.entities[idx]
            gender = PRONOUNS.get(event.pronoun, "")
            if not gender or not entity.presentation or gender == entity.presentation:
                candidates[idx] = max(candidates.get(idx, -99), 1.1)
        ranked = sorted(candidates, key=lambda i: (-candidates[i], i))
        if len(ranked) == 1 or (
            ranked and candidates[ranked[0]] - candidates[ranked[1]] >= 1.0
        ):
            return ranked[0], tuple(ranked)
        # A reply can select the other of two already established participants.
        if (
            event.verb in {"replied", "answered", "retorted", "responded"}
            and selected_ids
            and selected_ids[-1] >= 0
        ):
            other = [i for i in ranked if i != registry.root(selected_ids[-1])]
            if len(ranked) == 2 and len(other) == 1:
                return other[0], tuple(ranked)
        return -1, tuple(ranked)

    for start, end, kind, label_id in spans:
        qscene = scene_at(start)
        line_start = text.rfind("\n", 0, start) + 1
        line_end = text.find("\n", end)
        line_end = len(text) if line_end < 0 else line_end
        line_tags = tags[
            bisect.bisect_left(tag_starts, line_start) : bisect.bisect_left(
                tag_starts, line_end
            )
        ]
        tag_i = bisect.bisect_right(tag_starts, start) - 1
        active = tags[tag_i][2] if tag_i >= 0 else -1
        manual = bool(line_tags) or active >= 0
        chosen, confidence, reason, alternatives = -1, 0.0, "unattributed", ()
        if manual:
            chosen = active
            confidence, reason = 1.0, "explicit editable speaker tag"
        elif label_id >= 0:
            chosen, confidence, reason = label_id, 0.99, "screenplay speaker label"
        else:
            ranked = []
            left = bisect.bisect_left(mstarts, start - 220)
            right = bisect.bisect_right(mstarts, end + 180)
            for event in mentions[left:right]:
                if event.kind != "speech" or scene_at(event.start) != qscene:
                    continue
                if event.end <= start:
                    between = text[event.end : start]
                    distance = start - event.end
                    side = "before"
                elif event.start >= end:
                    between = text[end : event.start]
                    distance = event.start - end
                    side = "after"
                else:
                    continue
                multiline_lead = (
                    side == "before"
                    and between.count("\n") == 1
                    and between.strip() in {":", ","}
                )
                if (
                    distance > 150
                    or ("\n" in between and not multiline_lead)
                    or re.search(r"[.!?。！？]", between)
                ):
                    continue
                # Attribution cannot cross another quotation, even a single one.
                si = bisect.bisect_left(span_starts, min(event.end, end))
                if si < len(span_starts) and span_starts[si] < max(event.start, start):
                    continue
                if side == "after":
                    next_i = bisect.bisect_left(span_starts, event.end)
                    if next_i < len(span_starts) and span_starts[next_i] > start:
                        leading = text[event.end : span_starts[next_i]]
                        if (
                            len(leading) < 150
                            and "\n" not in leading
                            and leading.strip() in {"", ",", ":"}
                            and not text[start:end]
                            .rstrip()
                            .endswith((',"', ",”", ",’", ",'", ",»", ",」"))
                        ):
                            continue
                score = 100 - distance * 0.4 + (8 if side == "before" else 0)
                idx, candidates = event.entity, ()
                if event.pronoun:
                    idx, candidates = antecedent(event, start)
                    if idx < 0 and not candidates:
                        # If the scene already contains several actors, a bare
                        # pronoun cannot establish a brand-new identity safely.
                        prior = {
                            registry.root(m.entity)
                            for m in mentions[
                                : bisect.bisect_left(mstarts, event.start)
                            ]
                            if m.entity >= 0 and scene_at(m.start) == qscene
                        }
                        if not prior:
                            idx = registry.pronoun_speaker(event.pronoun, qscene)
                    score -= 18
                if idx >= 0:
                    ranked.append((score, registry.root(idx), event, candidates))
                elif candidates:
                    alternatives = tuple(registry.entities[i].name for i in candidates)
                    reason = "ambiguous pronoun antecedent"
            ranked.sort(key=lambda x: -x[0])
            if ranked:
                top = ranked[0]
                conflicts = [
                    r for r in ranked[1:] if r[1] != top[1] and abs(r[0] - top[0]) < 5
                ]
                if not conflicts:
                    _, chosen, event, _ = top
                    unknown = registry.entities[chosen].name.startswith(
                        "Unidentified speaker ("
                    )
                    confidence = 0.56 if unknown else 0.78 if event.pronoun else 0.97
                    reason = (
                        "consistent unidentified pronoun speaker: "
                        if unknown
                        else "resolved pronoun: "
                        if event.pronoun
                        else "explicit speech attribution: "
                    ) + event.verb
                    if (
                        event.pronoun
                        and PRONOUNS.get(event.pronoun)
                        and not registry.entities[chosen].presentation
                    ):
                        registry.entities[chosen].presentation = PRONOUNS[event.pronoun]
                        registry.entities[chosen].evidence.append(
                            event.pronoun + " " + event.verb
                        )
                else:
                    alternatives = tuple(
                        dict.fromkeys(
                            registry.entities[r[1]].name for r in [top] + conflicts
                        )
                    )
                    reason = "conflicting nearby speech attributions"
            # Same-paragraph action beat: Alice smiled. "Hello." But no
            # attribution may pass a second actor or another quotation.
            speech_content = text[start:end].strip("“”\"‘’'«»「」『』—– ")
            speech_like = bool(
                speech_content
                and (
                    speech_content[0].isupper()
                    or not any(
                        c.lower() != c.upper() for c in speech_content if c.isalpha()
                    )
                )
            )
            if chosen < 0 and not alternatives and speech_like:
                actions = [
                    m
                    for m in mentions[
                        bisect.bisect_left(mstarts, line_start) : bisect.bisect_left(
                            mstarts, start
                        )
                    ]
                    if m.kind == "action" and m.end <= start and start - m.end <= 90
                ]
                if actions:
                    event = actions[-1]
                    between = text[event.end : start]
                    if not any(
                        s < start and e > event.end
                        for s, e, _, _ in spans[
                            max(
                                0, bisect.bisect_left(span_starts, event.end) - 1
                            ) : bisect.bisect_left(span_starts, start)
                        ]
                    ) and not re.search(r"[\"“”«»「」]", between):
                        chosen = registry.root(event.entity)
                        confidence, reason = 0.76, "adjacent narrative action beat"
            # A named vocative in the preceding turn supplies an addressee,
            # not the current speaker. An immediate unlabelled response can
            # belong to that addressee without an arbitrary name guess.
            if (
                chosen < 0
                and not alternatives
                and addressed_ids
                and addressed_ids[-1] >= 0
                and results
            ):
                previous = results[-1]
                between = text[previous.end : start]
                if (
                    scene_at(previous.start) == qscene
                    and "\n" in between
                    and len(between.strip()) < 8
                    and start - previous.end < 80
                ):
                    chosen = registry.root(addressed_ids[-1])
                    confidence, reason = (
                        0.74,
                        "immediate response to named direct address",
                    )
            # Turn taking requires two established participants, separate short
            # dialogue paragraphs, and a nearby explicit anchor. It does not
            # alternate arbitrary scare-quotes or cross a scene boundary.
            if (
                chosen < 0
                and not alternatives
                and len(results) >= 2
                and kind != "screenplay"
            ):
                previous = results[-1]
                between = text[previous.end : start]
                recent = [
                    (q, i)
                    for q, i in zip(results[-4:], selected_ids[-4:])
                    if i >= 0 and scene_at(q.start) == qscene
                ]
                participants = {registry.root(i) for _, i in recent}
                if (
                    len(participants) == 2
                    and selected_ids[-1] >= 0
                    and "\n" in between
                    and len(between.strip()) < 8
                    and start - previous.end < 80
                    and text[start + 1 : start + 2].isupper()
                ):
                    chosen = next(
                        i for i in participants if i != registry.root(selected_ids[-1])
                    )
                    confidence, reason = 0.66, "two-speaker adjacent dialogue turn"
        if chosen >= 0:
            chosen = registry.root(chosen)
            if manual:
                # Re-analysis of generated tags must retain the author's
                # pronoun evidence rather than erasing an inferred voice.
                nearby = mentions[
                    bisect.bisect_left(mstarts, start - 100) : bisect.bisect_right(
                        mstarts, end + 120
                    )
                ]
                for event in nearby:
                    gender = PRONOUNS.get(event.pronoun, "")
                    if not gender:
                        continue
                    between = (
                        text[event.end : start]
                        if event.end <= start
                        else text[end : event.start]
                        if event.start >= end
                        else None
                    )
                    if between is None:
                        continue
                    between = TAG_PATTERN.sub("", between)
                    if (
                        len(between) > 100
                        or "\n" in between
                        or re.search(r"[.!?。！？\"“”«»「」]", between)
                    ):
                        continue
                    entity = registry.entities[chosen]
                    if not entity.presentation:
                        entity.presentation = gender
                    elif entity.presentation != gender:
                        entity.evidence.append("Conflicting presentation descriptions")
                    entity.evidence.append(event.pronoun + " " + event.verb)
            # Exact first-person identification can retroactively resolve an
            # earlier unnamed speaker. Other people's names in speech cannot.
            if registry.entities[chosen].kind == "descriptor":
                spoken = text[start:end].strip("“”\"‘’'«»「」『』 ")
                spoken = re.split(r"(?<=[.!?])[ \t]+", spoken, maxsplit=1)[0]
                identity = re.match(
                    rf"(?:my name is|i am called|call me|i(?: am|'m|’m))[ \t]+(?P<name>{PHRASE})[.!?,]?$",
                    spoken,
                    re.I,
                )
                if identity:
                    name = proper_name(identity.group("name"))
                    if name:
                        chosen = registry.merge(
                            chosen, registry.named(name, qscene), spoken
                        )
        addressee = -1
        if chosen >= 0:
            spoken = text[start:end].lstrip("“\"‘'«「『—– ")
            vocative = re.match(
                rf"(?P<name>{WORD}(?:[ \t]+{WORD}){{0,2}}),[ \t]+(?=[^\W\d_])", spoken
            )
            if vocative:
                candidate = proper_name(vocative.group("name"))
                if candidate:
                    addressee = registry.resolve(candidate, qscene)
                    if addressee >= 0 and registry.root(addressee) == registry.root(
                        chosen
                    ):
                        addressee = -1
        addressed_ids.append(addressee)
        selected_ids.append(chosen)
        manual_flags.append(manual)
        speaker = (
            registry.entities[registry.root(chosen)].name if chosen >= 0 else "Narrator"
        )
        results.append(Quote(start, end, speaker, confidence, reason, alternatives))
    for m in re.finditer(
        rf"\b(?P<pronoun>he|she|it|they|his|her|their)[ \t]+(?:name[ \t]+)?(?:was|is)[ \t]+(?:(?:named|called)[ \t]+)?(?P<name>{PHRASE})",
        outside,
        re.I,
    ):
        name = proper_name(_trim_subject(m.group("name"), True))
        if not name:
            continue
        gender = {"he": "Male", "his": "Male", "she": "Female", "her": "Female"}.get(
            key(m.group("pronoun")), ""
        )
        candidates = {
            registry.root(i)
            for q, i in zip(results, selected_ids)
            if i >= 0
            and q.end <= m.start()
            and m.start() - q.end < 600
            and scene_at(q.start) == scene_at(m.start())
            and registry.entities[registry.root(i)].kind == "descriptor"
            and (
                not gender or registry.entities[registry.root(i)].presentation == gender
            )
        }
        if len(candidates) == 1:
            registry.merge(
                next(iter(candidates)),
                registry.named(name, scene_at(m.start())),
                m.group(0),
            )
    registry.merge_name_forms()
    results = [
        replace(q, speaker=registry.entities[registry.root(idx)].name)
        if idx >= 0
        else q
        for q, idx in zip(results, selected_ids)
    ]
    if speaker_rules:
        approved={key(name):name for name in known_names}
        for i,(quote,manual) in enumerate(zip(results,manual_flags)):
            if manual:
                continue
            passage=text[quote.start:quote.end].casefold()
            for phrase,name in speaker_rules.items():
                if phrase and phrase.casefold() in passage and key(name) in approved:
                    results[i]=replace(quote,speaker=approved[key(name)],confidence=1.0,reason='project speaker rule')
                    break
    alias_targets = defaultdict(set)
    for entity in registry.output():
        for alias in entity.aliases:
            alias_targets[key(alias)].add(entity.name)
    aliases = {
        alias: e.name
        for e in registry.output()
        for alias in sorted(e.aliases)
        if key(alias) != key(e.name) and len(alias_targets[key(alias)]) == 1
    }
    edits = []
    if annotate:
        for q, manual in zip(results, manual_flags):
            if not manual and q.speaker != "Narrator":
                edits.extend(
                    [
                        (q.start, q.start, "[" + q.speaker + "] "),
                        (q.end, q.end, " [Narrator] "),
                    ]
                )
        # A verified identity revelation also updates old unnamed control tags.
        for a, b, idx in tags:
            if idx >= 0:
                canonical = registry.entities[registry.root(idx)].name
                if text[a:b] != "[" + canonical + "]":
                    edits.append((a, b, "[" + canonical + "]"))
    output = text
    if edits:
        parts = []
        cursor = 0
        for a, b, insertion in sorted(edits, key=lambda v: (v[0], v[1])):
            parts.extend((text[cursor:a], insertion))
            cursor = b
        parts.append(text[cursor:])
        output = "".join(parts)
        if not TAG_PATTERN.match(output.lstrip()):
            output = "[Narrator] " + output
    entities = registry.output()
    return DialogueAnalysis(
        output, tuple(e.name for e in entities), tuple(results), entities, aliases
    )


def profile_clues(text: str, name: str, *, mentions=None, analysis=None) -> dict:
    """Compatibility entry point for the full evidence-based inference engine."""
    from .voice_inference import infer_profile

    analysis = analysis or analyze_dialogue(text, known_names=[name], annotate=False)
    return infer_profile(text, name, analysis)[0]
