from __future__ import annotations
import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class TextTool:
    name: str
    title: str
    group: str
    apply: Callable[[str], str]
TOOLS: dict[str, TextTool] = {}

def add(name: str, title: str, group: str, fn: Callable[[str], str]) -> None:
    if name in TOOLS:
        raise ValueError(f'Duplicate tool: {name}')
    TOOLS[name] = TextTool(name, title, group, fn)

def rx(pattern: str, replacement: str, flags: int=0) -> Callable[[str], str]:
    compiled = re.compile(pattern, flags)
    return lambda value: compiled.sub(replacement, value)

def lines(text: str, fn: Callable[[list[str]], list[str]]) -> str:
    return '\n'.join(fn(text.splitlines()))

def replace_all(mapping: dict[str, str]) -> Callable[[str], str]:
    table = str.maketrans(mapping)
    return lambda text: text.translate(table)

def keep_first(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))

def strip_punctuation(value: str) -> str:
    return ''.join((c for c in value if not unicodedata.category(c).startswith('P')))

def strip_symbols(value: str) -> str:
    return ''.join((c for c in value if not unicodedata.category(c).startswith('S')))

def strip_diacritics(value: str) -> str:
    return ''.join((c for c in unicodedata.normalize('NFD', value) if unicodedata.category(c) != 'Mn'))

def split_sentences(value: str) -> list[str]:
    return [x.strip() for x in re.split('(?<=[.!?。！？])\\s+', value.strip()) if x.strip()]

def sentence_case(value: str) -> str:
    return re.sub('(^|(?<=[.!?])\\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), value.lower())

def smart_sentences(value: str) -> str:
    return '\n'.join(split_sentences(value))

def sentence_list(value: str) -> str:
    return '\n'.join((f'{i}. {x}' for i, x in enumerate(split_sentences(value), 1)))

def number_words(value: str) -> str:
    names = ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen', 'twenty')
    return re.sub('(?<!\\w)\\d{1,2}(?!\\w)', lambda m: names[int(m.group())] if int(m.group()) <= 20 else m.group(), value)

def letter_by_letter(value: str) -> str:
    return re.sub('\\b[A-Z]{2,}\\b', lambda m: ' '.join(m.group()), value)

def remove_bracketed(value: str, opening: str, closing: str) -> str:
    return re.sub(re.escape(opening) + '[^' + re.escape(closing) + ']*' + re.escape(closing), '', value)

def strip_markup(value: str) -> str:
    value = re.sub('(?s)<(script|style)\\b[^>]*>.*?</\\1\\s*>', ' ', value, flags=re.I)
    return html.unescape(re.sub('<[^>]+>', ' ', value))

def strip_markdown(value: str) -> str:
    value = re.sub('!?\\[([^]]+)\\]\\([^)]+\\)', '\\1', value)
    value = re.sub('(?m)^\\s{0,3}(?:#{1,6}\\s+|>\\s+|[-*+]\\s+|\\d+[.)]\\s+)', '', value)
    return re.sub('(?<!\\w)[*_~`]{1,3}|[*_~`]{1,3}(?!\\w)', '', value)

def strip_subtitle_timing(value: str) -> str:
    value = re.sub('(?m)^\\s*\\d\\d:\\d\\d:\\d\\d[,.]\\d+\\s*-->[^\\n]*\\n?', '', value)
    value = re.sub('(?m)^\\s*\\d\\d:\\d\\d[,.]\\d+\\s*-->[^\\n]*\\n?', '', value)
    return re.sub('(?m)^\\s*\\d+\\s*$', '', value)

def strip_repeated_headers(value: str) -> str:
    pages = re.split('\\f|\\n\\s*---\\s*PAGE\\s*---\\s*\\n', value, flags=re.I)
    if len(pages) < 2:
        return value
    heads = [next((x.strip() for x in p.splitlines() if x.strip()), '') for p in pages]
    recurring = {h for h in heads if h and heads.count(h) > 1}
    return '\n\n'.join((re.sub('^\\s*' + re.escape(heads[i]) + '\\s*\\n?', '', p, count=1) if heads[i] in recurring else p for i, p in enumerate(pages)))

def quoted_phrases(value: str) -> str:
    return '\n'.join(re.findall('[“"]([^”"]+)[”"]', value))

def unquoted_phrases(value: str) -> str:
    return re.sub('[“"][^”"]+[”"]', '', value)

def only_numbers(value: str) -> str:
    return '\n'.join(re.findall('\\b\\d+(?:[.,]\\d+)*\\b', value))

def only_urls(value: str) -> str:
    return '\n'.join(re.findall('https?://[^\\s<>()]+', value))

def only_emails(value: str) -> str:
    return '\n'.join(re.findall('\\b[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}\\b', value))

def only_headings(value: str) -> str:
    return '\n'.join(re.findall('(?m)^#{1,6}\\s+(.+)$', value))

def only_paragraph_starts(value: str) -> str:
    return '\n'.join((p.strip().splitlines()[0] for p in re.split('\\n\\s*\\n', value) if p.strip()))

def only_lines_containing(value: str, matcher: str) -> str:
    return '\n'.join((s for s in value.splitlines() if re.search(matcher, s)))
for name, title, fn in [('unicode-nfc', 'Unicode NFC composition', lambda x: unicodedata.normalize('NFC', x)), ('unicode-nfkc', 'Unicode NFKC compatibility', lambda x: unicodedata.normalize('NFKC', x)), ('unicode-nfd', 'Unicode NFD decomposition', lambda x: unicodedata.normalize('NFD', x)), ('unicode-nfkd', 'Unicode NFKD decomposition', lambda x: unicodedata.normalize('NFKD', x)), ('remove-diacritics', 'Remove combining accents', strip_diacritics), ('remove-control', 'Remove control characters', lambda x: ''.join((c for c in x if c in '\n\t' or unicodedata.category(c) != 'Cc'))), ('remove-bom', 'Remove byte order markers', lambda x: x.replace('\ufeff', '')), ('remove-zero-width', 'Remove zero-width characters', rx('[\u200b\u200c\u200d\u2060]', '')), ('normalize-spaces', 'Convert uncommon spaces', rx('[\xa0\u2000-\u200a\u202f\u205f\u3000]', ' ')), ('unix-newlines', 'Convert to Unix line endings', lambda x: x.replace('\r\n', '\n').replace('\r', '\n')), ('windows-newlines', 'Convert to Windows line endings', lambda x: x.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')), ('collapse-whitespace', 'Collapse spaces and tabs', rx('[ \\t]{2,}', ' ')), ('collapse-newlines', 'Collapse multiple blank lines', rx('\\n{3,}', '\n\n')), ('all-one-line', 'Convert to one paragraph', rx('\\s+', ' ')), ('trim', 'Trim start and end', str.strip), ('trim-left', 'Trim leading whitespace', str.lstrip), ('trim-right', 'Trim trailing whitespace', str.rstrip), ('tabs-to-spaces', 'Replace tabs with four spaces', lambda x: x.expandtabs(4)), ('spaces-to-tabs', 'Replace four spaces with tabs', lambda x: x.replace('    ', '\t')), ('remove-trailing-spaces', 'Trim whitespace at line ends', rx('(?m)[ \\t]+$', '')), ('remove-leading-spaces', 'Remove line indentation', rx('(?m)^[ \\t]+', '')), ('remove-soft-hyphens', 'Remove discretionary hyphens', lambda x: x.replace('\xad', '')), ('remove-formfeeds', 'Remove page-break controls', lambda x: x.replace('\x0c', '\n\n')), ('remove-non-ascii', 'Remove non-ASCII characters', lambda x: x.encode('ascii', 'ignore').decode('ascii')), ('ascii-fold', 'ASCII-fold Latin characters', lambda x: unicodedata.normalize('NFKD', x).encode('ascii', 'ignore').decode('ascii'))]:
    add(name, title, 'Unicode and whitespace', fn)
for name, title, fn in [('trim-lines', 'Trim each line', lambda x: lines(x, lambda a: [v.strip() for v in a])), ('drop-blank-lines', 'Remove empty lines', lambda x: lines(x, lambda a: [v for v in a if v.strip()])), ('unique-lines', 'Deduplicate lines, retaining order', lambda x: lines(x, keep_first)), ('unique-lines-casefold', 'Deduplicate lines regardless of case', lambda x: lines(x, lambda a: list({s.casefold(): s for s in a}.values()))), ('sort-lines', 'Sort lines A to Z', lambda x: lines(x, sorted)), ('sort-lines-reverse', 'Sort lines Z to A', lambda x: lines(x, lambda a: sorted(a, reverse=True))), ('sort-lines-casefold', 'Sort lines ignoring case', lambda x: lines(x, lambda a: sorted(a, key=str.casefold))), ('sort-lines-length', 'Sort lines by length', lambda x: lines(x, lambda a: sorted(a, key=len))), ('reverse-lines', 'Reverse line order', lambda x: lines(x, lambda a: list(reversed(a)))), ('reverse-words', 'Reverse word order', lambda x: ' '.join(reversed(x.split()))), ('number-lines', 'Number every line', lambda x: lines(x, lambda a: [f'{i}. {v}' for i, v in enumerate(a, 1)])), ('remove-line-numbers', 'Remove line numbers', rx('(?m)^\\s*\\d+[.)]\\s+', '')), ('bullet-lines', 'Add bullet to each line', lambda x: lines(x, lambda a: ['• ' + v for v in a])), ('remove-bullets', 'Remove bullet prefixes', rx('(?m)^\\s*[-*•+◦]\\s+', '')), ('lines-to-commas', 'Join lines using commas', lambda x: ', '.join((v.strip() for v in x.splitlines() if v.strip()))), ('commas-to-lines', 'Split comma-separated items', rx('\\s*,\\s*', '\n')), ('semicolons-to-lines', 'Split at semicolons', rx('\\s*;\\s*', '\n')), ('lines-to-semicolons', 'Join lines with semicolons', lambda x: '; '.join((v.strip() for v in x.splitlines() if v.strip()))), ('sentences-to-lines', 'Put each sentence on its own line', smart_sentences), ('number-sentences', 'Number each sentence', sentence_list), ('first-line-each-paragraph', 'Extract first line of paragraphs', only_paragraph_starts), ('remove-page-numbers', 'Remove standalone page numbers', rx('(?m)^\\s*(?:page\\s*)?\\d{1,5}\\s*$', '', re.I)), ('remove-roman-page-numbers', 'Remove Roman-numeral page numbers', rx('(?m)^\\s*[ivxlcdm]{1,8}\\s*$', '', re.I)), ('remove-repeated-headers', 'Remove repeated page headers', strip_repeated_headers), ('paragraphs-to-one-line', 'Join lines within paragraphs', lambda x: '\n\n'.join((' '.join(p.splitlines()) for p in re.split('\\n\\s*\\n', x)))), ('paragraphs-to-lines', 'Separate paragraphs with one newline', rx('\\n\\s*\\n+', '\n'))]:
    add(name, title, 'Lines and paragraphs', fn)
for name, title, fn in [('lowercase', 'Convert to lowercase', str.lower), ('uppercase', 'Convert to uppercase', str.upper), ('title-case', 'Capitalize as titles', str.title), ('sentence-case', 'Capitalize sentence beginnings', sentence_case), ('casefold', 'Unicode case folding', str.casefold), ('swap-case', 'Swap uppercase and lowercase', str.swapcase), ('capitalize', 'Capitalize first character', str.capitalize), ('normalize-quotes', 'Normalize curly quotations', replace_all({'“': '"', '”': '"', '„': '"', '«': '"', '»': '"', '‘': "'", '’': "'", '‚': "'"})), ('normalize-dashes', 'Normalize Unicode dashes', replace_all({'—': '-', '–': '-', '−': '-', '‐': '-', '‑': '-'})), ('expand-ellipsis', 'Replace ellipsis with dots', lambda x: x.replace('…', '...')), ('collapse-ellipsis', 'Replace three dots with ellipsis', rx('\\.{3,}', '…')), ('normalize-exclamation', 'Collapse repeated exclamations', rx('!{2,}', '!')), ('normalize-questions', 'Collapse repeated question marks', rx('\\?{2,}', '?')), ('normalize-commas', 'Collapse repeated commas', rx(',{2,}', ',')), ('normalize-periods', 'Collapse repeated periods', rx('\\.{4,}', '...')), ('punctuation-spaces', 'Remove spaces before punctuation', rx('\\s+([,.;:!?])', '\\1')), ('space-after-commas', 'Ensure space after commas', rx(',(?!\\s|\\d|$)', ', ')), ('space-after-semicolons', 'Ensure space after semicolons', rx(';(?!\\s|$)', '; ')), ('space-after-colons', 'Ensure space after colons', rx(':(?!\\s|/|\\d|$)', ': ')), ('remove-commas', 'Remove commas', lambda x: x.replace(',', '')), ('remove-semicolons', 'Remove semicolons', lambda x: x.replace(';', '')), ('remove-colons', 'Remove colons', lambda x: x.replace(':', '')), ('remove-parentheses', 'Remove parentheses only', replace_all({'(': '', ')': ''})), ('remove-brackets', 'Remove square brackets only', replace_all({'[': '', ']': ''})), ('remove-punctuation', 'Remove all punctuation', strip_punctuation), ('remove-symbols', 'Remove symbols', strip_symbols), ('remove-emoji', 'Remove most pictographic emoji', lambda x: ''.join((c for c in x if not (126976 <= ord(c) <= 129791 or 9728 <= ord(c) <= 10175)))), ('remove-empty-parentheses', 'Remove empty parentheses', rx('\\(\\s*\\)', '')), ('remove-empty-brackets', 'Remove empty brackets', rx('\\[\\s*\\]', ''))]:
    add(name, title, 'Case and punctuation', fn)
for name, title, fn in [('strip-html', 'Remove HTML tags and decode entities', strip_markup), ('decode-html', 'Decode HTML entities', html.unescape), ('escape-html', 'Escape HTML entities', html.escape), ('strip-markdown', 'Remove Markdown formatting', strip_markdown), ('remove-markdown-images', 'Remove Markdown image references', rx('!\\[[^]]*\\]\\([^)]+\\)', '')), ('strip-markdown-links', 'Keep labels of Markdown links', rx('\\[([^]]+)\\]\\([^)]+\\)', '\\1')), ('remove-markdown-fences', 'Remove Markdown code fences', rx('(?m)^\\s*`{3,}.*$', '')), ('remove-markdown-headings', 'Remove Markdown heading markers', rx('(?m)^\\s*#{1,6}\\s+', '')), ('headings-only', 'Extract Markdown headings', only_headings), ('remove-code-blocks', 'Remove fenced code blocks', rx('(?ms)^\\s*`{3,}[^\\n]*\\n.*?^\\s*`{3,}[^\\n]*$', '')), ('remove-xml-tags', 'Remove XML tags', rx('<[^>]+>', ' ')), ('remove-srt-timing', 'Remove subtitle timestamps', strip_subtitle_timing), ('remove-vtt-header', 'Remove WEBVTT header', rx('(?m)^\\s*WEBVTT[^\\n]*\\n?', '')), ('remove-web-links', 'Remove HTTP addresses', rx('https?://[^\\s<>()]+', '', re.I)), ('remove-email-addresses', 'Remove email addresses', rx('\\b[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}\\b', '')), ('extract-web-links', 'Extract HTTP addresses', only_urls), ('extract-email-addresses', 'Extract email addresses', only_emails), ('extract-numbers', 'Extract numbers', only_numbers), ('extract-quoted-phrases', 'Extract quoted phrases', quoted_phrases), ('remove-quoted-phrases', 'Remove quoted phrases', unquoted_phrases), ('remove-urls-and-emails', 'Remove URLs and email addresses', lambda x: TOOLS['remove-web-links'].apply(TOOLS['remove-email-addresses'].apply(x)))]:
    add(name, title, 'Markup and extraction', fn)
for name, title, fn in [('ocr-fix-hyphenated-lines', 'Join hyphenated OCR line breaks', rx('(?<=[a-z])[-\\u00ad]\\s*\\n\\s*(?=[a-z])', '')), ('ocr-join-soft-lines', 'Merge soft-wrapped OCR lines', rx('(?<!\\n)\\n(?!\\n)', ' ')), ('ocr-expand-ligatures', 'Expand OCR ligatures', replace_all({'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'æ': 'ae', 'œ': 'oe'})), ('ocr-remove-form-feeds', 'Replace OCR page breaks', lambda x: x.replace('\x0c', '\n\n')), ('ocr-fix-punctuation-space', 'Repair punctuation spacing', lambda x: TOOLS['punctuation-spaces'].apply(TOOLS['space-after-commas'].apply(x))), ('ocr-remove-page-numbers', 'Strip page-number-only lines', lambda x: TOOLS['remove-page-numbers'].apply(x)), ('ocr-clean', 'Apply conservative OCR cleanup', lambda x: TOOLS['ocr-join-soft-lines'].apply(TOOLS['ocr-fix-hyphenated-lines'].apply(TOOLS['ocr-expand-ligatures'].apply(x)))), ('spell-out-small-numbers', 'Spell out 0 through 20', number_words), ('say-percent', 'Expand percent signs', rx('(?<=\\d)%', ' percent')), ('say-ampersand', 'Speak ampersands as and', rx('\\s*&\\s*', ' and ')), ('say-at', 'Speak @ as at', lambda x: x.replace('@', ' at ')), ('say-hash', 'Speak hashtag symbols as hash', lambda x: x.replace('#', ' hash ')), ('say-plus', 'Speak plus signs', rx('(?<=\\d)\\s*\\+\\s*(?=\\d)', ' plus ')), ('say-equals', 'Speak equals signs', lambda x: x.replace('=', ' equals ')), ('say-multiplication', 'Speak multiplication symbols', lambda x: x.replace('×', ' times ')), ('say-division', 'Speak division symbols', lambda x: x.replace('÷', ' divided by ')), ('say-degrees', 'Speak degree symbols', lambda x: x.replace('°C', ' degrees Celsius').replace('°F', ' degrees Fahrenheit').replace('°', ' degrees')), ('say-currency', 'Expand common currency symbols', replace_all({'$': ' dollars ', '€': ' euros ', '£': ' pounds ', '¥': ' yen ', '₹': ' rupees '})), ('say-fractions', 'Expand fraction glyphs', replace_all({'½': ' one half ', '¼': ' one quarter ', '¾': ' three quarters ', '⅓': ' one third ', '⅔': ' two thirds '})), ('say-common-abbreviations', 'Expand common English abbreviations', lambda x: re.sub('\\b(?:Mr|Mrs|Dr|Prof|St|Ave)\\.(?=\\s|$)', lambda m: {'Mr.': 'Mister', 'Mrs.': 'Missus', 'Dr.': 'Doctor', 'Prof.': 'Professor', 'St.': 'Street', 'Ave.': 'Avenue'}[m.group()], x)), ('spell-acronyms', 'Separate capital-letter acronyms', letter_by_letter), ('pause-at-commas', 'Add line breaks after commas', rx(',\\s*', ',\n')), ('pause-at-semicolons', 'Add line breaks after semicolons', rx(';\\s*', ';\n')), ('pause-at-colons', 'Add line breaks after colons', rx(':\\s*', ':\n')), ('pause-at-dashes', 'Add line breaks after em dashes', rx('—\\s*', '—\n')), ('remove-stage-directions', 'Remove parenthetical stage directions', lambda x: remove_bracketed(x, '[', ']')), ('remove-parenthetical-asides', 'Remove parenthesized passages', lambda x: remove_bracketed(x, '(', ')')), ('remove-repeated-words', 'Remove repeated adjacent words', rx('\\b(\\w+)(?:\\s+\\1\\b)+', '\\1', re.I)), ('remove-filler-ums', 'Remove um and uh fillers', rx('\\b(?:um+|uh+)\\b[, ]*', '', re.I))]:
    add(name, title, 'Speech and OCR', fn)

def transform(text: str, operations: list[str] | tuple[str, ...]) -> str:
    for operation in operations:
        if operation not in TOOLS:
            raise ValueError(f'Unknown text tool: {operation}')
        text = TOOLS[operation].apply(text)
    return text

def text_stats(text: str, wpm: int=160) -> dict:
    if wpm < 1:
        raise ValueError('WPM must be positive')
    words = re.findall("\\b[\\w’'-]+\\b", text, flags=re.UNICODE)
    counts = {}
    for word in words:
        key = word.casefold()
        counts[key] = counts.get(key, 0) + 1
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    occurrences = {}
    for number, paragraph in enumerate(paragraphs, 1):
        occurrences.setdefault(' '.join(paragraph.casefold().split()), []).append(number)
    return {'duplicate_paragraph_numbers': [group for group in occurrences.values() if len(group) > 1],
            'mean_words_per_sentence': round(len(words) / max(1, len(split_sentences(text))), 1),
            'characters': len(text), 'characters_no_spaces': len(re.sub('\\s', '', text)), 'lines': len(text.splitlines()), 'paragraphs': len([p for p in re.split('\\n\\s*\\n', text) if p.strip()]), 'words': len(words), 'unique_words': len(counts), 'sentences': len(split_sentences(text)), 'estimated_seconds': round(60 * len(words) / wpm, 2), 'longest_word': max(words, key=len, default=''), 'top_words': sorted(counts.items(), key=lambda p: (-p[1], p[0]))[:20]}
