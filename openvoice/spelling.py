"""Offline English spelling and OCR restoration adapted from MIT Proofloom.

Ports OCR confusion candidates, case matching, document restoration and
overlap-safe edits from img2vid/proofloom at 2fa2d34a2a50fd1a62f9c08c0d9a071265449518.
See THIRD_PARTY_NOTICES.md and resources/PROOFLOOM_LICENSE.txt for provenance.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

COMMON_TYPOS = dict(pair.split(':', 1) for pair in '''
teh:the thsi:this tihs:this hte:the adn:and nad:and annd:and taht:that
wiht:with wtih:with wih:with wich:which whcih:which whihc:which
recieve:receive recieved:received recieves:receives recieveing:receiving
receving:receiving beleive:believe beleived:believed belive:believe
seperate:separate seperated:separated seperately:separately
definately:definitely definitly:definitely definately:definitely
occured:occurred occurence:occurrence ocassion:occasion ocasion:occasion
accomodate:accommodate accomodation:accommodation acheive:achieve
achivement:achievement acheived:achieved acheivement:achievement
adress:address addres:address adressing:addressing
becuase:because beacuse:because becasue:because becouse:because
freind:friend freinds:friends frend:friend freindship:friendship
enviroment:environment goverment:government goverment:government
langauge:language grammer:grammar sentance:sentence sentances:sentences
speling:spelling spelIing:spelling mispelled:misspelled misspeling:misspelling
eror:error erors:errors errror:error errrors:errors
tomorow:tomorrow tommorrow:tomorrow yesturday:yesterday
wierd:weird thier:their peice:piece peices:pieces
begining:beginning beggining:beginning writting:writing comming:coming
untill:until alwasy:always allways:always usefull:useful
succesful:successful sucessful:successful succesfully:successfully
sucess:success bussiness:business buisness:business bussines:business
neccessary:necessary necesary:necessary neccesary:necessary
neccessarily:necessarily aparent:apparent apparant:apparent
arguement:argument arguements:arguments embarass:embarrass
existance:existence independant:independent occured:occurred
posession:possession possesion:possession publically:publicly
realy:really realy:really finaly:finally normaly:normally
probaly:probably propably:probably proably:probably
responsability:responsibility reponsible:responsible
temprature:temperature temperture:temperature vaccum:vacuum
visable:visible invisiable:invisible comparision:comparison
knowlege:knowledge knoledge:knowledge diffrent:different
diffrence:difference diferrent:different differant:different
accross:across agian:again alot:a_lot infront:in_front aswell:as_well
'''.split())
COMMON_TYPOS = {k.casefold(): v.replace('_', ' ') for k, v in COMMON_TYPOS.items()}
OCR_SWAPS = (('rn', 'm'), ('m', 'rn'), ('cl', 'd'), ('d', 'cl'), ('vv', 'w'), ('w', 'vv'), ('h', 'li'), ('li', 'h'), ('ii', 'n'), ('n', 'ii'))
DIGIT_SWAPS = str.maketrans({'0': 'o', '1': 'l', '5': 's', '8': 'b', '2': 'z', '6': 'g', '9': 'g', '|': 'l', '¦': 'l'})
LIGATURES = {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st'}
TOKEN = re.compile(r"(?<![\w])(?:[A-Za-z01|¦][A-Za-z0125689|¦]*)(?:['’][A-Za-z]+)?(?![\w])")
PROTECTED = re.compile(r'https?://[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|`[^`]*`|<ipa:[^>]*>|<[^>]+>|\[[^\]\n]{1,100}\]', re.I)


@dataclass(frozen=True)
class SpellIssue:
    start: int
    end: int
    original: str
    suggestions: tuple[str, ...]
    category: str = 'spelling'
    message: str = 'Not found in the English dictionary.'
    confidence: float = .85

    @property
    def safe(self):
        return self.confidence >= .97


def match_case(candidate, original):
    if original.isupper():
        return candidate.upper()
    if original[:1].isupper():
        return candidate[:1].upper() + candidate[1:]
    return candidate


def edit_distance(a, b):
    """Optimal string alignment, including adjacent transpositions."""
    previous_previous = None
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        row = [i]
        for j, cb in enumerate(b, 1):
            value = min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                value = min(value, previous_previous[j - 2] + 1)
            row.append(value)
        previous_previous, previous = previous, row
    return previous[-1]


@lru_cache(maxsize=1)
def _proofloom_dictionary():
    raw = resources.files('openvoice').joinpath('resources', 'proofloom_english.json.gz').read_bytes()
    return json.loads(gzip.decompress(raw))


@lru_cache(maxsize=1)
def _frequency():
    raw = resources.files('openvoice').joinpath('resources', 'english_frequency.json.gz').read_bytes()
    words = json.loads(gzip.decompress(raw))
    for word in _proofloom_dictionary()['words']:
        words.setdefault(word, 20)
    pairs = resources.files('openvoice').joinpath('resources', 'english_variants.txt').read_text(encoding='utf-8')
    for line in pairs.splitlines():
        if not line or line.startswith('#'):
            continue
        american, british = line.split('\t')
        words.setdefault(british, words.get(american, 100))
        words.setdefault(american, words.get(british, 100))
        for suffix in ('s', 'es', 'ed', 'ing', 'ly', 'ness'):
            if american + suffix in words:
                words.setdefault(british + suffix, words[american + suffix])
        if american.endswith('e') and british.endswith('e'):
            for suffix in ('ing', 'ed'):
                if american[:-1] + suffix in words:
                    words.setdefault(british[:-1] + suffix, words[american[:-1] + suffix])
    return words


class EnglishSpeller:
    def __init__(self, personal=()):
        self.frequency = _frequency()
        self.personal = {str(x).casefold() for x in personal}
        self.personal.update('openmukti proofloom tesseract audiobook audiobooks ebook ebooks offline online pdf epub docx github piper ocr'.split())
        self.cache = {}
        self._deletions = None
        self._words_by_length = None
        self.no_suggest = frozenset(_proofloom_dictionary()['no_suggest'])
        self.replacements = _proofloom_dictionary()['replacements']

    def add_word(self, word):
        self.personal.add(word.casefold())
        self.cache.clear()

    def known(self, word):
        lower = word.casefold().replace('’', "'")
        return lower in self.personal or (lower in self.frequency and lower not in COMMON_TYPOS) or (lower.endswith("'s") and self.known(lower[:-2]))

    def _ocr_candidates(self, word):
        result = set()
        for before, after in OCR_SWAPS:
            start = word.find(before)
            while start >= 0:
                candidate = word[:start] + after + word[start + len(before):]
                if self.known(candidate):
                    result.add(candidate)
                start = word.find(before, start + 1)
        normalized = word.translate(DIGIT_SWAPS)
        if normalized != word and self.known(normalized):
            result.add(normalized)
        # "1" can also mean i; only dictionary-validated variants are offered.
        alternate = normalized.replace('l', 'i') if '1' in word else word
        if alternate != word and self.known(alternate):
            result.add(alternate)
        return result

    def _edits_one(self, word):
        alphabet = 'abcdefghijklmnopqrstuvwxyz'
        for i in range(len(word) + 1):
            left, right = word[:i], word[i:]
            if right:
                yield left + right[1:]
                for char in alphabet:
                    yield left + char + right[1:]
            if len(right) > 1:
                yield left + right[1] + right[0] + right[2:]
            for char in alphabet:
                yield left + char + right

    def _dictionary_candidates(self, word):
        # The REP table shipped with Proofloom's English Hunspell dictionary
        # handles multi-letter spelling confusions (e.g. f/ph and shun/tion).
        for before, after in self.replacements:
            start = word.find(before)
            while start >= 0:
                candidate = word[:start] + after + word[start + len(before):]
                if candidate != word and self.known(candidate):
                    yield candidate
                start = word.find(before, start + 1)

    def _distance_two(self, word):
        # Like Proofloom's deletion index, bounded to common vocabulary for CPU
        # and memory use. Build lazily, only when one-edit candidates fail.
        if self._deletions is None:
            index = defaultdict(list)
            common = sorted(self.frequency, key=self.frequency.get, reverse=True)[:35000]
            for candidate in common:
                if not candidate.isascii() or not candidate.isalpha() or not 3 <= len(candidate) <= 18:
                    continue
                for key in {candidate} | {candidate[:i] + candidate[i + 1:] for i in range(len(candidate))}:
                    index[key].append(candidate)
            self._deletions = index
        found = set()
        keys = {word} | {word[:i] + word[i + 1:] for i in range(len(word))}
        # Proofloom also queries second-order deletions: two extra letters
        # should not leave a common word with an empty suggestion list.
        keys.update(first[:i] + first[i + 1:] for first in tuple(keys) for i in range(len(first)))
        for key in keys:
            found.update(self._deletions.get(key, ()))
        # A one-deletion index cannot recover two missing letters. Keep a
        # compact length index instead of materializing millions of deletion
        # keys for the complete vocabulary (e.g. mispellng -> misspelling).
        if self._words_by_length is None:
            self._words_by_length = defaultdict(list)
            for candidate in self.frequency:
                if candidate.isascii() and candidate.isalpha() and 3 <= len(candidate) <= 26:
                    self._words_by_length[len(candidate)].append(candidate)
        for candidate in self._words_by_length.get(len(word) + 2, ()):
            remaining = iter(candidate)
            if all(char in remaining for char in word):
                found.add(candidate)
        return {c for c in found if c != word and self.known(c) and c not in self.no_suggest
                and abs(len(c) - len(word)) <= 2 and edit_distance(word, c) <= 2}

    def suggest(self, word, *, ocr=True):
        lower = word.casefold().replace('’', "'")
        key = (lower, ocr)
        if key in self.cache:
            return tuple(match_case(x, word) for x in self.cache[key])
        if lower in COMMON_TYPOS:
            candidates = (COMMON_TYPOS[lower],)
        else:
            ocr_choices = self._ocr_candidates(lower) if ocr else set()
            dictionary_choices = set(self._dictionary_candidates(lower))
            choices = ({c for c in self._edits_one(lower) if c != lower and self.known(c)}
                       | ocr_choices | dictionary_choices) - self.no_suggest
            if not choices and 5 <= len(lower) <= 24:
                choices = self._distance_two(lower)
            def score(candidate):
                # Proofloom-style ranking: edit distance, bigram similarity,
                # frequency prior, and an OCR-model bonus.
                a = {lower[i:i + 2] for i in range(len(lower) - 1)}
                b = {candidate[i:i + 2] for i in range(len(candidate) - 1)}
                dice = 2 * len(a & b) / max(1, len(a) + len(b))
                frequency = math.log1p(self.frequency.get(candidate, 0)) / 20
                return (1.4 * dice - .6 * edit_distance(lower, candidate) + .7 * frequency
                        + (.6 if candidate in ocr_choices else 0) + (1.0 if candidate in dictionary_choices else 0))
            candidates = tuple(sorted(choices, key=lambda c: (-score(c), c))[:6])
            if not candidates and len(lower) >= 6:
                splits = [lower[:i] + ' ' + lower[i:] for i in range(2, len(lower) - 2) if self.known(lower[:i]) and self.known(lower[i:])]
                candidates = tuple(splits[:6])
        if len(self.cache) > 12000:
            self.cache.clear()
        self.cache[key] = candidates
        return tuple(match_case(x, word) for x in candidates)

    def check(self, text, *, ocr=True, check_names=False, cancel=None):
        ranges = [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
        issues = []
        def protected(start, end):
            return any(start < e and end > s for s, e in ranges)
        def add(start, end, replacements, category='ocr', message='Possible OCR recognition error. Compare with the scan.', confidence=.88):
            if not protected(start, end):
                issues.append(SpellIssue(start, end, text[start:end], tuple(replacements), category, message, confidence))
        if ocr:
            for match in re.finditer(r'[ﬀﬁﬂﬃﬄﬅﬆ]|\u00ad', text):
                add(match.start(), match.end(), [LIGATURES.get(match[0], '')], confidence=.99)
            for match in re.finditer(r'([A-Za-z]{2,})-[ \t]*\r?\n[ \t]*([A-Za-z]{2,})', text):
                joined = match[1] + match[2]
                if self.known(joined):
                    add(match.start(), match.end(), [joined], message='Join a word split across a printed line ending.', confidence=.94)
        occupied = [(i.start, i.end) for i in issues]
        for index, token in enumerate(TOKEN.finditer(text)):
            if index % 128 == 0 and cancel is not None and cancel.is_set():
                return []
            word, start, end = token[0], token.start(), token.end()
            lower = word.casefold().replace('’', "'")
            if not 2 <= len(word) <= 48 or protected(start, end) or any(start < e and end > s for s, e in occupied):
                continue
            if not any(c.isalpha() for c in word) or word.isupper():
                continue
            if word in self.personal or lower in self.personal:
                continue
            if self.known(lower) and lower not in COMMON_TYPOS:
                continue
            # Ordinary capitalized names are reviewable with check_names=True;
            # do not silently rewrite the book's character names by default.
            if not check_names and word.istitle() and lower not in COMMON_TYPOS and start > 0 and not re.search(r'[.!?]\s*$', text[max(0, start - 6):start]):
                continue
            suggestions = self.suggest(word, ocr=ocr)
            confidence = .98 if lower in COMMON_TYPOS else .87
            category = 'ocr' if ocr and (any(c.isdigit() or c in '|¦' for c in word) or self._ocr_candidates(lower)) else 'spelling'
            add(start, end, suggestions, category, 'Choose the intended spelling; add names or specialist terms to the personal dictionary.', confidence)
        return sorted(issues, key=lambda i: (i.start, -i.confidence))


def apply_corrections(text, issues, *, safe_only=False):
    """Proofloom applyEdits port: reject stale and overlapping replacements."""
    selected = []
    for issue in sorted(issues, key=lambda i: (-i.confidence, i.start)):
        if not issue.suggestions or (safe_only and not issue.safe) or text[issue.start:issue.end] != issue.original:
            continue
        if not any(issue.start < other.end and issue.end > other.start for other in selected):
            selected.append(issue)
    for issue in sorted(selected, key=lambda i: i.start, reverse=True):
        text = text[:issue.start] + issue.suggestions[0] + text[issue.end:]
    return text, len(selected)
