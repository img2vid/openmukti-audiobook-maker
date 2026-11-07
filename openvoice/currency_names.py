"""Localized currency unit names from ICU without network requests."""
import ctypes as C
from .icu_tools import symbol,utf16,ENC,P,I


def currency_name(code,amount,locale):
    buf,_=utf16(code)
    error=I()
    length=I()
    fn=symbol('ucurr_getPluralName',P,P,C.c_char_p,P,C.c_char_p,P,P)
    # ICU accepts a CLDR plural category. Prefer Babel's locale rule when installed.
    try:
        from babel import Locale
        category=Locale.parse(locale.replace('-','_')).plural_form(amount)
    except ImportError:
        category='one' if amount==1 else 'other'
    p=fn(buf,locale.encode('ascii'),None,category.encode('ascii'),C.byref(length),C.byref(error))
    return C.string_at(p,length.value*2).decode(ENC) if p and error.value<=0 else code
