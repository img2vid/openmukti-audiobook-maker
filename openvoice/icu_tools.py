"""Use packaged/system ICU for Unicode transliteration and locale-aware number spelling."""
import ctypes as C
import ctypes.util
import re
import sys
from functools import lru_cache

P,I,U16=C.c_void_p,C.c_int32,C.c_uint16
ENC='utf-16-le' if sys.byteorder=='little' else 'utf-16-be'


@lru_cache(maxsize=1)
def _icu():
    name=ctypes.util.find_library('icui18n') or ctypes.util.find_library('icuin')
    if not name and sys.platform=='darwin':
        name='/usr/lib/libicucore.A.dylib'
    if not name:
        raise RuntimeError('Install ICU, PyICU or the ICU command-line tools')
    lib=C.CDLL(name)
    versions=re.findall(r'\d+',name)
    suffixes=['']+['_'+v for v in versions if int(v)>=40]
    for suffix in suffixes:
        if hasattr(lib,'unum_open'+suffix):
            return lib,suffix
    raise RuntimeError('Cannot resolve the installed ICU C API')


def symbol(name,result,*args):
    lib,suffix=_icu()
    fn=getattr(lib,name+suffix)
    fn.restype=result
    fn.argtypes=args
    return fn


def utf16(s):
    data=s.encode(ENC)
    units=len(data)//2
    buf=(U16*(units+1))()
    C.memmove(buf,data,len(data))
    return buf,units


def transliterate(text,identifier):
    if len(text)>2_000_000:
        raise ValueError('Transliterate at most two million characters per request')
    idbuf,idlen=utf16(identifier)
    error=I()
    handle=symbol('utrans_openU',P,P,I,I,P,I,P,P)(idbuf,idlen,0,None,0,None,C.byref(error))
    if error.value>0 or not handle:
        raise ValueError('Unknown ICU transliteration ID: '+identifier)
    try:
        src,units=utf16(text)
        capacity=max(64,2*units+32)
        run=symbol('utrans_transUChars',None,P,P,P,I,I,P,P)
        for _ in range(5):
            buf=(U16*capacity)()
            C.memmove(buf,src,units*2)
            count=I(units)
            limit=I(units)
            error=I()
            run(handle,buf,C.byref(count),capacity,0,C.byref(limit),C.byref(error))
            if error.value==15:
                capacity=max(capacity*2,count.value+1)
                continue
            if error.value>0:
                raise ValueError('ICU could not transliterate this passage')
            return C.string_at(buf,count.value*2).decode(ENC)
        raise ValueError('Transliterated result is too large')
    finally:
        symbol('utrans_close',None,P)(handle)


def spell_number(value,locale):
    if locale.replace('-','_').split('_')[0].lower()=='bn':
        from .bengali_numbers import spoken
        return spoken(value)
    error=I()
    fmt=symbol('unum_open',P,I,P,I,C.c_char_p,P,P)(5,None,0,locale.encode('ascii'),None,C.byref(error))
    if not fmt or error.value>0:
        raise ValueError('ICU could not open locale '+locale)
    try:
        error=I()
        actual=symbol('unum_getLocaleByType',C.c_char_p,P,I,P)(fmt,0,C.byref(error))
        if actual and actual.decode().split('_')[0]!=locale.replace('-','_').split('_')[0]:
            raise ValueError('No local spellout rules for '+locale)
        buf=(U16*1024)()
        error=I()
        if re.fullmatch(r'[-+]?\d+',str(value)) and -(2**63)<=int(value)<2**63:
            fn=symbol('unum_formatInt64',I,P,C.c_int64,P,I,P,P)
            v=int(value)
        else:
            fn=symbol('unum_formatDouble',I,P,C.c_double,P,I,P,P)
            v=float(value)
        size=fn(fmt,v,buf,len(buf),None,C.byref(error))
        if error.value>0:
            raise ValueError('ICU could not spell the supplied number')
        return C.string_at(buf,size*2).decode(ENC)
    finally:
        symbol('unum_close',None,P)(fmt)


def long_date(day,locale):
    import datetime
    zone,units=utf16('UTC')
    error=I()
    fn=symbol('udat_open',P,I,I,C.c_char_p,P,I,P,I,P)
    fmt=fn(-1,1,locale.encode('ascii'),zone,units,None,0,C.byref(error))
    if not fmt or error.value>0:
        raise ValueError('ICU could not open date locale '+locale)
    try:
        epoch=datetime.date(1970,1,1)
        ms=(day-epoch).days*86400000
        out=(U16*512)()
        error=I()
        length=symbol('udat_format',I,P,C.c_double,P,I,P,P)(fmt,ms,out,512,None,C.byref(error))
        if error.value>0:
            raise ValueError('ICU could not format this calendar date')
        return C.string_at(out,2*length).decode(ENC)
    finally:
        symbol('udat_close',None,P)(fmt)
