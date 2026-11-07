"""Point-and-click access to additional existing production capabilities."""
from __future__ import annotations
from pathlib import Path
from tkinter import filedialog
from .gui_forms import Field,FormEditor,show_report,choices
from .studio_windows import async_job


def utility_actions(app,studio):
    def tool(title,data,work,fields=None,report=False):
        def accept(d):
            def done(result):
                if report:
                    show_report(app.root,title,result)
                else:
                    app.status_var.set('Finished: '+str(result))
            async_job(app.root,app.status_var,lambda:work(d),done)
        return lambda:FormEditor(app.root,title,data,accept,fields=fields,apply_label='Run tool').win

    file=Field('Audio recording','file',required=True)
    output=Field('Save audio as','savefile',required=True)
    def signal(d):
        from .audio_analysis import waveform
        data=waveform(d['file'],200)
        return {k:v for k,v in data.items() if k!='points'}
    def compare(d):
        from .production_extras import compare_mixes
        return compare_mixes(d['reference'],d['candidate'])
    def crossfade(d):
        from .production_extras import transition
        if Path(d['output']).resolve() in (Path(d['first']).resolve(),Path(d['second']).resolve()):
            raise ValueError('Choose an output different from both recordings.')
        return transition(d['first'],d['second'],d['output'],d['seconds'])
    def sample(d):
        from .publishing import create_sample
        return create_sample(d['file'],d['output'],start=d['start'],duration=d['duration'],fade_seconds=d['fade_seconds'])
    def picture(d):
        from .sound_studio import audio_picture
        return audio_picture(d['file'],d['output'],d['kind'])
    def inventory(d):
        from .voice_assets import inventory
        return inventory(d['folder'],d['weights_only'])
    def duplicates(d):
        from .voice_assets import duplicate_files
        return duplicate_files(d['folder'])
    def pack(d):
        from .voice_assets import pack
        return pack(d['folder'],d['output'])
    def unpack(d):
        from .voice_assets import unpack
        return unpack(d['file'],d['folder'])
    folder=Field('Voice model folder','folder',required=True)
    rows=[
        ('Audio quality report','Inspect clipping, clicks, dropouts and recording duration.','Art & sound',tool('Audio quality report',{'file':''},signal,{'file':file},True)),
        ('Compare recordings','Compare signal measurements for two recordings.','Art & sound',tool('Compare recordings',{'reference':'','candidate':''},compare,{'reference':Field('Reference recording','file',required=True),'candidate':Field('Candidate recording','file',required=True)},True)),
        ('Crossfade recordings','Join two recordings with a smooth overlap.','Art & sound',tool('Crossfade recordings',{'first':'','second':'','output':'','seconds':1.0},crossfade,{'first':Field('First recording','file',required=True),'second':Field('Second recording','file',required=True),'output':output})),
        ('Promotional audio sample','Create a short excerpt with fades at both ends.','Produce & export',tool('Promotional sample',{'file':'','output':'','start':0.0,'duration':60.0,'fade_seconds':2.0},sample,{'file':file,'output':output,'fade_seconds':Field('Fade length (seconds)','number',minimum=0,maximum=60)})),
        ('Audio picture','Save a waveform or spectrogram as an image.','Art & sound',tool('Audio picture',{'file':'','output':'','kind':'waveform'},picture,{'file':file,'output':Field('Save image as','savefile',required=True,extension='.png'),'kind':Field('Image type',choices=choices('waveform','spectrogram'))})),
        ('Voice model inventory','Review files, sizes and checksums in a voice folder.','Voices & narration',tool('Voice model inventory',{'folder':'','weights_only':False},inventory,{'folder':folder},True)),
        ('Find duplicate voice files','Identify identical model files before organizing them.','Voices & narration',tool('Duplicate voice files',{'folder':''},duplicates,{'folder':folder},True)),
        ('Export voice model pack','Package local voice models for another computer.','Voices & narration',tool('Export voice model pack',{'folder':'','output':''},pack,{'folder':folder,'output':Field('Save pack as','savefile',required=True,extension='.zip')})),
        ('Import voice model pack','Unpack a saved model collection into a chosen folder.','Voices & narration',tool('Import voice model pack',{'file':'','folder':''},unpack,{'file':Field('Voice model pack','file',required=True),'folder':folder})),
        ('Prepare language and numbers','Preview locale-specific numbers, dates and punctuation.','Write & review',lambda:localization(app)),
        ('Import web article','Add the text of a web article to your manuscript.','Write & review',studio.article),
        ('Recover project assets','Find relocated project media and save a recovered copy.','Workspace',studio.recovery),
        ('Accessible workspace','Edit and control playback in a local accessible browser workspace.','Workspace',studio.accessible),
    ]
    return rows


def localization(app):
    original=app._get_text()
    if not original.strip():
        raise ValueError('Enter or import a manuscript first.')
    data={'locale':'en','numbers':True,'dates':True,'currency':'','arabic_marks':'preserve','romanization':''}
    def accept(d):
        from .localization_tools import localized
        from .gui_forms import theme_text
        import tkinter as tk
        from tkinter import ttk
        from .studio_windows import button,line
        from .windowing import fit_window
        result=localized(original,d['locale'],numbers=d['numbers'],dates=d['dates'],currency=d['currency'],arabic_marks=d['arabic_marks'],romanization=d['romanization'])
        win=tk.Toplevel(app.root)
        win.title('Language preparation preview')
        fit_window(win,850,550,400,300)
        box=tk.Text(win,wrap='word')
        theme_text(box)
        box.pack(fill='both',expand=True,padx=10,pady=10)
        box.insert('1.0',result)
        box.configure(state='disabled')
        def apply():
            if app._get_text()!=original:
                raise ValueError('The manuscript changed. Create a new preview before applying it.')
            app._replace_text(result)
            win.destroy()
        button(line(win),'Apply to manuscript',apply)
        button(line(win),'Discard preview',win.destroy)
    return FormEditor(app.root,'Prepare narration language',data,accept,fields={
        'locale':Field('Language / region code',hint='Examples: en, bn-IN, hi-IN, fr-FR.'),
        'arabic_marks':Field('Arabic vowel marks',choices={'preserve':'Keep marks','strip':'Remove marks'}),
        'romanization':Field('Transliteration',choices={'':'Keep the original script','Any-Latin':'Convert to Latin script','Bengali-Latin':'Bengali to Latin','Devanagari-Latin':'Devanagari to Latin'}),
        'currency':Field('Currency code (optional)',hint='Examples: INR, USD, EUR. Leave blank to keep currencies unchanged.')},apply_label='Preview changes').win
