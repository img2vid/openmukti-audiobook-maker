"""Original pen trajectories for compositional Hangul and basic Han characters.

Jamo are drawn in logical spelling order and composed in syllable cells.
These envelopes are independent of font outlines. Manual author packs take
priority, and strict transcription still requires the author's own pack.
"""
import math
import unicodedata
from functools import lru_cache

from .stroke_library import Trajectory

# An encoded point contains its x and y on a 0..9 writing grid. Spaces continue
# a pen movement, slashes lift the pen.
JAMO = {
    'ㄱ':'12 82 86', 'ㄴ':'12 18 88', 'ㄷ':'12 82/12 18 88',
    'ㄹ':'12 82 85 15 18 88', 'ㅁ':'12 18/12 82 88/18 88',
    'ㅂ':'12 18/82 88/15 85/18 88', 'ㅅ':'42 45 36 18/45 67 88',
    'ㅈ':'12 82/52 54 35 17/54 66 88', 'ㅊ':'41 61/12 82/53 55 36 18/55 67 88',
    'ㅋ':'12 82 88/25 85', 'ㅌ':'12 82/15 85/12 18 88',
    'ㅍ':'11 81/32 37/62 67/18 88', 'ㅎ':'41 61/12 82/oval',
    'ㅇ':'circle', 'ㅏ':'42 48/45 85', 'ㅐ':'22 28/25 75/72 78',
    'ㅑ':'42 48/43 83/46 86', 'ㅒ':'22 28/23 73/26 76/72 78',
    'ㅓ':'15 65/62 68','ㅔ':'14 54/52 58/82 88','ㅕ':'13 63/16 66/62 68',
    'ㅖ':'13 53/16 56/52 58/82 88','ㅗ':'52 56/16 86','ㅛ':'32 36/62 66/16 86',
    'ㅜ':'13 83/53 58','ㅠ':'13 83/33 38/63 68','ㅡ':'15 85','ㅣ':'52 58',
}

HAN = {
    '一':'15 85', '二':'23 73/18 88', '三':'22 72/25 75/18 88',
    '十':'14 84/52 59','丁':'12 82/52 58 48','干':'22 72/15 85/52 59',
    '工':'22 72/52 58/18 88','土':'24 74/51 58/18 88','士':'13 83/51 58/28 78',
    '王':'12 82/24 74/52 58/18 88','口':'12 18/12 82 88/18 88',
    '日':'22 28/22 72 78/25 75/28 78','目':'22 29/22 72 79/24 74/27 77/29 79',
    '中':'23 27/23 73 77/27 77/51 59','田':'12 18/12 82 88/15 85/52 58/18 88',
    '人':'52 45 37 18/46 68 89','大':'14 84/51 45 37 18/45 66 89',
    '天':'22 72/14 84/52 45 37 18/45 66 89','木':'14 84/51 59/54 37 18/54 76 88',
    '本':'14 84/51 59/54 37 18/54 76 88/36 76','八':'43 36 18/62 65 88',
    '上':'51 58/54 84/18 88','下':'12 82/52 59/55 77','小':'51 58 48/34 16/64 87',
    '山':'51 57/23 28 88/83 88','卜':'51 59/54 76','川':'22 26 18/52 58/82 89'
}
ONSETS='ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
VOWELS='ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
FINALS=('',*'ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ')
COMPOUNDS={'ㄲ':'ㄱㄱ','ㄸ':'ㄷㄷ','ㅃ':'ㅂㅂ','ㅆ':'ㅅㅅ','ㅉ':'ㅈㅈ','ㄳ':'ㄱㅅ','ㄵ':'ㄴㅈ','ㄶ':'ㄴㅎ',
           'ㄺ':'ㄹㄱ','ㄻ':'ㄹㅁ','ㄼ':'ㄹㅂ','ㄽ':'ㄹㅅ','ㄾ':'ㄹㅌ','ㄿ':'ㄹㅍ','ㅀ':'ㄹㅎ','ㅄ':'ㅂㅅ',
           'ㅘ':'ㅗㅏ','ㅙ':'ㅗㅐ','ㅚ':'ㅗㅣ','ㅝ':'ㅜㅓ','ㅞ':'ㅜㅔ','ㅟ':'ㅜㅣ','ㅢ':'ㅡㅣ'}


def paths(spec,box):
    x,y,width,height=box
    output=[]
    for stroke in spec.split('/'):
        if stroke in ('oval','circle'):
            cx,cy,rx,ry=(4.5,6.4,2.9,1.9) if stroke=='oval' else (4.5,5,3.2,3)
            pts=[(cx+rx*math.cos(-math.pi/2-i*2*math.pi/24),cy+ry*math.sin(-math.pi/2-i*2*math.pi/24)) for i in range(25)]
        else:
            pts=[(int(pair[0]),int(pair[1])) for pair in stroke.split()]
        output.append(Trajectory(tuple((x+u*width/9,y+v*height/9,
                      .60 if idx==0 else .53 if idx==len(pts)-1 else .88) for idx,(u,v) in enumerate(pts))))
    return tuple(output)


def component(jamo,box):
    if jamo in JAMO:
        return paths(JAMO[jamo],box)
    a,b=COMPOUNDS[jamo]
    x,y,w,h=box
    return component(a,(x,y,w*.49,h))+component(b,(x+w*.50,y,w*.50,h))


@lru_cache(maxsize=512)
def trajectories(cluster):
    ch=unicodedata.normalize('NFC',cluster)
    if ch in HAN:
        return paths(HAN[ch],(.025,.025,.95,.95))
    if len(ch)!=1 or not 0xAC00<=ord(ch)<=0xD7A3:
        return None
    lead,rest=divmod(ord(ch)-0xAC00,588)
    vowel,tail=divmod(rest,28)
    medial=VOWELS[vowel]
    body=.67 if tail else .95
    if medial in 'ㅗㅛㅜㅠㅡ':
        shape=component(ONSETS[lead],(.14,.02,.72,body*.57))+component(medial,(.06,body*.57,.88,body*.44))
    elif medial in ('ㅘ','ㅙ','ㅚ','ㅝ','ㅞ','ㅟ','ㅢ'):
        under,right=COMPOUNDS[medial]
        shape=(component(ONSETS[lead],(.04,.025,.55,body*.53))+
               component(under,(.025,body*.55,.61,body*.44))+component(right,(.62,.025,.35,body*.92)))
    else:
        shape=component(ONSETS[lead],(.025,.04,.58,body*.9))+component(medial,(.60,.025,.38,body*.94))
    if tail:
        shape+=component(FINALS[tail],(.12,.69,.77,.29))
    return shape
