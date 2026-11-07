from __future__ import annotations
import json
import copy
import math
import re
import unicodedata
from functools import lru_cache
from dataclasses import asdict, dataclass, field
from pathlib import Path
from .voice_catalog import CatalogVoice
from .ipa_pronunciation import display_inline_ipa
from .dialogue_analysis import analyze_dialogue
from .character_identity import TAG_PATTERN, key
from .voice_inference import infer_profile


@dataclass
class CharacterProfile:
    name: str
    voice: str = ""
    gender: str = "Unspecified"
    age: str = "Unspecified"
    language: str = "auto"
    characteristics: str = "natural"
    rate: int = 0
    pitch: int = 0
    design_strength: int = 85
    volume: int = 100
    aliases: list[str] = field(default_factory=list)
    auto_values: dict = field(default_factory=dict)
    inference: dict = field(default_factory=dict)
    locked_fields: list[str] = field(default_factory=list)
    speaker_id: int = 0  # Piper speaker within the selected ONNX voice
    engine: str = 'auto'  # explicitly override speech backend per character
    model: str = ''        # optional neural model name or local Piper ONNX file

    def __post_init__(self):
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or len(self.name) > 160
            or any(c in self.name for c in "[]\n\r")
        ):
            raise ValueError(
                "Character names must be 1–160 characters without brackets or line breaks"
            )
        self.name = self.name.strip()
        for attr, lo, hi in (
            ("rate", -10, 10),
            ("pitch", -10, 10),
            ("volume", 0, 100),
            ("design_strength", 0, 100),
        ):
            try:
                value = float(getattr(self, attr))
                if not math.isfinite(value):
                    raise ValueError()
                setattr(self, attr, max(lo, min(hi, round(value))))
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("Invalid character " + attr) from exc
        if type(self.speaker_id) is not int or not 0 <= self.speaker_id <= 100000:
            raise ValueError('Invalid character Piper speaker ID (must be nonnegative integer)')
        if not isinstance(self.aliases, list) or any(
            not isinstance(a, str)
            or not a.strip()
            or len(a) > 160
            or any(c in a for c in "[]\n\r")
            for a in self.aliases
        ):
            raise ValueError("Aliases must be a list of valid character names")
        if self.engine not in ('auto', 'piper', 'kokoro', 'kitten', 'pocket', 'coqui', 'sapi', 'macos', 'espeak', 'flite'):
            from .engines import all_engines
            if self.engine not in all_engines():
                raise ValueError('Unknown character speech engine: ' + self.engine)
        self.aliases = list(
            {
                key(a): a.strip()
                for a in reversed(self.aliases)
                if key(a) != key(self.name)
            }.values()
        )
        if (
            not isinstance(self.auto_values, dict)
            or not isinstance(self.inference, dict)
            or not isinstance(self.locked_fields, list)
        ):
            raise ValueError("Invalid character inference metadata")
        for attr in ("voice", "engine", "model", "language", "gender", "age", "characteristics"):
            if not isinstance(getattr(self, attr), str):
                raise ValueError("Invalid character " + attr)


@dataclass
class VoiceProject:
    profiles: list[CharacterProfile] = field(
        default_factory=lambda: [CharacterProfile("Narrator")]
    )
    script: str = ""
    pronunciation_files: list[str] = field(default_factory=list)
    sound_files: list[str] = field(default_factory=list)
    analysis: object = field(default=None, repr=False, compare=False)
    speaker_rules: dict[str,str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.speaker_rules,dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in self.speaker_rules.items()):
            raise ValueError("Speaker rules must map quoted phrases to character profile names")

    def save(self, destination: str | Path) -> None:
        Path(destination).write_text(
            json.dumps(
                {
                    "version": 2,
                    "script": self.script,
                    "pronunciation_files": self.pronunciation_files,
                    "sound_files": self.sound_files,
                    "speaker_rules": self.speaker_rules,
                    "profiles": [asdict(p) for p in self.profiles],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, source: str | Path) -> "VoiceProject":
        data = json.loads(Path(source).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
            raise ValueError("Invalid character voice project")
        profiles = [
            CharacterProfile(**p) for p in data["profiles"] if isinstance(p, dict)
        ]
        for profile in profiles:
            path = Path(profile.voice) if profile.voice else None
            if (
                path is not None
                and path.suffix.lower() == ".onnx"
                and not path.is_absolute()
            ):
                candidate = (Path(source).parent / path).resolve()
                if candidate.is_file():
                    previous_voice = profile.voice
                    profile.voice = str(candidate)
                    if profile.auto_values.get("voice") == previous_voice:
                        profile.auto_values["voice"] = profile.voice
                    if (
                        profile.inference.get("voice", {}).get("suggested")
                        == previous_voice
                    ):
                        profile.inference["voice"]["suggested"] = profile.voice
        if not profiles or not any(p.name.casefold() == "narrator" for p in profiles):
            raise ValueError("A Narrator profile is required")
        if len({key(p.name) for p in profiles}) != len(profiles):
            raise ValueError("Duplicate character names")
        return cls(
            profiles,
            str(data.get("script", "")),
            [
                str(p)
                if Path(p).is_absolute()
                else str((Path(source).parent / p).resolve())
                for p in data.get("pronunciation_files", [])
                if isinstance(p, str)
            ],
            sound_files=[str(Path(p).expanduser().resolve()) if Path(p).is_absolute() else
                         str((Path(source).parent / p).resolve())
                         for p in data.get('sound_files', []) if isinstance(p, str)],
            speaker_rules=data.get('speaker_rules',{}),
        )


@dataclass(frozen=True)
class SpeechPassage:
    speaker: str
    text: str
    language: str


SCRIPT_RANGES = [
    ("bn", "Bengali", 0x0980, 0x09FF),
    ("hi", "Hindi", 0x0900, 0x097F),
    ("ar", "Arabic", 0x0600, 0x06FF),
    ("ru", "Russian", 0x0400, 0x052F),
    ("el", "Greek", 0x0370, 0x03FF),
    ("he", "Hebrew", 0x0590, 0x05FF),
    ("th", "Thai", 0x0E00, 0x0E7F),
    ("ko", "Korean", 0xAC00, 0xD7AF),
    ("ja", "Japanese", 0x3040, 0x30FF),
    ("zh", "Chinese", 0x4E00, 0x9FFF),
    ("ta", "Tamil", 0x0B80, 0x0BFF),
    ("te", "Telugu", 0x0C00, 0x0C7F),
    ("ml", "Malayalam", 0x0D00, 0x0D7F),
    ("gu", "Gujarati", 0x0A80, 0x0AFF),
    ("pa", "Punjabi", 0x0A00, 0x0A7F),
    ("kn", "Kannada", 0x0C80, 0x0CFF),
]
STOPWORDS = {
    "en": {
        "the",
        "and",
        "of",
        "in",
        "was",
        "is",
        "with",
        "for",
        "to",
        "you",
        "she",
        "he",
        "said",
        "asked",
        "replied",
        "are",
        "were",
        "has",
        "have",
        "had",
        "did",
        "do",
        "does",
        "we",
        "they",
        "this",
        "that",
        "my",
        "your",
        "it",
        "from",
        "by",
        "but",
        "as",
        "at",
        "on",
        "not",
        "would",
        "could",
        "should",
        "there",
        "here",
        "then",
        "when",
        "why",
        "what",
        "where",
        "his",
        "her",
        "their",
        "me",
        "mine",
        "us",
        "our",
        "him",
        "them",
        "who",
        "which",
        "all",
        "just",
        "can",
        "will",
        "say",
        "yes",
        "hello",
        "good",
        "morning",
        "story",
    },
    "fr": {
        "le",
        "les",
        "la",
        "des",
        "une",
        "est",
        "dans",
        "pour",
        "avec",
        "vous",
        "elle",
    },
    "es": {"el", "los", "las", "una", "que", "del", "con", "para", "como", "está"},
    "de": {"der", "die", "das", "ist", "mit", "und", "ein", "eine", "nicht", "ich"},
    "pt": {"uma", "que", "com", "não", "para", "está", "como", "dos", "das"},
    "it": {"gli", "una", "che", "con", "per", "non", "sono", "della"},
    "nl": {"het", "een", "van", "niet", "met", "voor", "zijn", "dat"},
}


@lru_cache(maxsize=1)
def _lingua_detector():
    try:
        from lingua import LanguageDetectorBuilder

        # Load on demand: preloading all models is prohibitively large on low-end PCs.
        return LanguageDetectorBuilder.from_all_languages().build()
    except (ImportError, OSError):
        return None


def _clean_language_text(text: str) -> str:
    # Actor tags and IPA notation are not the language spoken by the passage.
    return re.sub(r"\[[^\[\]\n]{1,160}\]", " ", display_inline_ipa(text))


def detect_language(text: str) -> tuple[str, float]:
    text = _clean_language_text(text)
    significant = sum(unicodedata.category(ch).startswith("L") for ch in text)
    if significant == 0:
        return "und", 0.0
    counts = {
        iso: sum(start <= ord(ch) <= end for ch in text)
        for iso, _, start, end in SCRIPT_RANGES
    }
    kana = counts.get("ja", 0)
    han = counts.get("zh", 0)
    # Kanji coexists with kana in Japanese; isolated Han text is ambiguous Chinese.
    if kana >= 2 and (kana + han) / significant > 0.2:
        return "ja", round(min(0.99, 0.68 + (kana + han) / significant * 0.29), 2)
    candidates = {iso: n for iso, n in counts.items() if iso != "ja" and n}
    nonlatin = max(candidates, key=candidates.get) if candidates else ""
    if nonlatin and candidates[nonlatin] >= max(2, significant * 0.28):
        n = candidates[nonlatin]
        return nonlatin, round(min(0.99, 0.55 + n / significant * 0.43), 2)
    if len(text.strip()) >= 35:
        detector = _lingua_detector()
        if detector is not None:
            try:
                values = detector.compute_language_confidence_values(text)
                if values and values[0].value >= 0.52:
                    code = values[0].language.iso_code_639_1
                    if code is not None:
                        return code.name.lower(), round(values[0].value, 2)
            except (ValueError, RuntimeError):
                pass
    words = re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
    scores = {code: sum(w in vocab for w in words) for code, vocab in STOPWORDS.items()}
    if not words or not any(scores.values()):
        return "und", 0.0
    ordered = sorted(scores.items(), key=lambda x: -x[1])
    first = ordered[0][1]
    runner = ordered[1][1] if len(ordered) > 1 else 0
    if first == runner:
        return "und", 0.0
    return ordered[0][0], round(
        min(0.95, 0.49 + (first - runner) / max(3, first) * 0.43), 2
    )


def detected_languages(text: str) -> list[tuple[str, float]]:
    """Find languages across paragraphs, including mixed-script paragraphs."""
    source = _clean_language_text(text)
    segments = []
    for para in re.split(r"\n\s*\n|(?<=[.!?。！？])\s+(?=[A-Z\u0400-\uffff])", source):
        if not para.strip():
            continue
        # Preserve latin/nonlatin fragments even if both occur on a single line.
        for line in para.splitlines():
            chunks = re.findall(
                r"[\u3040-\u30ff\u3400-\u9fff]+|[\u0980-\u09ff]+|[\u0900-\u097f]+|[\u0400-\u052f]+|[\u0600-\u06ff]+|[A-Za-zÀ-ž][A-Za-zÀ-ž\s’\'-]{2,}|[^\s]+",
                line,
            )
            merged = []
            for chunk in chunks:
                if not chunk.strip():
                    continue
                if (
                    merged
                    and re.match(r"[A-Za-zÀ-ž]", chunk)
                    and re.match(r"[A-Za-zÀ-ž]", merged[-1])
                ):
                    merged[-1] += " " + chunk
                else:
                    merged.append(chunk)
            segments.extend(merged)
    scores = {}
    max_conf = {}
    for item in segments:
        lang, conf = detect_language(item)
        if lang == "und" or conf < 0.48:
            continue
        weight = min(200, max(1, sum(ch.isalpha() for ch in item)))
        scores[lang] = scores.get(lang, 0) + weight * conf
        max_conf[lang] = max(max_conf.get(lang, 0), conf)
    return [
        (lang, round(max_conf[lang], 2))
        for lang in sorted(scores, key=lambda x: -scores[x])
    ]


def parse_passages(
    text: str, profiles: list[CharacterProfile], *, auto_tag: bool = False, speaker_rules=None
) -> list[SpeechPassage]:
    names = {key(p.name): p.name for p in profiles}
    names.update({key(a): n for a, n in profile_aliases(profiles).items()})
    if auto_tag:
        analysis = analyze_dialogue(
            text,
            known_names=[p.name for p in profiles],
            known_aliases=profile_aliases(profiles),
            speaker_rules=speaker_rules,
        )
        text = analysis.tagged_text
        for discovered in analysis.characters:
            if key(discovered) in names:
                continue
            previous = {
                names[key(a)]
                for a, n in analysis.aliases.items()
                if key(n) == key(discovered) and key(a) in names
            }
            names[key(discovered)] = (
                next(iter(previous))
                if len(previous) == 1
                else names.get("narrator", "Narrator")
            )
    current = names.get("narrator", "Narrator")
    passages: list[SpeechPassage] = []
    inline = re.compile(r"^\s*([^:\n]{1,160}):\s*(.+)$")
    tags = TAG_PATTERN

    def append(content: str):
        if content.strip():
            language, _ = detect_language(display_inline_ipa(content))
            passages.append(SpeechPassage(current, content.strip(), language))

    for line in text.splitlines():
        content = line.strip()
        leading = re.match(r"^\s*\[Narrator\]\s*", content, re.I)
        if leading:
            current = names.get("narrator", "Narrator")
            content = content[leading.end() :]
        if not content:
            continue
        match = inline.match(content)
        if match and key(match.group(1)) in names:
            current = names[key(match.group(1))]
            content = match.group(2).strip()
        elif auto_tag:
            attributed = re.search(
                r"\b([\w-]{2,35})\s+(?:said|asked|replied|whispered|shouted|answered|murmured)\b",
                content,
                re.I,
            )
            if attributed and attributed.group(1).casefold() in names:
                current = names[attributed.group(1).casefold()]
            elif not content.startswith(("“", '"', "'")):
                current = names.get("narrator", "Narrator")
        position = 0
        for tag in tags.finditer(content):
            who = names.get(key(tag.group(1)))
            if who is None:
                continue
            append(content[position : tag.start()])
            current = who
            position = tag.end()
        append(content[position:])
    return passages


PROFILE_FIELDS = (
    "language",
    "voice",
    "speaker_id",
    "engine",
    "model",
    "rate",
    "volume",
    "pitch",
    "gender",
    "age",
    "characteristics",
    "design_strength",
)


def profile_aliases(profiles: list[CharacterProfile]) -> dict[str, str]:
    candidates = {}
    for p in profiles:
        if key(p.name) == "narrator":
            continue
        for alias in [p.name, *p.aliases]:
            candidates.setdefault(key(alias), set()).add(p.name)
    return {a: next(iter(v)) for a, v in candidates.items() if len(v) == 1}


def read_name_list(source: str | Path) -> list[str]:
    """Import UTF-8 text, CSV (first column), JSON array, or GZip name lists."""
    import csv
    import gzip
    import io

    source = Path(source)
    opener = gzip.open if source.suffix.casefold() == ".gz" else open
    with opener(source, "rt", encoding="utf-8-sig") as stream:
        content = stream.read(32_000_001)
    if len(content) > 32_000_000:
        raise ValueError("Name list exceeds 32 million characters; split it into files")
    extension = source.stem if source.suffix.casefold() == ".gz" else source.name
    if extension.casefold().endswith(".json"):
        values = json.loads(content)
        if not isinstance(values, list):
            raise ValueError("Name JSON must be an array of strings")
    elif extension.casefold().endswith(".csv"):
        values = [row[0] for row in csv.reader(io.StringIO(content)) if row]
        if values and key(values[0]) in {"name", "names", "first name", "full name"}:
            values = values[1:]
    else:
        values = content.splitlines()
    names = {}
    for value in values:
        if not isinstance(value, str):
            raise ValueError("Each imported name must be text")
        name = value.strip()
        if not name or name.startswith("#"):
            continue
        CharacterProfile(name)  # use the same marker validation as projects
        names.setdefault(key(name), name)
    return list(names.values())


def _voice_info(voice, catalog=(), metadata=None):
    value = str(getattr(voice, "name", voice))
    path = getattr(voice, "model", None)
    if path is None and value.lower().endswith(".onnx"):
        path = Path(value)
    name = Path(value).stem if value.lower().endswith(".onnx") else value
    record = next((v for v in catalog if v.key.casefold() == name.casefold()), None)
    language = record.language if record else name.split("-", 1)[0].replace("_", "-")
    quality = record.quality if record else name.rsplit("-", 1)[-1]
    info = {}
    if path:
        config = Path(str(path) + ".json")
        try:
            if config.stat().st_size < 2_000_000:
                data = json.loads(config.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    lang = data.get("language", {})
                    if isinstance(lang, dict):
                        language = lang.get("code") or language
                    details = data.get("openmukti", {})
                    if isinstance(details, dict):
                        info.update(details)
        except (OSError, ValueError, TypeError):
            pass
    supplied = (metadata or {}).get(value, (metadata or {}).get(name, {}))
    if isinstance(supplied, dict):
        info.update(supplied)
    info.update(
        {
            "value": value,
            "language": str(info.get("language") or language).replace("_", "-"),
            "quality": quality,
        }
    )
    return info


def _choose_installed_voice(
    language: str,
    installed: list,
    taken: set[str],
    *,
    profile=None,
    catalog=(),
    metadata=None,
) -> str:
    """Rank installed models by locale, known metadata, quality and reuse.

    Demographics are read only from explicit local metadata, never guessed from
    model/person names. Downloadable catalog entries are not assigned as if installed.
    """
    family = language.replace("_", "-").split("-")[0].casefold()
    matches = [_voice_info(v, catalog, metadata) for v in installed]
    matches = [v for v in matches if v["language"].casefold().split("-")[0] == family]
    if not matches:
        return ""

    def score(v):
        total = (
            12
            if v["language"].casefold() == language.replace("_", "-").casefold()
            else 0
        )
        total += {"high": 5, "medium": 4, "low": 2, "x_low": 0}.get(v["quality"], 1)
        total += 3 if v["value"] not in taken else 0
        if profile:
            gender = str(v.get("gender", "Unspecified")).casefold()
            if gender != "unspecified" and profile.gender != "Unspecified":
                total += 25 if gender == profile.gender.casefold() else -25
            if str(v.get("age", "")).casefold() == profile.age.casefold():
                total += 4
            styles = v.get("styles", [])
            if isinstance(styles, str):
                styles = styles.split(",")
            if isinstance(styles, list):
                total += 2 * len(
                    {str(s).strip().casefold() for s in styles}
                    & {s.strip().casefold() for s in profile.characteristics.split(",")}
                )
        return -total, v["value"].casefold()

    return min(matches, key=score)["value"]


def auto_profiles(
    text: str,
    *,
    installed: list | None = None,
    catalog: list[CatalogVoice] | None = None,
    known_names=(),
    existing_profiles: list[CharacterProfile] | None = None,
    voice_metadata: dict | None = None,
    extra_names=(),
) -> VoiceProject:
    installed = installed or []
    existing_profiles = existing_profiles or []
    known = list(dict.fromkeys([*known_names, *(p.name for p in existing_profiles)]))
    analysis = analyze_dialogue(
        text,
        known_names=known,
        known_aliases=profile_aliases(existing_profiles),
        extra_names=extra_names,
    )
    names = ["Narrator"] + [n for n in analysis.characters if key(n) != "narrator"]
    langs = detected_languages(text)
    general = langs[0][0] if langs else "auto"
    # Group speech once. Per-character language analysis excludes attribution
    # prose, which can be in a different language from the character's quotes.
    own = {key(n): [] for n in names}
    for q in analysis.quotations:
        if q.speaker != "Narrator":
            own[key(q.speaker)].append(text[q.start : q.end])
    for passage in parse_passages(
        analysis.tagged_text, [CharacterProfile(n) for n in names]
    ):
        if passage.speaker == "Narrator" or not own.get(key(passage.speaker)):
            own.setdefault(key(passage.speaker), []).append(passage.text)
    assigned = set()
    profiles = []
    for n in names:
        spoken = " ".join(own[key(n)])
        own_languages = detected_languages(spoken)
        local = own_languages[0][0] if own_languages else general
        p = CharacterProfile(n, language=local)
        clues, evidence = infer_profile(text, n, analysis)
        for attr, value in clues.items():
            setattr(p, attr, value)
        p.inference = evidence
        p.inference["language"] = {
            "confidence": own_languages[0][1]
            if own_languages
            else langs[0][1]
            if langs
            else 0.0,
            "evidence": [
                "Character dialogue language"
                if own_languages
                else "Document language fallback"
                if langs
                else "No reliable language evidence"
            ],
        }
        entity = next((e for e in analysis.entities if key(e.name) == key(n)), None)
        p.aliases = list(
            {
                key(a): a
                for a in sorted((entity.aliases if entity else ()), reverse=True)
                if key(a) != key(n) and analysis.aliases.get(a) == n
            }.values()
        )
        p.inference["name"] = {
            "confidence": 1.0,
            "evidence": list(entity.evidence)
            if entity and entity.evidence
            else ["Canonical speaker identity"],
        }
        p.voice = _choose_installed_voice(
            p.language,
            installed,
            assigned,
            profile=p,
            catalog=catalog or (),
            metadata=voice_metadata,
        )
        if p.voice:
            assigned.add(p.voice)
        p.inference["voice"] = {
            "confidence": 0.7 if p.voice else 0.0,
            "evidence": [
                "Matching installed model: " + p.voice
                if p.voice
                else "No matching installed model; automatic engine selection"
            ],
        }
        for attr in PROFILE_FIELDS:
            p.inference.setdefault(
                attr,
                {
                    "confidence": 0.0,
                    "evidence": ["No character-specific evidence; default retained."],
                },
            )["suggested"] = getattr(p, attr)
        p.auto_values = {attr: getattr(p, attr) for attr in PROFILE_FIELDS}
        profiles.append(p)
    return VoiceProject(profiles, analysis.tagged_text, analysis=analysis)


def merge_auto_profiles(
    existing: list[CharacterProfile], proposed: list[CharacterProfile]
) -> list[CharacterProfile]:
    """Refresh all inferred fields while preserving per-field manual overrides.

    Legacy projects without inference metadata retain non-default settings. Old
    descriptive profiles are folded into a verified canonical identity.
    """
    output = []
    consumed = set()
    for new in proposed:
        identities = {key(new.name), *(key(a) for a in new.aliases)}
        matches = [
            (i, p)
            for i, p in enumerate(existing)
            if i not in consumed and key(p.name) in identities
        ]
        matches.sort(key=lambda item: key(item[1].name) != key(new.name))
        if not matches:
            output.append(copy.deepcopy(new))
            continue
        index, old = matches[0]
        current = copy.deepcopy(old)
        current.name = new.name
        current.aliases = list(
            dict.fromkeys(
                [
                    *new.aliases,
                    *old.aliases,
                    *(p.name for _, p in matches if key(p.name) != key(new.name)),
                ]
            )
        )
        # A manually configured unnamed profile can have settings worth keeping
        # when the named profile still holds defaults.
        for _, secondary in matches[1:]:
            defaults = CharacterProfile(secondary.name)
            for attr in PROFILE_FIELDS:
                if getattr(current, attr) == getattr(defaults, attr) and (
                    attr in secondary.locked_fields
                    or getattr(secondary, attr)
                    != secondary.auto_values.get(attr, getattr(defaults, attr))
                ):
                    setattr(current, attr, getattr(secondary, attr))
                    if attr not in current.locked_fields:
                        current.locked_fields.append(attr)
        defaults = CharacterProfile(old.name)
        for attr in PROFILE_FIELDS:
            value = getattr(current, attr)
            previous = current.auto_values.get(attr, getattr(defaults, attr))
            if attr not in current.locked_fields and value == previous:
                setattr(current, attr, getattr(new, attr))
                current.auto_values[attr] = getattr(new, attr)
        current.aliases = list(
            {
                key(a): a
                for a in reversed(current.aliases)
                if key(a) != key(current.name)
            }.values()
        )
        current.inference = copy.deepcopy(new.inference)
        output.append(current)
        consumed.update(i for i, _ in matches)
    output.extend(copy.deepcopy(p) for i, p in enumerate(existing) if i not in consumed)
    return output


def detect_characters(text: str) -> list[str]:
    return [
        n
        for n in analyze_dialogue(text, annotate=False).characters
        if n.casefold() != "narrator"
    ]


def recommend_voices(
    profile: CharacterProfile,
    catalog: list[CatalogVoice],
    *,
    used: set[str] | None = None,
    limit: int = 5,
) -> list[CatalogVoice]:
    language = profile.language if profile.language not in ("auto", "und") else "en"
    normalized = language.replace("_", "-").casefold()
    family = normalized.split("-")[0]
    voices = [
        v
        for v in catalog
        if v.language.replace("_", "-").casefold().split("-")[0] == family
    ]
    quality = {"high": 0, "medium": 1, "low": 2, "x_low": 3}
    taken = used or set()
    return sorted(
        voices,
        key=lambda v: (
            v.key in taken,
            v.language.casefold() != normalized,
            quality.get(v.quality, 3),
            v.key,
        ),
    )[:limit]
