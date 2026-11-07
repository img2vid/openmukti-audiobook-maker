"""Editorial proofreading reports for audiobook manuscripts.

All checks are offline, deterministic heuristics that report suspicious
passages for human review; none of them rewrites text automatically.
Covers proper-name consistency, dialogue punctuation, OCR punctuation
artifacts, readability statistics, cross-chapter terminology consistency
and pronunciation audits.
"""
from __future__ import annotations
import re
import unicodedata
from collections import Counter

_WORD = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
_SENTENCE_END = re.compile(r'[.!?。！？]+')
_NAME_TOKEN = re.compile(r"\b[A-ZÀ-Þ][\w’'-]{2,}\b")

# Words that are legitimately capitalized at sentence starts; excluded from
# name-consistency clusters unless they appear mid-sentence capitalized.
_COMMON_CAPITALIZED = {
    'the', 'a', 'an', 'and', 'but', 'or', 'if', 'when', 'then', 'that', 'this', 'these',
    'those', 'there', 'here', 'it', 'its', 'he', 'she', 'they', 'we', 'i', 'you', 'in',
    'on', 'at', 'as', 'of', 'to', 'for', 'with', 'by', 'from', 'after', 'before', 'not',
    'no', 'yes', 'now', 'so', 'up', 'down', 'out', 'off', 'over', 'under', 'again',
    'once', 'still', 'just', 'only', 'very', 'how', 'what', 'who', 'why', 'which',
    'chapter', 'part', 'book', 'said', 'mr', 'mrs', 'ms', 'dr', 'st',
}


def _edit_distance(a: str, b: str, limit: int = 2) -> int:
    """Optimal string alignment distance (Levenshtein plus adjacent
    transpositions, so ``Elais``/``Elias`` count as one typo)."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    rows = [list(range(len(b) + 1))]
    for i, ca in enumerate(a, 1):
        current = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            value = min(rows[-1][j] + 1, current[j - 1] + 1, rows[-1][j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                value = min(value, rows[-2][j - 2] + cost)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        rows.append(current)
    return rows[-1][-1]


def proper_name_consistency(text: str, *, min_occurrences: int = 2) -> list[dict]:
    """Cluster similar capitalized names and report inconsistent spellings.

    Names like ``Elias``/``Elisa`` or ``MacDonald``/``McDonald`` are grouped
    when their edit distance is small, so a proofreader can check whether
    the variants are intentional characters or typos.
    """
    counts: Counter[str] = Counter()
    for match in _NAME_TOKEN.finditer(text):
        token = match.group()
        if token.casefold() in _COMMON_CAPITALIZED:
            continue
        counts[token] += 1
    clusters: list[dict] = []
    assigned: set[str] = set()
    ordered = sorted(counts, key=lambda n: (-counts[n], n))
    for name in ordered:
        if name in assigned or counts[name] < min_occurrences:
            continue
        group = [name]
        assigned.add(name)
        for other in ordered:
            if other in assigned:
                continue
            folded_a, folded_b = name.casefold(), other.casefold()
            if folded_a == folded_b:
                group.append(other)
                assigned.add(other)
                continue
            limit = 1 if min(len(folded_a), len(folded_b)) <= 6 else 2
            if _edit_distance(folded_a, folded_b, limit) <= limit:
                group.append(other)
                assigned.add(other)
        if len(group) > 1:
            clusters.append({'variants': [{'name': g, 'count': counts[g]} for g in
                                          sorted(group, key=lambda n: (-counts[n], n))],
                             'suggestion': max(group, key=lambda n: counts[n])})
    return clusters


_QUOTE_PAIRS = {'"': '"', '“': '”', '‘': '’', '«': '»'}


def dialogue_punctuation_issues(text: str) -> list[dict]:
    """Report paragraphs with unbalanced quotation marks or missing
    punctuation inside closing quotes — common OCR and typing errors."""
    issues = []
    for number, paragraph in enumerate(re.split(r'\n\s*\n', text), 1):
        if not paragraph.strip():
            continue
        for opening, closing in _QUOTE_PAIRS.items():
            if opening == closing:
                if paragraph.count(opening) % 2:
                    issues.append({'paragraph': number, 'issue': 'unbalanced straight quotes',
                                   'excerpt': paragraph.strip()[:80]})
            else:
                opens = paragraph.count(opening)
                closes = paragraph.count(closing)
                if opens != closes:
                    issues.append({'paragraph': number,
                                   'issue': f'unbalanced quotes: {opens} {opening} vs {closes} {closing}',
                                   'excerpt': paragraph.strip()[:80]})
        # A closing quote directly after a word character, with no sentence
        # punctuation inside the quote, often means a dropped period.
        for match in re.finditer(r'\w["”’»](?=\s|$)', paragraph):
            before = paragraph[:match.start() + 1]
            last_open = max(before.rfind('"'), before.rfind('“'), before.rfind('«'))
            inner = before[last_open + 1:] if last_open >= 0 else before
            inner = inner.rstrip('"”’»')
            if inner.strip() and not re.search(r'[.!?,;:…—]$', inner):
                issues.append({'paragraph': number,
                               'issue': 'closing quote without sentence punctuation inside',
                               'excerpt': paragraph.strip()[:80]})
                break
    return issues


_OCR_PUNCT_PATTERNS = [
    ('space before punctuation', re.compile(r'\w\s+[,.;:!?]')),
    ('doubled terminal punctuation', re.compile(r'[!?]{3,}|(?<!\.)\.{2}(?!\.)')),
    ('digit inside a word', re.compile(r'\b[A-Za-z]+[0-9]+[A-Za-z]+\b')),
    ('single letter word that may be OCR noise', re.compile(r'(?<!\w)[bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ](?!\w)')),
    ('pipe or tilde used as a letter', re.compile(r'(?<=\w)[|~](?=\w)|(?<=\s)[|~](?=\w)')),
]


def ocr_punctuation_report(text: str, *, max_per_kind: int = 10) -> list[dict]:
    """List punctuation and character artifacts commonly introduced by OCR."""
    findings = []
    for label, pattern in _OCR_PUNCT_PATTERNS:
        matches = []
        for match in pattern.finditer(text):
            line = text.count('\n', 0, match.start()) + 1
            matches.append({'line': line, 'excerpt': text[max(0, match.start() - 25):match.end() + 25].replace('\n', ' ')})
            if len(matches) >= max_per_kind:
                break
        if matches:
            findings.append({'issue': label, 'occurrences': len(matches), 'examples': matches})
    return findings


def _syllables(word: str) -> int:
    """Rough English syllable estimate used only for readability scoring."""
    word = re.sub(r'[^a-z]', '', word.casefold())
    if not word:
        return 1
    groups = re.findall(r'[aeiouy]+', word)
    count = len(groups)
    if word.endswith('e') and not word.endswith(('le', 'ee', 'ye')) and count > 1:
        count -= 1
    return max(1, count)


def readability(text: str) -> dict:
    """Readability and rhythm statistics for review before narration."""
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
    words = _WORD.findall(text)
    if not words:
        raise ValueError('Text contains no words')
    syllables = sum(_syllables(w) for w in words)
    n_sent = max(1, len(sentences))
    n_words = len(words)
    per_sentence = n_words / n_sent
    per_word = syllables / n_words
    flesch = 206.835 - 1.015 * per_sentence - 84.6 * per_word
    grade = 0.39 * per_sentence + 11.8 * per_word - 15.59
    lengths = sorted((len(_WORD.findall(s)) for s in sentences), reverse=True)
    vocabulary = Counter(w.casefold() for w in words)
    return {
        'sentences': n_sent, 'words': n_words, 'syllables': syllables,
        'mean_words_per_sentence': round(per_sentence, 2),
        'mean_syllables_per_word': round(per_word, 3),
        'flesch_reading_ease': round(flesch, 1),
        'flesch_kincaid_grade': round(grade, 1),
        'lexical_diversity': round(len(vocabulary) / n_words, 3),
        'longest_sentences_words': lengths[:5],
        'long_sentence_share': round(sum(1 for n in lengths if n > 25) / n_sent, 3),
    }


def terminology_consistency(chapters: dict[str, str], *, min_occurrences: int = 3) -> list[dict]:
    """Find terms whose spelling or casing differs across chapters.

    ``chapters`` maps chapter titles to their text. Variants of the same
    folded term (``the Order`` vs ``the order``) that appear in different
    chapters are reported with per-chapter counts.
    """
    per_chapter: dict[str, Counter[str]] = {}
    for title, text in chapters.items():
        counts: Counter[str] = Counter()
        for match in re.finditer(r"\b[A-Za-zÀ-ÿ][\w’'-]{3,}\b", text):
            counts[match.group()] += 1
        per_chapter[title] = counts
    folded: dict[str, dict[str, dict[str, int]]] = {}
    for title, counts in per_chapter.items():
        for term, n in counts.items():
            if n < min_occurrences and sum(c.get(term, 0) for c in per_chapter.values()) < min_occurrences:
                continue
            folded.setdefault(term.casefold(), {}).setdefault(term, {})[title] = n
    report = []
    for key, variants in folded.items():
        if len(variants) < 2:
            continue
        chapter_sets = {frozenset(where) for where in variants.values()}
        report.append({'term': key,
                       'variants': [{'form': form, 'chapters': where} for form, where in
                                    sorted(variants.items(), key=lambda kv: -sum(kv[1].values()))],
                       'appears_in_distinct_chapter_sets': len(chapter_sets) > 1})
    report.sort(key=lambda r: -sum(sum(v['chapters'].values()) for v in r['variants']))
    return report


def pronunciation_audit(text: str, dictionary_words: set[str] | None = None,
                        override_words: set[str] | None = None) -> dict:
    """List words likely to need pronunciation review.

    Flags long words, words with unusual internal capitals, hyphenated
    coinages, numbers embedded in words, and words absent from the supplied
    dictionary. Words covered by an existing pronunciation override are
    listed separately so reviewers can see what is already handled.
    """
    dictionary_words = {w.casefold() for w in (dictionary_words or set())}
    override_words = {w.casefold() for w in (override_words or set())}
    difficult: Counter[str] = Counter()
    covered: Counter[str] = Counter()
    for match in _WORD.finditer(text):
        word = match.group()
        folded = word.casefold()
        hard = (len(word) >= 13
                or re.search(r'[a-z][A-Z]', word) is not None
                or ('-' in word and len(word) >= 8)
                or any(c.isdigit() for c in word)
                or (dictionary_words and folded not in dictionary_words and len(word) >= 6))
        if hard:
            (covered if folded in override_words else difficult)[word] += 1
    def top(counter: Counter[str]) -> list[dict]:
        return [{'word': w, 'count': n} for w, n in
                sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:100]]
    return {'difficult_words': top(difficult),
            'covered_by_overrides': top(covered),
            'unique_difficult': len(difficult), 'unique_covered': len(covered)}
