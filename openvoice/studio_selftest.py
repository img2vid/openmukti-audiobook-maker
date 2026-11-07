"""User-runnable checks for production installations, with real local work samples."""
import io
import json
import tempfile
from pathlib import Path


def selftest(suite):
    checks={}
    def run(name,callback):
        try:
            value=callback()
            checks[name]={'ok':bool(value),'detail':value}
        except Exception as exc:
            checks[name]={'ok':False,'detail':str(exc)}
    if suite=='source':
        import unittest
        directory=Path(__file__).resolve().parent.parent/'tests'
        if not directory.is_dir():
            raise ValueError('The source test suite is available in the source distribution')
        stream=io.StringIO()
        res=unittest.TextTestRunner(stream=stream,verbosity=1).run(unittest.defaultTestLoader.discover(str(directory)))
        checks['suite']={'ok':res.wasSuccessful(),'tests':res.testsRun,'skipped':len(res.skipped),'detail':stream.getvalue()[-4000:]}
    elif suite=='portable':
        from .portable import check_system_runtime
        result=check_system_runtime(exercise=True)
        checks['runtime']={'ok':result['ok'],'detail':result}
    elif suite=='languages':
        from .localization_tools import TEST_PASSAGES,localized
        from .animated_video import graphemes
        from .character_voices import detect_language
        for lang,text in TEST_PASSAGES.items():
            def verify(lang=lang,text=text):
                import unicodedata
                restored=''.join(graphemes(localized(text,lang)))
                if unicodedata.normalize('NFC',text)!=restored:
                    raise ValueError('Grapheme or normalization mismatch')
                return {'expected':lang,'detected':detect_language(text)[0],'characters':len(restored)}
            run(lang,verify)
    elif suite=='render':
        from .engines import get_engine,SpeechSettings
        from .service import render_text
        from .video import audio_duration
        from .audio_analysis import waveform
        with tempfile.TemporaryDirectory() as tmp:
            def speech():
                path=render_text('The studio is ready.',Path(tmp)/'speech.wav',get_engine('auto'),SpeechSettings())
                signal=waveform(path,128)
                if not any(r[2]>.002 for r in signal['points']):
                    raise ValueError('Speech is silent')
                return {'seconds':audio_duration(path),'device':signal['analysis_device']}
            run('actual speech synthesis',speech)
    elif suite=='accessibility':
        from .storyboard import PALETTES
        from .localization_tools import TEST_PASSAGES
        import tkinter as tk
        def luminance(hexcolor):
            c=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
            c=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in c]
            return sum(a*b for a,b in zip(c,(.2126,.7152,.0722)))
        for name,(bg,fg,accent) in PALETTES.items():
            def check(bg=bg,fg=fg):
                lo,hi=sorted((luminance(bg),luminance(fg)))
                contrast=(hi+.05)/(lo+.05)
                if contrast<4.5:
                    raise ValueError('Text contrast below 4.5:1')
                return round(contrast,2)
            run('text contrast '+name,check)
        def widgets():
            from tkinter import ttk
            from .studio_windows import protect_widget
            root=tk.Tk()
            try:
                b=ttk.Button(root,text='Save project',takefocus=True)
                b.pack()
                editor=tk.Text(root,takefocus=True)
                editor.pack()
                protect_widget(editor)
                root.update()
                editor.insert('1.0','protected')
                editor.tag_add('locked','1.0','end-1c')
                editor.delete('1.0','1.2')
                return editor.get('1.0','end-1c')=='protected' and bool(b.cget('text')) and str(b.tk_focusNext())==str(editor)
            finally:
                root.destroy()
        run('keyboard traversal, button label and protected text',widgets)
    else:
        raise ValueError('Unknown self-test suite')
    return {'ok':all(v['ok'] for v in checks.values()),'checks':checks}
