"""Deterministic, scene-aware character identities. No network or ML runtime.

Descriptions have identities, rather than being turned into a new speaker at
all occurrences. Only explicit equivalences and unambiguous name forms merge.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

TAG_PATTERN = re.compile(r"\[([^\[\]\n]{1,160})\]")
WORD = r"(?:(?:Mr|Mrs|Ms|Dr|Prof|Sr|Sra|St|Jr|[A-Z])\.(?!\w)|[^\W\d_][\w\u0300-\u036f\u0591-\u05c7\u0610-\u061a\u064b-\u065f\u0900-\u0dff’'\-]*)"
PHRASE = rf"{WORD}(?:[ \t]+{WORD}){{0,7}}"
TITLES = set(
    "mr mrs ms miss dr doctor professor prof captain sir lady lord king queen prince princess general sergeant officer teacher master madam uncle aunt grandma grandpa monsieur madame señor señora sra sr herr frau sensei detective father mother".split()
)
BAD_NAMES = set(
    "i you he she they them we us it who someone nobody anybody everybody one the and a an that this then but when where what why how there here his her their my our your its narrator said asked replied yes no hello oh hey okay sir madam mister doctor captain teacher mr mrs chapter part book scene page note meanwhile later suddenly next today tomorrow yesterday now good morning evening night indeed please well very finally once dear go stop run wait stay leave come listen look thanks thank help hurry one two three four five six seven eight nine ten goodbye hi welcome".split()
)
NOUNS = set(
    (
        "man gentleman fellow guy chap woman lady boy lad girl lass child kid youngster person stranger traveler traveller elder soldier guard officer captain king queen prince princess doctor nurse teacher professor student pupil detective wizard witch merchant shopkeeper innkeeper servant maid butler farmer hunter sailor monk priest nun robot android dog canine cat feline wolf fox dragon bird raven parrot horse animal creature monster giant dwarf elf fairy voice speaker figure brother sister mother father grandmother grandfather uncle aunt husband wife friend neighbor neighbour customer manager master mistress landlord landlady passenger driver waiter waitress policeman policewoman kingpin knight warrior talking-dog"
    ).split()
)
DETERMINERS = set(
    "the a an this that another other new different el la un una le les une der die das ein eine o os as um uma il lo gli uno".split()
)
PRONOUNS = {
    "he": "Male",
    "him": "Male",
    "she": "Female",
    "her": "Female",
    "they": "",
    "them": "",
    "it": "",
    "il": "Male",
    "elle": "Female",
    "él": "Male",
    "ella": "Female",
    "er": "Male",
    "sie": "",
    "ele": "Male",
    "ela": "Female",
}
FEMALE = set(
    "woman girl mother sister daughter grandmother grandma aunt wife queen princess witch nun maid landlady waitress policewoman female".split()
)
MALE = set(
    "man boy father brother son grandfather grandpa uncle husband king prince monk priest butler policeman male".split()
)


def key(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value).replace("’", "'").casefold().split()
    ).strip(" .,;:")


def descriptor_key(value: str) -> str:
    words = key(value).split()
    while words and words[0] in DETERMINERS:
        words.pop(0)
    synonyms = {
        "elderly": "old",
        "aged": "old",
        "gentleman": "man",
        "fellow": "man",
        "guy": "man",
        "chap": "man",
        "lady": "woman",
        "lad": "boy",
        "lass": "girl",
        "kid": "child",
        "canine": "dog",
        "feline": "cat",
        "grey-haired": "gray-haired",
    }
    return " ".join(synonyms.get(w, w) for w in words)


def proper_name(raw: str, known=()) -> str:
    tokens = raw.strip(' \t\n,;:!?()[]{}—–“”«»"').split()
    if not tokens:
        return ""
    normalized = key(" ".join(tokens))
    names = {key(n): n for n in known}
    if normalized in names:
        return names[normalized]
    suffix = []
    for token in reversed(tokens):
        clean = token.strip(".,;:!?")
        norm = key(clean)
        if (
            norm in BAD_NAMES
            or (
                norm in DETERMINERS
                and not (
                    suffix
                    and norm
                    in {
                        "de",
                        "da",
                        "del",
                        "van",
                        "von",
                        "den",
                        "bin",
                        "ibn",
                        "al",
                        "la",
                        "le",
                        "dos",
                        "das",
                    }
                )
            )
            or not clean
        ):
            break
        # Uncased scripts are accepted in attribution context; lowercase Latin
        # dictionary words are not converted into invented names.
        uncased = not any(c.lower() != c.upper() for c in clean)
        if not (
            clean[0].isupper()
            or uncased
            or (
                suffix
                and norm
                in {
                    "de",
                    "da",
                    "del",
                    "van",
                    "von",
                    "den",
                    "bin",
                    "ibn",
                    "al",
                    "la",
                    "le",
                    "dos",
                    "das",
                }
            )
        ):
            break
        suffix.insert(0, token.rstrip(",;:!?"))
        if len(suffix) == 6:
            break
    if not suffix:
        return ""
    earlier = len(tokens) - len(suffix) - 1
    if earlier >= 0 and key(tokens[earlier]) in TITLES:
        suffix.insert(0, tokens[earlier])
    if len(suffix) == 1 and key(suffix[0]) in TITLES:
        return ""
    return (
        " ".join(suffix).rstrip(".")
        if not (len(suffix) == 1 and suffix[0].endswith("."))
        else suffix[0].rstrip(".")
    )


def description(raw: str) -> str:
    tokens = raw.strip(' \t\n,;:!?()[]{}—–“”«»".').split()
    if not tokens:
        return ""
    # Keep the final determiner phrase, excluding sentence-leading adverbs.
    starts = [i for i, w in enumerate(tokens) if key(w) in DETERMINERS]
    if starts:
        tokens = tokens[starts[-1] :]
    norms = [key(t) for t in tokens]
    if not any(n in NOUNS for n in norms):
        return ""
    # Reject an object or subordinate clause swallowed by a loose regex.
    if any(
        n
        in {
            "to",
            "at",
            "with",
            "about",
            "from",
            "of",
            "and",
            "but",
            "because",
            "which",
            "who",
            "whose",
        }
        for n in norms
    ):
        return ""
    if norms[-1] not in NOUNS or len(tokens) > 7:
        return ""
    if (
        not starts
        and not (len(tokens) == 1 and norms[0] in NOUNS)
        and not (len(tokens) <= 3 and all(not t[0].isupper() for t in tokens))
    ):
        return ""
    return " ".join(tokens)


def presentation(value: str) -> str:
    words = set(re.findall(r"[^\W\d_]+", key(value)))
    female, male = bool(words & FEMALE), bool(words & MALE)
    return "Female" if female and not male else "Male" if male and not female else ""


@dataclass
class Entity:
    name: str
    kind: str
    scene: int
    aliases: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)
    presentation: str = ""


class Identities:
    def __init__(self, known_names=(), aliases=None):
        self.entities: list[Entity] = []
        self.parent: list[int] = []
        self.proper: dict[str, int] = {}
        self.descriptors: dict[tuple[int, str], list[int]] = {}
        self.manual: dict[str, int] = {}
        self.unidentified: dict[tuple[int, str], int] = {}
        for name in known_names:
            if key(name) == "narrator" or not str(name).strip():
                continue
            base = re.sub(r" \(\d+\)$", "", name)
            idx = (
                self._new(name, "descriptor", -1)
                if description(base) or name.startswith("Unidentified speaker (")
                else self.named(name, 0)
            )
            self.manual[key(name)] = idx
        for alias, name in (aliases or {}).items():
            idx = self.named(name, 0)
            prior = self.manual.get(key(alias))
            if prior is not None and self.root(prior) != self.root(idx):
                idx = self.merge(prior, idx, "explicit saved alias: " + alias)
            self.manual[key(alias)] = idx
            self.entities[idx].aliases.add(alias)

    def root(self, idx: int) -> int:
        while self.parent[idx] != idx:
            self.parent[idx] = self.parent[self.parent[idx]]
            idx = self.parent[idx]
        return idx

    def _new(self, name: str, kind: str, scene: int) -> int:
        idx = len(self.entities)
        self.parent.append(idx)
        self.entities.append(
            Entity(
                name,
                kind,
                scene,
                {name},
                presentation=presentation(name) if kind == "descriptor" else "",
            )
        )
        return idx

    def named(self, name: str, scene: int) -> int:
        if key(name) in self.manual:
            return self.root(self.manual[key(name)])
        if key(name) not in self.proper:
            self.proper[key(name)] = self._new(name, "proper", scene)
        return self.root(self.proper[key(name)])

    def described(self, raw: str, scene: int, *, new: bool = False) -> int:
        desc = descriptor_key(raw)
        lookup = (scene, desc)
        if key(raw) in self.manual:
            idx = self.root(self.manual[key(raw)])
            entity = self.entities[idx]
            if entity.kind == "proper":
                return idx
            if entity.scene in (-1, scene):
                entity.scene = scene
                self.descriptors.setdefault(lookup, []).append(idx)
        existing = {self.root(i) for i in self.descriptors.get(lookup, [])}
        if existing and not new:
            if len(existing) == 1:
                idx = next(iter(existing))
                self.entities[idx].aliases.add(raw)
                return idx
            # A plural candidate is deliberately not resolved to one at random.
            return -1
        # "the man" can shorten "the old man" only when there is one match.
        if not new:
            variants = {
                self.root(i)
                for (s, d), ids in self.descriptors.items()
                if s == scene and d.endswith(" " + desc)
                for i in ids
            }
            if len(variants) == 1:
                idx = next(iter(variants))
                self.entities[idx].aliases.add(raw)
                self.descriptors.setdefault(lookup, []).append(idx)
                return idx
        label = "The " + desc
        count = sum(key(e.name).split(" (")[0] == key(label) for e in self.entities)
        if count:
            label += f" ({count + 1})"
        idx = self._new(label, "descriptor", scene)
        self.entities[idx].aliases.add(raw)
        self.descriptors.setdefault(lookup, []).append(idx)
        return idx

    def tagged(self, value: str, scene: int) -> int:
        idx = (
            self.root(self.manual[key(value)])
            if key(value) in self.manual
            else self.resolve(value, scene)
        )
        if idx >= 0 and self.entities[idx].kind == "descriptor":
            entity = self.entities[idx]
            entity.scene = scene
            base = re.sub(r" \(\d+\)$", "", entity.name)
            desc = description(base)
            if desc:
                self.descriptors.setdefault((scene, descriptor_key(desc)), []).append(
                    idx
                )
        return idx

    def pronoun_speaker(self, pronoun: str, scene: int) -> int:
        lookup = (scene, pronoun)
        if lookup not in self.unidentified:
            label = "Unidentified speaker (" + pronoun + ")"
            if any(e.name == label for e in self.entities):
                label += f" (scene {scene + 1})"
            idx = self._new(label, "descriptor", scene)
            self.entities[idx].presentation = PRONOUNS.get(pronoun, "")
            self.unidentified[lookup] = idx
        return self.root(self.unidentified[lookup])

    def resolve(self, raw: str, scene: int, *, new: bool = False) -> int:
        if (
            key(raw) in self.manual
            and self.entities[self.root(self.manual[key(raw)])].kind == "proper"
        ):
            return self.root(self.manual[key(raw)])
        desc = description(raw)
        if desc:
            return self.described(desc, scene, new=new)
        name = proper_name(raw, self.proper)
        return self.named(name, scene) if name else -1

    def merge(self, first: int, second: int, evidence: str) -> int:
        if min(first, second) < 0:
            return max(first, second)
        a, b = self.root(first), self.root(second)
        if a == b:
            return a
        ea, eb = self.entities[a], self.entities[b]
        # A proper name wins over a description. More complete names win over
        # short forms, except when a user has explicitly chosen a canonical name.
        rank = lambda e: (
            e.kind == "proper",
            key(e.name) in self.manual,
            len(e.name.split()),
            len(e.name),
        )
        if rank(eb) > rank(ea):
            a, b, ea, eb = b, a, eb, ea
        self.parent[b] = a
        ea.aliases.update(eb.aliases)
        ea.evidence.extend(eb.evidence)
        ea.evidence.append(evidence)
        if ea.presentation and eb.presentation and ea.presentation != eb.presentation:
            ea.presentation = ""
            ea.evidence.append("Conflicting presentation descriptions")
        elif not ea.presentation:
            ea.presentation = eb.presentation
        return a

    def merge_name_forms(self):
        # Only a UNIQUE full name may absorb a first name or surname. Two
        # Bennetts or two Alices remain distinct; no edit-distance merging.
        full = [
            (i, e)
            for i, e in enumerate(self.entities)
            if self.root(i) == i and e.kind == "proper"
        ]
        for idx, entity in full:
            parts = key(entity.name).split()
            core = [p for p in parts if p.rstrip(".") not in TITLES]
            candidates = []
            for other, longer in full:
                if other == idx:
                    continue
                lc = [
                    p for p in key(longer.name).split() if p.rstrip(".") not in TITLES
                ]
                if len(lc) > len(core) and (
                    lc[: len(core)] == core or lc[-len(core) :] == core
                ):
                    candidates.append(other)
            roots = {self.root(i) for i in candidates}
            if len(roots) == 1:
                self.merge(idx, next(iter(roots)), "unique full-name / honorific match")

    def output(self) -> tuple[Entity, ...]:
        return tuple(e for i, e in enumerate(self.entities) if self.root(i) == i)
