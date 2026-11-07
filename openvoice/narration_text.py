"""Speech-oriented text preparation for narration.

Converts written conventions into forms text-to-speech engines read aloud
correctly: abbreviation expansion, number narration (cardinal, ordinal,
year, digit-by-digit), date and time pronunciation, and interpretation of
ellipses and dashes as configurable pauses. The transformations are also
registered as text tools, so the ``transform`` command and the GUI text
pipeline can apply them like any other cleanup.
"""
from __future__ import annotations
import re
from .texttools import add

# --- abbreviations ------------------------------------------------------

DEFAULT_ABBREVIATIONS = {
    'mr.': 'Mister', 'mrs.': 'Missus', 'ms.': 'Ms', 'dr.': 'Doctor', 'prof.': 'Professor',
    'st.': 'Saint', 'mt.': 'Mount', 'rev.': 'Reverend', 'fr.': 'Father', 'sr.': 'Senior',
    'jr.': 'Junior', 'gen.': 'General', 'capt.': 'Captain', 'lt.': 'Lieutenant',
    'col.': 'Colonel', 'sgt.': 'Sergeant', 'cmdr.': 'Commander', 'adm.': 'Admiral',
    'hon.': 'Honorable', 'pres.': 'President', 'gov.': 'Governor', 'sen.': 'Senator',
    'rep.': 'Representative', 'det.': 'Detective', 'insp.': 'Inspector',
    'e.g.': 'for example', 'i.e.': 'that is', 'etc.': 'et cetera', 'vs.': 'versus',
    'viz.': 'namely', 'cf.': 'compare', 'ibid.': 'in the same place', 'n.b.': 'note well',
    'a.m.': 'A M', 'p.m.': 'P M', 'vol.': 'volume',
    'ch.': 'chapter', 'pp.': 'pages', 'ed.': 'edition', 'eds.': 'editors',
    'approx.': 'approximately', 'appt.': 'appointment', 'dept.': 'department',
    'est.': 'established', 'inc.': 'Incorporated', 'ltd.': 'Limited',
    'corp.': 'Corporation', 'ave.': 'Avenue', 'blvd.': 'Boulevard', 'rd.': 'Road',
    'apt.': 'Apartment', 'ft.': 'feet', 'cm.': 'centimeters',
    'mm.': 'millimeters', 'km.': 'kilometers', 'kg.': 'kilograms', 'lb.': 'pounds',
    'lbs.': 'pounds', 'oz.': 'ounces', 'hr.': 'hour', 'hrs.': 'hours', 'min.': 'minutes',
    'sec.': 'seconds', 'jan.': 'January', 'feb.': 'February', 'mar.': 'March',
    'apr.': 'April', 'jun.': 'June', 'jul.': 'July', 'aug.': 'August', 'sep.': 'September',
    'sept.': 'September', 'oct.': 'October', 'nov.': 'November', 'dec.': 'December',
}


def expand_abbreviations(text: str, rules: dict[str, str] | None = None) -> str:
    """Expand abbreviations using user rules over sensible defaults.

    Matching is case-insensitive on word boundaries; the expansion keeps the
    capitalization of the original token. A trailing period that ends a
    sentence is preserved for sentence-final abbreviations like ``etc.``
    """
    table = dict(DEFAULT_ABBREVIATIONS)
    for key, value in (rules or {}).items():
        key = str(key).strip().casefold()
        if not key:
            raise ValueError('Abbreviation rules must not contain empty keys')
        # Custom keys match exactly as written: 'OTP' matches OTP, while a
        # dotted 'assn.' matches the dotted form only.
        table[key] = str(value).strip()
    def replace(match: re.Match) -> str:
        original = match.group()
        expansion = table[original.casefold()]
        # Capitalize only sentence-style tokens (Dr. → Doctor); acronyms like
        # OTP keep the expansion's own capitalization.
        if original[:1].isupper() and not original.rstrip('.').isupper():
            expansion = expansion[:1].upper() + expansion[1:]
        return expansion
    if not table:
        return text
    pattern = re.compile(r'\b(?:' + '|'.join(re.escape(k) for k in
                         sorted(table, key=len, reverse=True)) + r')', re.I)
    return pattern.sub(replace, text)


# --- numbers ------------------------------------------------------------

_ONES = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
         'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
         'seventeen', 'eighteen', 'nineteen']
_TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
_SCALES = [(10 ** 12, 'trillion'), (10 ** 9, 'billion'), (10 ** 6, 'million'), (10 ** 3, 'thousand')]


def number_to_words(value: int) -> str:
    """Convert an integer up to the trillions into English words."""
    if not isinstance(value, int) or abs(value) > 999_999_999_999_999:
        raise ValueError('Number narration supports integers up to the hundreds of trillions')
    if value < 0:
        return 'negative ' + number_to_words(-value)
    if value < 20:
        return _ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        return _TENS[tens] + (('-' + _ONES[rest]) if rest else '')
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return _ONES[hundreds] + ' hundred' + ((' ' + number_to_words(rest)) if rest else '')
    for scale, name in _SCALES:
        if value >= scale:
            head, rest = divmod(value, scale)
            return number_to_words(head) + ' ' + name + ((' ' + number_to_words(rest)) if rest else '')
    raise ValueError('Number is too large')


def ordinal_to_words(value: int) -> str:
    """Convert an integer into its ordinal words (21 → twenty-first)."""
    special = {1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth', 6: 'sixth',
               7: 'seventh', 8: 'eighth', 9: 'ninth', 10: 'tenth', 11: 'eleventh',
               12: 'twelfth', 13: 'thirteenth', 14: 'fourteenth', 15: 'fifteenth',
               16: 'sixteenth', 17: 'seventeenth', 18: 'eighteenth', 19: 'nineteenth',
               20: 'twentieth', 30: 'thirtieth', 40: 'fortieth', 50: 'fiftieth',
               60: 'sixtieth', 70: 'seventieth', 80: 'eightieth', 90: 'ninetieth'}
    if value in special:
        return special[value]
    words = number_to_words(value)
    if value < 100:
        head, _, tail = words.rpartition('-')
        if tail:
            return head + '-' + ordinal_to_words(int(re.sub(r'\D', '', str(value))[-1]))
    for scale_value, scale_name in _SCALES + [(100, 'hundred')]:
        if value % scale_value == 0 and value >= scale_value:
            return words + 'th'
    rest = value % 100 if value > 100 else value
    if value > 100 and rest:
        base = number_to_words(value - rest)
        return base + ' ' + ordinal_to_words(rest)
    return words + 'th'


def year_to_words(value: int) -> str:
    """Speak a year naturally: 1999 → nineteen ninety-nine, 2007 → two thousand seven."""
    if 1000 <= value <= 1999:
        head, rest = divmod(value, 100)
        return number_to_words(head) + ((' ' + number_to_words(rest)) if rest else ' hundred')
    if 2000 <= value <= 2009:
        return 'two thousand' + ((' ' + number_to_words(value - 2000)) if value > 2000 else '')
    if 2010 <= value <= 2099:
        head, rest = divmod(value, 100)
        return number_to_words(head) + ' ' + number_to_words(rest)
    return number_to_words(value)


_CURRENCY_MAJOR = {'$': 'dollar', '€': 'euro', '£': 'pound', '₹': 'rupee', '¥': 'yen'}
_ORDINAL_SUFFIX = re.compile(r'\b(\d{1,4})(st|nd|rd|th)\b', re.I)
_NUMBER = re.compile(r'(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?!\w|\.\d)')
_CURRENCY_AMOUNT = re.compile(r'([$€£₹¥])\s*(\d[\d,]*)(?:\.(\d{1,2}))?')
_PERCENT = re.compile(r'(\d+(?:\.\d+)?)\s*%')


def _speak_digits(value: str) -> str:
    return ' '.join(_ONES[int(d)] for d in value)


def speak_numbers(text: str, *, mode: str = 'cardinal', year_detection: bool = True) -> str:
    """Convert numerals to spoken words.

    ``mode`` is ``cardinal`` (42 → forty-two), ``digits`` (42 → four two,
    for telephone-style reading), or ``ordinal-aware`` which also honors
    explicit ordinal suffixes. Currency amounts, percentages, decimals and
    thousands separators are handled in every mode. With ``year_detection``,
    bare four-digit numbers in a plausible year range are read as years.
    """
    if mode not in ('cardinal', 'digits', 'ordinal-aware'):
        raise ValueError("Mode must be 'cardinal', 'digits' or 'ordinal-aware'")

    def currency(match: re.Match) -> str:
        symbol, major, minor = match.group(1), match.group(2).replace(',', ''), match.group(3)
        unit = _CURRENCY_MAJOR[symbol]
        spoken = number_to_words(int(major)) + ' ' + unit + ('s' if int(major) != 1 else '')
        if minor and int(minor):
            spoken += ' and ' + number_to_words(int(minor)) + ' cents'
        return ' ' + spoken + ' '

    def percent(match: re.Match) -> str:
        value = match.group(1)
        if '.' in value:
            whole, frac = value.split('.')
            return f' {number_to_words(int(whole))} point {_speak_digits(frac)} percent '
        return f' {number_to_words(int(value))} percent '

    def plain(match: re.Match) -> str:
        whole = match.group(1).replace(',', '')
        fraction = match.group(2)
        if mode == 'digits':
            spoken = _speak_digits(whole)
        elif year_detection and re.fullmatch(r'1[0-9]{3}|20[0-9]{2}', whole):
            spoken = year_to_words(int(whole))
        else:
            spoken = number_to_words(int(whole))
        if fraction:
            spoken += ' point ' + _speak_digits(fraction)
        return ' ' + spoken + ' '

    result = _CURRENCY_AMOUNT.sub(currency, text)
    result = _PERCENT.sub(percent, result)
    if mode == 'ordinal-aware':
        result = _ORDINAL_SUFFIX.sub(lambda m: ' ' + ordinal_to_words(int(m.group(1))) + ' ', result)
    return _NUMBER.sub(plain, result)


# --- dates and times ----------------------------------------------------

_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
           'August', 'September', 'October', 'November', 'December']
_ISO_DATE = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
_SLASH_DATE = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b')
_TEXTUAL_DATE = re.compile(r'\b(' + '|'.join(_MONTHS) + r')\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b', re.I)
_TIME = re.compile(r'\b(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b', re.I)


def _speak_time(hour: int, minute: int, ampm: str) -> str:
    if ampm:
        marker = 'A M' if ampm.lower().startswith('a') else 'P M'
        hour12 = hour % 12 or 12
        if minute == 0:
            return f'{number_to_words(hour12)} {marker}'
        return f'{number_to_words(hour12)} {number_to_words(minute) if minute >= 10 else "oh " + _ONES[minute]} {marker}'
    if minute == 0:
        return number_to_words(hour) + " o'clock"
    return f'{number_to_words(hour)} {number_to_words(minute) if minute >= 10 else "oh " + _ONES[minute]}'


def speak_dates_times(text: str, *, day_first: bool = False) -> str:
    """Convert common written dates and clock times to spoken English.

    ISO dates (2026-11-04), slash dates (11/4/2026 or 4/11/2026 with
    ``day_first``), textual dates (November 4, 2026) and times (14:30,
    2:30 PM) are covered. Ambiguous slash dates default to month-first
    unless ``day_first`` is set.
    """
    def iso(match: re.Match) -> str:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return match.group()
        return f'the {ordinal_to_words(day)} of {_MONTHS[month - 1]}, {year_to_words(year)}'

    def slash(match: re.Match) -> str:
        first, second, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if len(match.group(3)) == 2:
            year += 2000 if year < 70 else 1900
        day, month = (first, second) if day_first else (second, first)
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            return match.group()
        return f'the {ordinal_to_words(day)} of {_MONTHS[month - 1]}, {year_to_words(year)}'

    def textual(match: re.Match) -> str:
        month = _MONTHS.index(match.group(1).capitalize())
        day, year = int(match.group(2)), int(match.group(3))
        return f'the {ordinal_to_words(day)} of {_MONTHS[month]}, {year_to_words(year)}'

    def clock(match: re.Match) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 24 or minute > 59:
            return match.group()
        ampm = match.group(4) or ''
        if not ampm and hour > 12:
            return _speak_time(hour, minute, '')
        return _speak_time(hour, minute, ampm.replace('.', ''))

    result = _TEXTUAL_DATE.sub(textual, text)
    result = _ISO_DATE.sub(iso, result)
    result = _SLASH_DATE.sub(slash, result)
    return _TIME.sub(clock, result)


# --- ellipses and dashes ------------------------------------------------

def interpret_pauses(text: str, *, style: str = 'tags', ellipsis_seconds: float = 0.7,
                     dash_seconds: float = 0.4) -> str:
    """Interpret ellipses and dashes as trailing or interrupted speech.

    ``style='tags'`` inserts timing tags understood by the multivoice
    engine (``[p:0.7s]``); ``style='punctuation'`` normalizes them to plain
    punctuation; ``style='keep'`` validates inputs and returns the text
    unchanged. Trailing ellipses become longer pauses than mid-sentence
    dashes, matching their dramatic function.
    """
    if style not in ('tags', 'punctuation', 'keep'):
        raise ValueError("Style must be 'tags', 'punctuation' or 'keep'")
    if not 0 <= ellipsis_seconds <= 10 or not 0 <= dash_seconds <= 10:
        raise ValueError('Pause lengths must be between 0 and 10 seconds')
    if style == 'keep':
        return text
    result = re.sub(r'\.{3,}|…', '\x00ELLIPSIS\x00', text)
    result = re.sub(r'(?<=\S)\s*(?:—|–|--)\s*(?=\S)', '\x00DASH\x00', result)
    if style == 'tags':
        result = result.replace('\x00ELLIPSIS\x00', f' [p:{ellipsis_seconds:g}s] ')
        result = result.replace('\x00DASH\x00', f' [p:{dash_seconds:g}s] ')
    else:
        result = result.replace('\x00ELLIPSIS\x00', '... ')
        result = result.replace('\x00DASH\x00', ', ')
    return re.sub(r' {2,}', ' ', result)


# Register as text tools so `transform --apply` and the GUI can use them.
add('expand-abbreviations', 'Expand common abbreviations for speech', 'Speech and OCR', expand_abbreviations)
add('speak-numbers', 'Convert numerals to spoken words', 'Speech and OCR',
    lambda text: speak_numbers(text, mode='ordinal-aware'))
add('speak-numbers-plain', 'Convert numerals without ordinal suffixes', 'Speech and OCR',
    lambda text: speak_numbers(text, mode='cardinal'))
add('speak-dates-times', 'Speak dates and clock times', 'Speech and OCR', speak_dates_times)
add('pauses-to-tags', 'Convert ellipses and dashes to pause tags', 'Speech and OCR',
    lambda text: interpret_pauses(text, style='tags'))
