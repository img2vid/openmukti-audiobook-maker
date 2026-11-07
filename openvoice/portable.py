"""Runtime checks executed inside the generated Windows, Linux and macOS bundles."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path


def check_system_runtime(*, exercise=False, gui=False):
    """Inventory native providers; optionally exercise actual OCR and the GUI."""
    import importlib.util
    import shutil
    from .spelling import EnglishSpeller
    from .ocr import ocr_status, import_ocr, OCRSettings
    from .fftools import media_tools_status
    result = {'dictionary': EnglishSpeller().suggest('recieved')[0] == 'received',
              'ocr': ocr_status(), 'media': media_tools_status(),
              'pdf_renderer': bool(importlib.util.find_spec('pypdfium2') or shutil.which('pdftoppm')),
              'providers': {name: importlib.util.find_spec(name) is not None for name in
                            ('tkinter','pypdf','striprtf','PIL','numpy','cv2','piper')},
              'embedded_runtime': False, 'inventory_only': not exercise, 'checks': {}}
    result['providers']['piper'] |= bool(shutil.which('piper'))
    if exercise:
        def check(name, operation):
            try:
                result['checks'][name] = {'ok': True, 'detail': operation()}
            except Exception as exc:
                result['checks'][name] = {'ok': False, 'error': str(exc)}
        def recognition():
            scan = resources.files('openvoice').joinpath('resources','portable-ocr-check.png')
            with resources.as_file(scan) as path:
                text = import_ocr(path,OCRSettings(psm=6,auto_rotate=False,deskew=False)).text
            if 'modern world' not in text.casefold(): raise RuntimeError('Sample OCR recognition failed')
            return 'Sample English image recognized'
        def speech():
            from .engines import get_engine
            if not get_engine('piper').available(): raise RuntimeError('Piper runtime is unavailable')
            return 'Native Piper provider is available (voice models selected separately)'
        check('real_ocr', recognition)
        check('speech_provider', speech)
        check('tk_import', lambda: __import__('tkinter').TkVersion)
        check('animated_text',_check_text_rendering)
        if gui: check('gui', _check_gui)
    result['ok'] = (result['dictionary'] and result['ocr']['available'] and
                    {'eng','osd'}.issubset(result['ocr']['languages']) and result['pdf_renderer'] and
                    all(p['available'] and (p['version'] or not exercise) for p in result['media'].values()) and
                    all(result['providers'].values()) and all(p['ok'] for p in result['checks'].values()))
    return result


def check_runtime(*, require_frozen=True, gui=False):
    from . import __version__
    result = {'application':'Openmukti Audiobook Maker','version':__version__,
              'python':sys.version.split()[0],'frozen':bool(getattr(sys,'frozen',False)),
              'checks':{},'ok':False}
    checks = result['checks']
    bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)).resolve()
    def check(name, operation):
        try:
            value = operation()
            checks[name] = {'ok':True,'detail':value}
        except Exception as exc:
            checks[name] = {'ok':False,'error':str(exc)}
    def embedded(path):
        if path is None or not Path(path).resolve().is_relative_to(bundle):
            raise RuntimeError('Required component is not embedded in this executable')
        return Path(path)
    def frozen():
        if require_frozen and not result['frozen']:
            raise RuntimeError('Standalone verification must run inside the generated EXE')
        return result['python']
    check('embedded_python', frozen)
    def dictionary():
        from .spelling import EnglishSpeller
        suggestions = EnglishSpeller().suggest('recieved')
        if not suggestions or suggestions[0] != 'received':
            raise RuntimeError('Bundled English dictionary did not load')
        return 'English dictionary and spelling corrections loaded'
    check('english_dictionary', dictionary)
    def formats():
        import pypdf
        from striprtf.striprtf import rtf_to_text
        if rtf_to_text(r'{\rtf1 Portable text}') != 'Portable text':
            raise RuntimeError('RTF importer failed')
        return 'PDF and RTF import libraries loaded'
    check('document_importers', formats)
    check('animated_text',_check_text_rendering)
    def health(worker):
        worker = embedded(worker)
        environment = os.environ.copy()
        environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        code = subprocess.run([str(worker),'--health'],capture_output=True,text=True,
            encoding='utf-8',errors='replace',timeout=180,env=environment,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if code.returncode:
            raise RuntimeError((code.stderr or code.stdout)[-1500:])
        return code.stdout.strip()
    from .piper_sidecar import find_worker as piper_worker
    from .ocr_sidecar import find_worker as ocr_worker
    if os.name == 'nt' or piper_worker() is not None:
        check('piper_worker',lambda:health(piper_worker()))
    else:
        def native_speech():
            from piper.voice import PiperVoice
            import onnxruntime
            embedded(onnxruntime.__file__)
            return 'Bundled Piper and ONNX runtime loaded'
        check('piper_native', native_speech)
    if os.name == 'nt' or ocr_worker() is not None:
        check('ocr_worker',lambda:health(ocr_worker()))
    else:
        def native_imaging():
            import PIL, numpy, cv2, pypdfium2
            for module in (PIL, numpy, cv2, pypdfium2):
                embedded(module.__file__)
            return 'Bundled Pillow, NumPy, OpenCV and PDFium loaded'
        check('ocr_native', native_imaging)
    def media():
        from .fftools import find_binary,media_tools_status
        values = media_tools_status()
        for name in ('ffmpeg','ffprobe'):
            embedded(find_binary(name,allow_system=False) or None)
            if not values[name]['version']:
                raise RuntimeError(f'Embedded {name} could not start')
        return {name:values[name]['version'] for name in values}
    check('ffmpeg_ffprobe',media)
    def recognition():
        from .ocr import find_tesseract,ocr_status,import_ocr,OCRSettings
        embedded(find_tesseract())
        state=ocr_status()
        if not state['available'] or not {'eng','osd'}.issubset(state['languages']):
            raise RuntimeError('Embedded Tesseract or eng/osd traineddata is missing')
        scan=resources.files('openvoice').joinpath('resources','portable-ocr-check.png')
        with resources.as_file(scan) as source:
            text=import_ocr(source,OCRSettings(psm=6,auto_rotate=False,deskew=False)).text
        if 'modern world' not in text.casefold():
            raise RuntimeError('Bundled Tesseract failed its real image-recognition check: '+text[:150])
        return 'Recognized the embedded English image without an installed Tesseract'
    check('real_ocr',recognition)
    if gui:
        check('tk_spelling_popup_and_undo',_check_gui)
    result['ok']=all(v['ok'] for v in checks.values())
    return result


def _check_text_rendering():
    """Exercise actual Bengali shaping and all three animation engines.

    Windows one-file verification must fail if RAQM or packaged fonts vanished
    during freezing, rather than shipping a broken Bengali video renderer.
    """
    from PIL import Image, ImageChops, ImageFont
    from .animated_video import pick_font,ScriptFont,estimate_timing,paginate,PagePainter
    from .text_layout import load_font,layout_status
    font=pick_font('Portable text',20)
    primary=font.primary if isinstance(font,ScriptFont) else font
    basic=load_font(primary.path,20,force_basic=True)
    for face in (font,basic):
        pages=paginate(estimate_timing('Portable text',1),face,280,3,1)
        painter=PagePainter(pages,(320,180),face,mode='static',color='FFFFFF',panel_opacity=165)
        frame=painter.render(Image.new('RGB',(320,180),'black'),.5)
        if frame.getbbox() is None:raise RuntimeError('Animated text produced an empty frame')
    status=layout_status()
    status.update(native_text_rendered=True,basic_fallback_rendered=True)
    if status['raqm']:
        bengali='বাংলা ভাষা সুন্দর।'
        face=pick_font(bengali,32,handwriting=True)
        base=face.primary if isinstance(face,ScriptFont) else face
        if base.layout_engine != ImageFont.Layout.RAQM:
            raise RuntimeError('Bengali font did not use RAQM text shaping')
        pages=paginate(estimate_timing(bengali,2.5),face,470,3,2.5)
        frame=Image.new('RGB',(550,200),(7,9,14))
        results=[]
        for mode in ('typewriter','handwriting','calligraphy'):
            painter=PagePainter(pages,frame.size,face,mode=mode,color='FFFFFF',panel_opacity=120)
            results.append(painter.render(frame,.5))
        if (ImageChops.difference(results[0],results[1]).getbbox() is None or
            ImageChops.difference(results[1],results[2]).getbbox() is None):
            raise RuntimeError('Bengali typewriter/handwriting/calligraphy must differ')
        status['bengali_raqm_rendered']=True
        status['three_bengali_animations_distinct']=True
    elif os.name=='nt' and getattr(sys,'frozen',False):
        raise RuntimeError('Windows portable release is missing RAQM/Harfbuzz '
                           'and cannot render Bengali. Rebuild with the repaired packager.')
    else:
        status['bengali_raqm_rendered']=False
        status['three_bengali_animations_distinct']=False
    return status


def _check_gui():
    import tkinter as tk
    from .ocr_ui import SpellingController
    root=tk.Tk()
    root.title('Openmukti spelling verification')
    root.geometry('480x180+20+20')
    controller=None
    try:
        editor=tk.Text(root,undo=True)
        editor.pack()
        controller=SpellingController(root,editor,tk.StringVar())
        original='Teh freind.'
        editor.insert('1.0',original)
        root.update()
        controller.check()
        def wait_for(predicate):
            deadline=time.monotonic()+20
            while not predicate():
                root.update()
                if time.monotonic()>deadline:
                    raise RuntimeError('Timed out waiting for the spelling UI')
                time.sleep(.02)
        wait_for(lambda:bool(controller.issues))
        if not editor.tag_ranges('ocr_spelling'):
            raise RuntimeError('Spelling underline tags are missing')
        bounds=editor.bbox('1.5')
        if not bounds:
            raise RuntimeError('Spelling test word is not visible')
        x,y=bounds[0]+1,bounds[1]+bounds[3]//2
        editor.event_generate('<ButtonPress-1>',x=x,y=y)
        editor.event_generate('<ButtonRelease-1>',x=x,y=y)
        root.update()
        if controller.popup is not None:
            raise RuntimeError('Ordinary editing clicks must not open spelling popups')
        expected_index=editor.index(f'@{x},{y}')
        if editor.index('insert') != expected_index:
            raise RuntimeError('A normal click did not place the text cursor')
        editor.focus_force()
        root.update()
        before=editor.get('1.0','end-1c')
        editor.event_generate('<KeyPress>',keysym='x')
        root.update()
        if editor.get('1.0','end-1c')==before:
            raise RuntimeError('Typing at an underlined word did not edit the text')
        editor.event_generate('<KeyPress>',keysym='BackSpace')
        root.update()
        if editor.get('1.0','end-1c')!=before:
            raise RuntimeError('Backspace did not restore the edited text')
        controller.check()
        wait_for(lambda:controller.snapshot==original and bool(controller.issues))
        editor.event_generate('<Button-3>',x=x,y=y)
        wait_for(lambda:controller.popup is not None and controller.popup.winfo_ismapped())
        buttons=controller.popup.winfo_children()[0].winfo_children()
        suggestion=next((w for w in buttons if w.winfo_class()=='TButton' and str(w.cget('text'))=='friend'),None)
        if suggestion is None:
            raise RuntimeError('Dictionary suggestion button is missing')
        suggestion.invoke()
        if editor.get('1.0','end-1c')!='Teh friend.':
            raise RuntimeError('Clicking the suggestion did not replace the word')
        editor.edit_undo()
        if editor.get('1.0','end-1c')!=original:
            raise RuntimeError('The clicked correction was not undone in one step')
        controller.correct_all()
        wait_for(lambda:editor.get('1.0','end-1c')=='The friend.')
        editor.edit_undo()
        if editor.get('1.0','end-1c')!=original:
            raise RuntimeError('One-click correction was not undone in one step')
        editor.edit_redo()
        if editor.get('1.0','end-1c')!='The friend.':
            raise RuntimeError('One-click correction was not redone in one step')
        # Keyboard access opens the same suggestions without interfering with editing.
        controller.check()
        wait_for(lambda:controller.snapshot==editor.get('1.0','end-1c'))
        editor.mark_set('insert','1.0')
        # The corrected words are valid, so reintroduce the sample through a normal edit.
        editor.delete('1.0','end')
        editor.insert('1.0',original)
        root.update()
        controller.check()
        wait_for(lambda:controller.snapshot==original and bool(controller.issues))
        editor.mark_set('insert','1.5')
        editor.focus_force()
        root.update()
        editor.event_generate('<Shift-F10>')
        wait_for(lambda:controller.popup is not None and controller.popup.winfo_ismapped())
        controller.dismiss_popup()
        root.update()
        if editor.focus_get() is not editor:
            raise RuntimeError('Closing suggestions did not return focus to the editor')
        return 'Tk caret placement, typing, Backspace, context/keyboard suggestions, correction and undo/redo passed'
    finally:
        if controller is not None:
            controller.close()
        root.destroy()


def main(argv=None, *, gui=False):
    parser=argparse.ArgumentParser(description='Verify the embedded portable runtime')
    parser.add_argument('--portable-check',required=True,type=Path,metavar='REPORT.json')
    args=parser.parse_args(argv)
    report=check_runtime(gui=gui or os.environ.get('OPENMUKTI_VERIFY_GUI') == '1')
    args.portable_check.parent.mkdir(parents=True,exist_ok=True)
    args.portable_check.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if report['ok'] else 1
