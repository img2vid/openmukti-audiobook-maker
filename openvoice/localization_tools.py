"""Configurable local normalization and ICU transliteration for production scripts."""
import datetime
import re
import shutil
import subprocess
import unicodedata

TEST_PASSAGES={'en':'The wind will wind around the old mill at noon.',
 'bn':'বিকেল তিনটায় শিশুরা বাংলা বই পড়ে।','hi':'आज शाम पाँच बजे हम पुस्तक पढ़ेंगे।',
 'ar':'قَرَأَ الطِّفْلُ كِتَابًا جَدِيدًا.','he':'הילדה קראה ספר חדש.',
 'ja':'明日の午後、図書館で本を読みます。','zh':'今天下午三点，我们一起读书。',
 'ko':'오늘 오후 세 시에 새 책을 읽습니다.','ta':'இன்று மாலை ஒரு புதிய புத்தகத்தைப் படிப்போம்.',
 'es':'Mañana, a las tres, leeremos un libro.','fr':'Demain à quinze heures, nous lirons un livre.',
 'de':'Morgen um drei Uhr lesen wir ein neues Buch.','ru':'Завтра в три часа мы прочитаем книгу.',
 'el':'Αύριο θα διαβάσουμε ένα καινούργιο βιβλίο.','th':'วันนี้เราอ่านหนังสือด้วยกัน',
 'uk':'Ми читаємо нову книгу.','tr':'Yarın yeni bir kitap okuyacağız.','pt':'Amanhã vamos ler um livro.',
 'it':'Domani leggeremo un nuovo libro.','ur':'آج ہم ایک نئی کتاب پڑھیں گے۔',
 'ml':'ഇന്ന് നമ്മൾ ഒരു പുതിയ പുസ്തകം വായിക്കും.','gu':'આજે આપણે એક નવું પુસ્તક વાંચીશું.'}


def romanize(text,scheme='Any-Latin'):
    if len(scheme)>160 or not re.fullmatch(r'[\w/; .-]+',scheme) or scheme.startswith('-'):
        raise ValueError('Enter an ICU transliterator ID')
    tool=shutil.which('uconv')
    if tool:
        r=subprocess.run([tool,'-f','UTF-8','-t','UTF-8','-x',scheme],input=text.encode('utf-8'),
                         capture_output=True,timeout=40)
        if r.returncode:
            raise ValueError(r.stderr.decode(errors='replace')[:600])
        return r.stdout.decode('utf-8')
    try:
        from icu import Transliterator
    except ImportError:
        from .icu_tools import transliterate
        return transliterate(text,scheme)
    return Transliterator.createInstance(scheme).transliterate(text)


def localized(text,locale,*,numbers=False,dates=False,currency='',arabic_marks='preserve',romanization=''):
    from .character_voices import detect_language
    if locale=='auto':
        locale=detect_language(text)[0]
    if not re.fullmatch(r'[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*',locale):
        raise ValueError('Use a language or regional locale such as bn-IN')
    lang=locale.replace('-','_').split('_')[0].lower()
    text=unicodedata.normalize('NFC',text)
    if arabic_marks not in ('preserve','strip'):
        raise ValueError('Unknown diacritic policy')
    if arabic_marks=='strip':
        text=re.sub(r'[\u064b-\u065f\u0670]','',text)
    if dates:
        try:
            from babel.dates import format_date
        except ImportError:
            format_date=None
        def date(m):
            try:
                d=datetime.date.fromisoformat(m[0])
            except ValueError:
                return m[0]
            if format_date:
                return format_date(d,'long',locale=locale.replace('-','_'))
            from .icu_tools import long_date
            return long_date(d,locale)
        text=re.sub(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',date,text)
    if numbers or currency:
        try:
            from num2words import num2words
        except ImportError:
            num2words=None
        def speak(value,**kwargs):
            if num2words is None or lang=='bn':
                from .icu_tools import spell_number
                spoken=spell_number(value,locale)
                if kwargs.get('to')=='currency':
                    from decimal import Decimal
                    from .currency_names import currency_name
                    spoken+=' '+currency_name(kwargs['currency'],value,locale)
                return spoken
            try:
                return num2words(value,lang=locale.replace('-','_'),**kwargs)
            except NotImplementedError as exc:
                raise ValueError('Number narration is unavailable for '+locale) from exc
        if currency:
            if not re.fullmatch('[A-Z]{3}',currency):
                raise ValueError('Use an ISO currency code')
            text=re.sub(r'\b'+currency+r'\s+([0-9]+(?:\.[0-9]{1,2})?)\b',lambda m:speak(float(m[1]),to='currency',currency=currency),text)
        if numbers:
            text=re.sub(r'(?<![\w.])\d+(?:\.\d+)?(?![\w.])',lambda m:speak(m[0]),text)
    if lang=='fr':
        text=re.sub(r'\s*([;!?])',r' \1',text)
    if lang in ('zh','ja'):
        text=re.sub(r'(?<=[\u3040-\u30ff\u3400-\u9fff])[ \t]+(?=[\u3040-\u30ff\u3400-\u9fff])','',text)
    return romanize(text,romanization) if romanization else text


def language_spans(text,default='en'):
    """Split changes of writing system without losing punctuation or whitespace."""
    from .character_voices import detect_language
    families={'ARABIC':'ar','HEBREW':'he','BENGALI':'bn','DEVANAGARI':'hi','TAMIL':'ta','TELUGU':'te',
              'GUJARATI':'gu','GURMUKHI':'pa','MALAYALAM':'ml','KANNADA':'kn','HANGUL':'ko',
              'HIRAGANA':'ja','KATAKANA':'ja','CJK':'zh','CYRILLIC':'ru','GREEK':'el','THAI':'th',
              'LAO':'lo','MYANMAR':'my','SINHALA':'si','ETHIOPIC':'am','ARMENIAN':'hy','GEORGIAN':'ka','LATIN':'latin'}
    spans=[]
    family=None
    start=0
    for i,c in enumerate(text):
        if not c.isalpha():
            continue
        detected=families.get(unicodedata.name(c,'').split(' ',1)[0],default)
        if family is None:
            family=detected
        elif detected!=family:
            spans.append((start,i,family))
            start=i
            family=detected
    if start<len(text):
        spans.append((start,len(text),family or default))
    result=[]
    for first,last,lang in spans:
        if lang=='latin':
            detected=detect_language(text[first:last])[0]
            lang=default if detected in ('auto','und','') else detected
        elif lang=='zh' and (any(f=='ja' for _,_,f in spans) or default.startswith('ja')):
            lang='ja'
        result.append({'start':first,'end':last,'text':text[first:last],'language':lang})
    return result
