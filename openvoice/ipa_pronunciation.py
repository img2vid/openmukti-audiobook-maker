from __future__ import annotations
from .acceleration import load_voice
import csv
import json
import re
import unicodedata
import wave
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class PronunciationError(ValueError):
    pass


@dataclass(frozen=True)
class Pronunciation:
    word: str
    ipa: str
    language: str = '*'
    spoken: str = ''


@dataclass(frozen=True)
class PronunciationSegment:
    text: str
    ipa: str = ''
    spoken: str = ''


def _clean_ipa(value: str) -> str:
    value = unicodedata.normalize('NFC', value.strip())
    if len(value) >= 2 and ((value[0], value[-1]) in {('/', '/'), ('[', ']')}):
        value = value[1:-1].strip()
    if not value or any(unicodedata.category(ch) == 'Cc' for ch in value):
        raise PronunciationError('IPA must contain printable phonetic characters')
    return value


def language_matches(rule: str, requested: str) -> bool:
    rule = (rule or '*').replace('_', '-').casefold()
    requested = (requested or 'und').replace('_', '-').casefold()
    return rule in {'*', 'all'} or (requested not in {'auto','und'} and (requested == rule or requested.startswith(rule + '-')))


def load_pronunciations(files: list[str] | tuple[str, ...]) -> list[Pronunciation]:
    results: list[Pronunciation] = []
    for filename in files:
        path = Path(filename).expanduser()
        if path.suffix.lower() == '.json':
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if isinstance(data, dict):
                data = data.get('entries')
            if not isinstance(data, list):
                raise PronunciationError(f'{path}: IPA JSON must be a list or an object with an entries list')
            rows = data
        elif path.suffix.lower() in {'.tsv','.txt','.dic'}:
            with path.open(encoding='utf-8-sig', newline='') as f:
                rows = [dict(zip(('word','ipa','language','spoken'), row)) for row in csv.reader(f, delimiter='\t') if row and not row[0].startswith('#')]
        else:
            raise PronunciationError('IPA dictionaries must be .json or tab-delimited .tsv/.txt/.dic')
        for number,row in enumerate(rows,1):
            if not isinstance(row,dict):
                raise PronunciationError(f'{path}: rule {number} is not an object')
            word = row.get('word', row.get('find', ''))
            ipa = row.get('ipa','')
            if not isinstance(word,str) or not word.strip() or not isinstance(ipa,str):
                raise PronunciationError(f'{path}: rule {number} requires word and ipa strings')
            if len(word) > 150 or '\n' in word:
                raise PronunciationError(f'{path}: rule {number} word is too long or contains a line break')
            lang = row.get('language', '*')
            spoken = row.get('spoken', '')
            if not isinstance(lang,str) or not isinstance(spoken,str) or '\n' in spoken:
                raise PronunciationError(f'{path}: rule {number} has invalid language or spoken fallback')
            results.append(Pronunciation(word.strip(), _clean_ipa(ipa),lang.strip() or '*',spoken))
    return results


def segment_pronunciations(text: str, rules: list[Pronunciation], language: str='und') -> list[PronunciationSegment]:
    matching = [rule for rule in rules if language_matches(rule.language,language)]
    if not matching or not text:
        return [PronunciationSegment(text)] if text else []
    by_word = {}
    for rule in sorted(matching,key=lambda item: item.language.casefold() not in {'*','all'}):
        by_word[rule.word.casefold()] = rule
    needles = sorted(by_word,key=lambda word:(-len(word),word))
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(word) for word in needles) + r')(?!\w)',re.I)
    out = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            out.append(PronunciationSegment(text[cursor:match.start()]))
        rule = by_word.get(match.group().casefold())
        if rule:
            out.append(PronunciationSegment(match.group(),rule.ipa,rule.spoken))
        cursor = match.end()
    if cursor < len(text):
        out.append(PronunciationSegment(text[cursor:]))
    return out or [PronunciationSegment(text)]


INLINE_IPA = re.compile(r'(?<!\\)<([^<>\n]{1,300})>')
HTML_TAG_NAMES = {
    'a', 'abbr', 'article', 'aside', 'b', 'blockquote', 'body', 'br', 'caption',
    'code', 'dd', 'div', 'dl', 'dt', 'em', 'figure', 'footer', 'form', 'h1',
    'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hr', 'html', 'i', 'img',
    'input', 'label', 'li', 'link', 'main', 'meta', 'nav', 'ol', 'p', 'pre',
    'script', 'section', 'small', 'span', 'strong', 'style', 'sub', 'sup',
    'table', 'tbody', 'td', 'th', 'thead', 'title', 'tr', 'u', 'ul',
}


def parse_inline_ipa(text: str) -> list[PronunciationSegment]:
    if not text:
        return []
    segments: list[PronunciationSegment] = []
    cursor = 0
    for match in INLINE_IPA.finditer(text):
        raw = match.group(1).strip()
        explicit = raw.casefold().startswith('ipa:')
        body = raw[4:].strip() if explicit else raw
        ipa_value, separator, spoken = body.partition('|')
        ipa_value = ipa_value.strip()
        spoken = spoken.strip() if separator else ''
        if not explicit and (not ipa_value or ipa_value.casefold() in HTML_TAG_NAMES or
                             raw.startswith(('!', '?', '/')) or '=' in raw or
                             raw.endswith('/') or raw.startswith('http')):
            continue
        if explicit and (not ipa_value or (separator and not spoken)):
            raise PronunciationError(f'Invalid inline IPA tag at character {match.start() + 1}. Use <ipa:həˈloʊ> or <ipa:həˈloʊ|hello>.')
        if not ipa_value:
            continue
        if match.start() > cursor:
            segments.append(PronunciationSegment(text[cursor:match.start()]))
        try:
            cleaned = _clean_ipa(ipa_value)
        except PronunciationError as exc:
            raise PronunciationError(f'Invalid inline IPA at character {match.start() + 1}: {exc}') from exc
        segments.append(PronunciationSegment(match.group(), cleaned, spoken))
        cursor = match.end()
    if cursor < len(text):
        segments.append(PronunciationSegment(text[cursor:]))
    return segments or [PronunciationSegment(text)]


def display_inline_ipa(text: str) -> str:
    return ''.join(unit.spoken or f'/{unit.ipa}/' if unit.ipa else unit.text
                   for unit in parse_inline_ipa(text))


def ipa_to_model_phonemes(ipa: str, phoneme_map: dict) -> list[str]:
    ipa = _clean_ipa(ipa)
    known = [key for key in phoneme_map if isinstance(key,str) and key and key not in {'^','$','_'}]
    known.sort(key=lambda item: -len(item))
    sequence = []
    position = 0
    while position < len(ipa):
        ch = ipa[position]
        if ch.isspace() or ch in '.|/[]':
            position += 1
            continue
        symbol = next((key for key in known if ipa.startswith(key,position)),None)
        if symbol is None:
            raise PronunciationError(f'The Piper model cannot pronounce IPA symbol {ch!r} in /{ipa}/. Choose a compatible model, adjust the IPA, or provide a spoken fallback.')
        sequence.append(symbol)
        position += len(symbol)
    if not sequence:
        raise PronunciationError('The supplied IPA contains no supported phonemes')
    return sequence


def _resolve_piper_model(settings):
    from .piper_models import get_voice
    model = Path(settings.model).expanduser() if settings.model else None
    if model is None:
        item = get_voice(settings.voice)
        if item is None:
            raise PronunciationError('Select an installed Piper ONNX model for IPA speech')
        model = item.model
    if not model.is_file() or not Path(str(model)+'.json').is_file():
        raise PronunciationError(f'Piper voice model and matching .onnx.json are required: {model}')
    return model


def render_ipa_wav(ipa: str, destination: str | Path, settings, control=None) -> None:
    try:
        from piper.voice import PiperVoice
    except ImportError as exc:
        from .piper_sidecar import find_worker, render_with_worker, PiperSidecarError
        if find_worker() is None:
            raise PronunciationError('Direct IPA synthesis requires the Piper Python backend or the portable Piper worker. Rebuild using: py -3 build.py --repair.') from exc
        model = _resolve_piper_model(settings)
        length_scale = max(0.45, min(1.8, 1.0 / (1.0 + settings.rate * 0.065)))
        speaker_id = int(settings.voice) if settings.voice.isdecimal() else None
        try:
            render_with_worker(mode='ipa', model=model, config=Path(str(model)+'.json'),
                               output=Path(destination), ipa=ipa, length_scale=length_scale,
                               speaker_id=speaker_id, control=control)
        except PiperSidecarError as worker_error:
            raise PronunciationError(str(worker_error)) from worker_error
        return
    if control:
        control.check()
    model = _resolve_piper_model(settings)
    voice = load_voice(PiperVoice, model, str(model)+'.json')
    tokens = ipa_to_model_phonemes(ipa,voice.config.phoneme_id_map)
    ids = voice.phonemes_to_ids(tokens)
    if len(ids) < 3:
        raise PronunciationError('Could not convert IPA into this Piper voice model\'s phoneme IDs')
    length_scale = max(0.45,min(1.8,1.0/(1.0+settings.rate*0.065)))
    speaker_id = int(settings.voice) if settings.voice.isdecimal() else None
    if hasattr(voice, 'phoneme_ids_to_audio'):
        from piper.config import SynthesisConfig
        import numpy as np
        audio = voice.phoneme_ids_to_audio(ids, syn_config=SynthesisConfig(length_scale=length_scale, speaker_id=speaker_id))
        data = (np.clip(np.asarray(audio), -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    else:
        data = voice.synthesize_ids_to_raw(ids,speaker_id=speaker_id,length_scale=length_scale)
    if control:
        control.check()
    with wave.open(str(destination),'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(voice.config.sample_rate)
        wav.writeframes(data)
