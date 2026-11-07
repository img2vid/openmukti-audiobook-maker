"""Runtime desktop translations and offline generation of complete source catalogs."""
from __future__ import annotations
import ast
import json
import re
import string
from functools import lru_cache
from pathlib import Path
import tkinter as tk

MORE={
'Studio → Production':('Studio → Producción','স্টুডিও → প্রযোজনা'),
'Import several documents':('Importar varios documentos','একাধিক নথি আমদানি'),
'Import web article':('Importar un artículo web','ওয়েব নিবন্ধ আমদানি'),
'Watch document folder':('Vigilar una carpeta de documentos','নথির ফোল্ডার পর্যবেক্ষণ'),
'Aligned OCR page review':('Revisar la página y el texto OCR','স্ক্যান ও ওসিআর লেখা পর্যালোচনা'),
'Recover project assets':('Recuperar archivos del proyecto','প্রকল্পের ফাইল পুনরুদ্ধার'),
'Cast and dialogue timeline':('Reparto y cronología del diálogo','চরিত্র ও সংলাপের ক্রম'),
'Caption design':('Diseño de subtítulos','সাবটাইটেলের নকশা'),
'Split manuscript and preview':('Manuscrito y vista previa en paralelo','পাণ্ডুলিপি ও পূর্বরূপ পাশাপাশি'),
'Preview chapter openings':('Escuchar el inicio de los capítulos','অধ্যায়গুলির শুরু শুনুন'),
'Sentence emphasis editor':('Editor de énfasis','বাক্যে জোর দেওয়ার সম্পাদক'),
'Render narration score or SSML':('Generar narración desde partitura o SSML','স্কোর বা এসএসএমএল থেকে বর্ণনা তৈরি'),
'Voice auditions':('Pruebas de voces','কণ্ঠস্বরের নমুনা'),
'Production queue':('Cola de producción','প্রযোজনার সারি'),
'Configure chunk cache':('Configurar la caché de fragmentos','বাক্যাংশের ক্যাশ নির্ধারণ'),
'Install local accelerator wheels':('Instalar paquetes locales de aceleración','স্থানীয় অ্যাক্সিলারেটর প্যাকেজ স্থাপন'),
'Local voice command':('Comando de voz local','স্থানীয় কণ্ঠনির্দেশ'),
'Export diagnostic bundle':('Exportar diagnóstico','রোগনির্ণয় তথ্য রপ্তানি'),
'Accessible manuscript and playback workspace':('Edición y reproducción accesibles','প্রবেশগম্য লেখা ও প্লেব্যাক কর্মক্ষেত্র'),
'Focus writing mode':('Modo de escritura sin distracciones','মনোযোগ দিয়ে লেখার মোড'),
'Project workspace':('Espacio de proyectos','প্রকল্প কর্মক্ষেত্র'),
'New tab':('Nueva pestaña','নতুন ট্যাব'),'Open project':('Abrir proyecto','প্রকল্প খুলুন'),
'Open read-only':('Abrir en modo de lectura','শুধু পড়ার জন্য খুলুন'),'Save copy':('Guardar copia','অনুলিপি সংরক্ষণ'),
'Close tab':('Cerrar pestaña','ট্যাব বন্ধ'),'Compare edits':('Comparar cambios','পরিবর্তন তুলনা'),
'Review corrections':('Revisar correcciones','সংশোধন পর্যালোচনা'),'Transform preview':('Vista previa de transformación','রূপান্তরের পূর্বরূপ'),
'Editorial rules':('Normas editoriales','সম্পাদনার নিয়ম'),'Protect selection':('Proteger selección','নির্বাচিত লেখা সুরক্ষিত করুন'),
'Activity':('Actividad','কার্যকলাপ'),'Chapters':('Capítulos','অধ্যায়'),
'Cover and video designer':('Diseñador de portadas y vídeo','প্রচ্ছদ ও ভিডিও নকশা'),
'New design':('Nuevo diseño','নতুন নকশা'),'Export cover':('Exportar portada','প্রচ্ছদ রপ্তানি'),
'Use in video':('Usar en el vídeo','ভিডিওতে ব্যবহার'),'Add artwork':('Añadir ilustración','চিত্র যোগ করুন'),
'Add text':('Añadir texto','লেখা যোগ করুন'),'Watermark':('Marca de agua','জলছাপ'),'Panel tour':('Recorrido por viñetas','কমিক প্যানেলের ক্রম'),
'Layer properties':('Propiedades de la capa','স্তরের বৈশিষ্ট্য'),'Remove':('Quitar','সরান'),'Choose color':('Elegir color','রং বাছুন'),
'Open session':('Abrir sesión','সেশন খুলুন'),'Save template':('Guardar plantilla','টেমপ্লেট সংরক্ষণ'),
'Add clips':('Añadir clips','ক্লিপ যোগ করুন'),'Edit clip':('Editar clip','ক্লিপ সম্পাদনা'),
'Add marker':('Añadir marcador','চিহ্ন যোগ করুন'),'Find cut points':('Buscar puntos de corte','কাটার স্থান খুঁজুন'),
'Mix options':('Opciones de mezcla','মিক্সের বিকল্প'),'Export mix':('Exportar mezcla','মিক্স রপ্তানি'),
'Export stems':('Exportar pistas separadas','পৃথক ট্র্যাক রপ্তানি'),'Preview clip':('Escuchar clip','ক্লিপ শুনুন'),
'Open audio':('Abrir audio','অডিও খুলুন'),'Spectrogram':('Espectrograma','বর্ণালিচিত্র'),
'Enter selection':('Introducir intervalo','সময়সীমা লিখুন'),'Play selection':('Reproducir selección','নির্বাচিত অংশ শুনুন'),
'Save selection':('Guardar selección','নির্বাচিত অংশ সংরক্ষণ'),'Preview time':('Tiempo de vista previa','পূর্বরূপের সময়'),
'Show grid and safe area':('Mostrar cuadrícula y área segura','গ্রিড ও সুরক্ষিত এলাকা দেখান'),
'Role':('Rol','ভূমিকা'),'Start':('Inicio','শুরু'),'Duration':('Duración','সময়কাল'),'Gain':('Ganancia','গেইন'),'Name':('Nombre','নাম'),
'Previous':('Anterior','পূর্ববর্তী'),'Next':('Siguiente','পরবর্তী'),'Try this step':('Probar este paso','এই ধাপটি চেষ্টা করুন'),
'Close workspace':('Cerrar espacio de trabajo','কর্মক্ষেত্র বন্ধ'),'Apply changes':('Aplicar cambios','পরিবর্তন প্রয়োগ করুন'),
'Queue':('Cola','সারি'),'Help':('Ayuda','সাহায্য'),'Statistics':('Estadísticas','পরিসংখ্যান'),
'Find / Replace':('Buscar y reemplazar','খুঁজুন ও প্রতিস্থাপন করুন'),'Combine Chapters':('Combinar capítulos','অধ্যায় একত্র করুন'),
'Character Voices':('Voces de personajes','চরিত্রের কণ্ঠস্বর'),'Text tools':('Herramientas de texto','লেখার সরঞ্জাম'),
'Audio':('Audio','অডিও'),'Status':('Estado','অবস্থা'),'Undo':('Deshacer','পূর্বাবস্থা'),'Redo':('Rehacer','পুনরায় করুন')
}


@lru_cache(maxsize=2)
def static_catalog(target):
    if target not in ('bn','es'):
        return {}
    from importlib import resources
    path=resources.files('openvoice').joinpath('resources',f'interface-{target}.json')
    extra=json.loads(path.read_text(encoding='utf-8'))
    return {**{k:v[0 if target=='es' else 1] for k,v in MORE.items()},**extra}


def source_strings(source):
    """Extract user-facing literals, including dynamic f-string templates."""
    root=Path(source)
    texts=set()
    methods={'title','showinfo','showwarning','showerror','askyesno','askstring','askfloat','askinteger','show_text','button'}
    for path in sorted((root/'openvoice').glob('*.py')):
        try:tree=ast.parse(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):continue
            name=getattr(node.func,'attr',getattr(node.func,'id',''))
            args=[kw.value for kw in node.keywords if kw.arg in ('text','label','title','message','help')]
            if name in methods:args+=list(node.args[:3])
            for arg in args:
                if isinstance(arg,ast.Constant) and isinstance(arg.value,str) and any(c.isalpha() for c in arg.value):
                    texts.add(arg.value)
    texts.update(MORE)
    return sorted(texts)


def compile_pack(root,target,output,translate=False):
    from .studio_desk import BN,ES
    table={**({'bn':BN,'es':ES}.get(target,{})),**static_catalog(target)}
    phrases=source_strings(root)
    translator=None
    if translate:
        try:from argostranslate import translate as argos
        except ImportError as exc:raise RuntimeError('Install Argos Translate and a local English-to-target language model') from exc
        langs={l.code:l for l in argos.get_installed_languages()}
        if 'en' not in langs or target not in langs:raise ValueError('Install the requested local translation model first')
        translator=langs['en'].get_translation(langs[target])
    for phrase in phrases:
        if phrase in table:continue
        table[phrase]=translator.translate(phrase) if translator else phrase
    from .voice_library import _atomic_json
    _atomic_json(Path(output),table)
    return {'entries':len(table),'language':target,'translated_entries':sum(k!=v for k,v in table.items())}


class WindowTranslations:
    def __init__(self,root):
        self.root=root;self.translations={};self.known={};self.fallback=None;self.target=None;self.proxies={}
        localize_native_dialogs(self)
        root.bind_all('<Map>',self.mapped,add='+')

    def update(self,table,target='en',translate_missing=False):
        self.locale=target
        new_target=target if translate_missing and target!='en' else None
        if new_target!=self.target:
            self.fallback=LocalTranslator(new_target) if new_target else None
            self.target=new_target
        self.translations=table
        for source_var,dest,_ in self.proxies.values():
            dest.set(self.word(str(self.root.getvar(source_var))))
        self.walk(self.root)

    def word(self,value):
        fixed=self.translations.get(value)
        if fixed and fixed!=value:return fixed
        framed=translated_frame(value,getattr(self,'locale','en'))
        if framed is not None:return framed
        return self.fallback(value) if self.fallback else value

    def item(self,key,value):
        old=self.known.get(key)
        original=old[0] if old and old[1]==value else value
        result=self.word(original)
        if result!=original or old:self.known[key]=(original,result)
        return result

    def mapped(self,event):
        if self.translations or self.fallback:
            w=event.widget
            if hasattr(w,'winfo_exists'):self.root.after_idle(lambda:self.one(w) if w.winfo_exists() else None)

    def one(self,w):
        try:
            if isinstance(w,(tk.Toplevel,tk.Tk)):
                v=w.title();t=self.item((str(w),'title'),v)
                if t!=v:w.title(t)
            if isinstance(w,tk.Menu):
                for i in range((w.index('end') or 0)+1):
                    if w.type(i) in ('separator','tearoff'):continue
                    v=w.entrycget(i,'label');t=self.item((str(w),i),v)
                    if t!=v:w.entryconfigure(i,label=t)
            elif 'text' in w.keys() and not ('textvariable' in w.keys() and w.cget('textvariable')):
                v=w.cget('text')
                if v:
                    t=self.item((str(w),'text'),v)
                    if t!=v:w.configure(text=t)
            if (self.translations or self.fallback) and w.winfo_class() in ('Label','TLabel','Button','TButton') and w.cget('textvariable') and str(w) not in self.proxies:
                source_var=str(w.cget('textvariable'))
                dest=tk.StringVar(master=self.root,value=self.word(str(self.root.getvar(source_var))))
                trace=w.register(lambda *_:dest.set(self.word(str(self.root.getvar(source_var)))))
                self.root.tk.call('trace','add','variable',source_var,'write',trace)
                self.proxies[str(w)]=(source_var,dest,trace)
                w.configure(textvariable=dest)
                def dispose(evt):
                    if evt.widget is w:
                        self.root.tk.call('trace','remove','variable',source_var,'write',trace);self.proxies.pop(str(w),None)
                w.bind('<Destroy>',dispose,add='+')
            if w.winfo_class()=='Treeview':
                for c in w.cget('columns'):
                    v=w.heading(c,'text');t=self.item((str(w),'heading',c),v)
                    if t!=v:w.heading(c,text=t)
        except tk.TclError:
            return

    def walk(self,w):
        self.one(w)
        for child in w.winfo_children():self.walk(child)


class LocalTranslator:
    """Optional, already-installed Argos model. No package catalog or download is opened."""
    def __init__(self,target):
        try:
            from argostranslate import translate
        except ImportError as exc:
            raise RuntimeError('Install Argos Translate and a local language model to translate missing UI strings') from exc
        langs={item.code:item for item in translate.get_installed_languages()}
        if 'en' not in langs or target not in langs:
            raise ValueError('No installed offline English-to-'+target+' translation model')
        self.model=langs['en'].get_translation(langs[target])
        self.cache={}
    def __call__(self,value):
        if not value or not re.search('[A-Za-z]',value) or len(value)>8000:
            return value
        if value not in self.cache:
            self.cache[value]=self.model.translate(value)
        return self.cache[value]


def localize_native_dialogs(service):
    """Translate Tk file-dialog titles, modal prompts and messages before presentation."""
    from functools import wraps
    from tkinter import filedialog,messagebox,simpledialog
    for module,names in ((filedialog,('askopenfilename','askopenfilenames','asksaveasfilename','askdirectory')),
                         (messagebox,('showinfo','showwarning','showerror','askquestion','askokcancel','askyesno','askyesnocancel','askretrycancel')),
                         (simpledialog,('askstring','askinteger','askfloat'))):
        for name in names:
            current=getattr(module,name)
            original=getattr(current,'_openmukti_original',current)
            def wrap(fn,has_positionals):
                @wraps(fn)
                def translated(*args,**kwargs):
                    args=list(args)
                    if has_positionals:
                        for i in range(min(2,len(args))):
                            if isinstance(args[i],str):args[i]=service.word(args[i])
                    for key in ('title','message','prompt','detail'):
                        if isinstance(kwargs.get(key),str):kwargs[key]=service.word(kwargs[key])
                    return fn(*args,**kwargs)
                translated._openmukti_original=fn
                return translated
            setattr(module,name,wrap(original,module is not filedialog))


WEB={
    'Openmukti accessible workspace':('Openmukti প্রবেশগম্য কর্মক্ষেত্র','Espacio de trabajo accesible de Openmukti'),
    'Skip to manuscript':('সরাসরি পাণ্ডুলিপিতে যান','Saltar al manuscrito'),
    'Open a local text file, edit the manuscript, then generate audio. Use the media controls to play, pause, seek or change volume.':('স্থানীয় লেখার ফাইল খুলুন, সম্পাদনা করুন ও অডিও তৈরি করুন। মিডিয়া নিয়ন্ত্রণ দিয়ে শুনুন, বিরতি দিন, সময় বাছুন বা শব্দমাত্রা বদলান।','Abra un archivo de texto local, edite el manuscrito y genere el audio. Use los controles para reproducir, pausar, buscar una posición o cambiar el volumen.'),
    'Open UTF-8 text':('UTF-8 লেখা খুলুন','Abrir texto UTF-8'),'Manuscript':('পাণ্ডুলিপি','Manuscrito'),
    'Download text':('লেখা ডাউনলোড করুন','Descargar texto'),'Generate narration':('বর্ণনার অডিও তৈরি করুন','Generar narración'),
    'Playback':('প্লেব্যাক','Reproducción'),'Narration playback':('বর্ণনার প্লেব্যাক','Reproducción de la narración'),
    'Download narration WAV':('বর্ণনার WAV ডাউনলোড করুন','Descargar narración en WAV'),
    'Ready':('প্রস্তুত','Listo'),'Loaded ':('খোলা হয়েছে: ','Abierto: '),
    'Generating narration':('বর্ণনা তৈরি হচ্ছে','Generando narración'),'Narration ready':('বর্ণনা প্রস্তুত','Narración lista'),
    'Could not render: ':('অডিও তৈরি করা যায়নি: ','No se pudo generar el audio: '),
    'Desktop controls':('ডেস্কটপের নিয়ন্ত্রণ','Controles de escritorio'),
    'Use the same commands, fields, tabs and selections as the desktop. Refresh after a window opens or closes.':('ডেস্কটপের একই নির্দেশ, ক্ষেত্র, ট্যাব ও নির্বাচন এখানে ব্যবহার করুন। উইন্ডো খোলা বা বন্ধ হলে তালিকা হালনাগাদ করুন।','Use las mismas órdenes, campos, pestañas y selecciones que en el escritorio. Actualice la lista al abrir o cerrar una ventana.'),
    'Refresh controls':('নিয়ন্ত্রণ হালনাগাদ করুন','Actualizar controles'),'Find a control':('নিয়ন্ত্রণ খুঁজুন','Buscar un control'),
    'Apply ':('প্রয়োগ করুন: ','Aplicar '),'Desktop controls refreshed':('ডেস্কটপের নিয়ন্ত্রণ হালনাগাদ হয়েছে','Controles actualizados'),
    'Command accepted. Refresh after the desktop changes.':('নির্দেশ গৃহীত। ডেস্কটপের পরিবর্তনের পরে হালনাগাদ করুন।','Orden aceptada. Actualice la lista cuando cambie el escritorio.')
}


def web_page(page,locale):
    if locale not in ('bn','es'):
        return page
    import html
    table={k:v[0 if locale=='bn' else 1] for k,v in WEB.items()}
    page=page.replace('<html lang="en">','<html lang="'+locale+'">')
    for source,target in sorted(table.items(),key=lambda pair:-len(pair[0])):
        page=page.replace('>'+source+'<','>'+html.escape(target)+'<')
        page=page.replace('aria-label="'+source+'"','aria-label="'+html.escape(target,quote=True)+'"')
        # Only substitute exact JavaScript string literals in the shipped template.
        page=page.replace("'"+source+"'",json.dumps(target,ensure_ascii=True))
    return page


@lru_cache(maxsize=2)
def patterns(locale):
    if locale not in ('bn','es'):
        return ()
    from importlib import resources
    source=resources.files('openvoice').joinpath('resources',f'interface-patterns-{locale}.json')
    data=json.loads(source.read_text(encoding='utf-8'))
    ordered=sorted(data,key=lambda key:len(key.replace('{}','')),reverse=True)
    return tuple((key.split('{}'),data[key]) for key in ordered)


def translated_frame(text,locale):
    """Capture variable values without evaluating them or changing names and paths."""
    if not text or len(text)>32000:return None
    for pieces,target in patterns(locale):
        prefix,suffix=pieces[0],pieces[-1]
        if not text.startswith(prefix) or not text.endswith(suffix) or len(prefix)+len(suffix)>len(text):
            continue
        end=len(text)-len(suffix) if suffix else len(text)
        section=text[len(prefix):end]
        values=[]
        for delimiter in pieces[1:-1]:
            if not delimiter:
                values.append('')
                continue
            if delimiter not in section:
                break
            value,section=section.split(delimiter,1)
            values.append(value)
        else:
            values.append(section)
            # Avoid interpreting an arbitrary nonnumeric filename as a count.
            if pieces==['',' strokes'] and not section.isdecimal():
                continue
            return target.format(*values)
    return None
