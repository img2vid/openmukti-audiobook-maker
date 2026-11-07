import base64
import hashlib
import io
import json
import os
import sqlite3
from contextlib import closing
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock,patch
from zipfile import ZipFile

from openvoice.engines import SpeechSettings
from openvoice.security_tools import staged_file
from openvoice.service import JobOptions,render_text


def make_wav(path,value=1700,frames=1600):
    with wave.open(str(path),'wb') as f:
        f.setparams((1,2,16000,0,'NONE','not compressed'))
        f.writeframes(int(value).to_bytes(2,'little',signed=True)*frames)


class Demo:
    key='demo'
    def __init__(self):
        self.calls=0
        self.fail=0
    def render_wav(self,text,path,settings,control):
        self.calls+=1
        if self.fail and self.calls==self.fail:
            raise RuntimeError('interrupted')
        make_wav(path,1400+settings.rate)


class Workspace(unittest.TestCase):
    def setUp(self):
        root=tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root=Path(root.name)
        env=patch.dict(os.environ,{'OPENMUKTI_NEURAL_HOME':str(self.root/'engines'),'OPENMUKTI_GPU_MODE':'cpu'})
        env.start()
        self.addCleanup(env.stop)
    def put(self,name,value):
        p=self.root/name
        p.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        return p


class Caching(Workspace):
    def test_changed_settings_and_corruption(self):
        backend=Demo()
        opts=JobOptions(cache_dir=str(self.root/'cache'))
        wav=self.root/'out.wav'
        render_text('Hello.',wav,backend,SpeechSettings(),opts)
        render_text('Hello.',wav,backend,SpeechSettings(),opts)
        self.assertEqual(backend.calls,1)
        db=self.root/'cache'/'speech-cache.sqlite3'
        with closing(sqlite3.connect(db)) as conn, conn:
            conn.execute("UPDATE chunks SET audio=X'00'")
        render_text('Hello.',wav,backend,SpeechSettings(),opts)
        render_text('Hello.',wav,backend,SpeechSettings(rate=1),opts)
        self.assertEqual(backend.calls,3)
    def test_resume_reuses_completed_chunks(self):
        backend=Demo()
        backend.fail=2
        text='Hello there. '*50+'The end!'
        opts=JobOptions(cache_dir=str(self.root/'cache'),chunk_size=100)
        with self.assertRaisesRegex(RuntimeError,'interrupted'):
            render_text(text,self.root/'new.wav',backend,SpeechSettings(),opts)
        self.assertFalse((self.root/'new.wav').exists())
        backend.fail=0
        render_text(text,self.root/'new.wav',backend,SpeechSettings(),opts)
        with closing(sqlite3.connect(self.root/'cache'/'speech-cache.sqlite3')) as conn, conn:
            rows=conn.execute('SELECT count(*) FROM chunks').fetchone()[0]
        self.assertEqual(backend.calls,rows+1)
    def test_model_weights_change_key(self):
        from openvoice.render_cache import model_identity
        file=self.root/'v.onnx'
        file.write_bytes(b'first')
        settings=SpeechSettings(model=str(file))
        d=Demo()
        before=model_identity(d,settings)
        file.write_bytes(b'other')
        self.assertNotEqual(before,model_identity(d,settings))
    def test_stream_yields_real_independent_wav_files(self):
        from openvoice.local_speech import speech_chunks
        events=[]
        for i,text,path in speech_chunks('A short passage. '*20,Demo(),SpeechSettings(),JobOptions(chunk_size=100)):
            with wave.open(str(path)) as f:
                self.assertEqual(f.getnframes(),1600)
            events.append(i)
        self.assertGreater(len(events),1)
        self.assertEqual(events,list(range(1,len(events)+1)))


class Devices(Workspace):
    def test_cpu_mode_does_not_probe(self):
        from openvoice import video_devices as vd
        with patch.object(vd,'advertised',side_effect=AssertionError):
            self.assertEqual(list(vd.candidates('ffmpeg','libx264')),[('libx264','')])
    def test_runtime_encoder_fallback_and_cancel(self):
        from openvoice import video_devices as vd
        from openvoice.engines.base import Cancelled
        candidates=[('h264_nvenc',''),('libx264','')]
        failure=Mock(side_effect=[RuntimeError('driver lost'),None])
        with patch.object(vd,'candidates',return_value=candidates):
            vd.encode('ffmpeg','libx264',failure)
            self.assertEqual([c.args for c in failure.call_args_list],candidates)
            cancel=Mock(side_effect=Cancelled('cancelled'))
            with self.assertRaises(Cancelled):
                vd.encode('ffmpeg','libx264',cancel)
            self.assertEqual(cancel.call_count,1)
    def test_encoder_options_are_specific_to_hardware(self):
        from openvoice.video_devices import arguments
        pre,out=arguments('h264_vaapi',23,(640,360),24,'fps=24','/dev/dri/renderD128')
        self.assertIn('hwupload',out[1])
        self.assertIn('/dev/dri/renderD128',pre)
        self.assertNotIn('-crf',out)
        self.assertIn('-hw_encoding',arguments('h264_mf',23,(640,360),24)[1])
    def test_cpu_overlay_preserves_transparency(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow')
        from openvoice.compute import composite
        a=Image.new('RGBA',(30,30),'red')
        b=Image.new('RGBA',(25,25),(0,0,255,127))
        ref=a.copy()
        ref.alpha_composite(b,(-1,2))
        composite(a,b,(-1,2))
        self.assertEqual(ref.tobytes(),a.tobytes())
    def test_audio_kernel_is_bypassed_in_cpu_mode(self):
        from openvoice.compute import pcm_effect
        self.assertFalse(pcm_effect('no file',self.root/'x.wav',operation='gain',gain=3,pan=0,fade_seconds=1,duration=1))
    def test_no_gpu_pocket_worker_retries_actual_cpu_path(self):
        from openvoice import neural_worker as worker
        worker._FAILED_DEVICES.clear()
        with patch.object(worker,'_preferred_torch_device',return_value='mps'),patch.object(worker,'_synthesize',side_effect=[RuntimeError('missing operator'),None,None]) as mock:
            worker.synthesize({'engine':'pocket'})
            worker.synthesize({'engine':'pocket'})
        worker._FAILED_DEVICES.clear()
        self.assertEqual([c.args[1] for c in mock.call_args_list],['mps','cpu','cpu'])


class AssetsAndProjects(Workspace):
    def test_project_recovery_after_resource_rename(self):
        from openvoice.project_archive import ProjectData,save_project,load_project
        from openvoice.project_tools import recover,migrate
        art=self.root/'cover.png'
        art.write_bytes(b'cover-data')
        src=save_project(self.root/'ok.oamproj',ProjectData(text='কথা',video_images=[art]))
        with ZipFile(src) as original,ZipFile(self.root/'broken.oamproj','w') as broken:
            manifest=json.loads(original.read('project.json'))
            manifest['version']=1
            broken.writestr('project.json',json.dumps(manifest))
        art.rename(self.root/'renamed')
        fixed=self.root/'fixed.oamproj'
        self.assertEqual(len(recover(self.root/'broken.oamproj',self.root,fixed)),1)
        migrated=self.root/'migrated.oamproj'
        migrate(fixed,migrated)
        result=load_project(migrated,self.root/'output')
        self.assertEqual(result.text,'কথা')
        self.assertEqual(result.video_images[0].read_bytes(),b'cover-data')
    def test_storyboard_chapter_and_system_voice_portability(self):
        from openvoice.project_archive import ProjectData,save_project,load_project
        from openvoice.character_voices import VoiceProject,CharacterProfile
        from openvoice.audiobooks import Book,Chapter
        f=self.root/'picture.png'
        f.write_bytes(b'original pixels')
        audio=self.root/'intro.wav'
        make_wav(audio)
        board=self.put('board.json',{'layers':[{'type':'image','file':f.name}]})
        project=ProjectData(video_settings={'storyboard':str(board)},voice_project=VoiceProject([CharacterProfile('Narrator',engine='flite',voice='slt')]),
                            books=[Book('a',[Chapter('b',[],text='Useful',narration={'intro_audio':str(audio),'rate':2})])])
        src=save_project(self.root/'book.oamproj',project)
        f.unlink()
        audio.unlink()
        board.unlink()
        obj=load_project(src,self.root/'restore')
        path=Path(json.loads(Path(obj.video_settings['storyboard']).read_text())['layers'][0]['file'])
        self.assertEqual(path.read_bytes(),b'original pixels')
        self.assertEqual(obj.voice_project.profiles[0].voice,'slt')
        self.assertTrue(Path(obj.books[0].chapters[0].narration['intro_audio']).is_file())
    def test_untrusted_voice_pack_paths_do_not_escape(self):
        from openvoice.voice_assets import unpack
        with ZipFile(self.root/'bad.zip','w') as z:
            z.writestr('voices.json',json.dumps({'format':'openmukti-asset-pack','files':[{'path':'../oops','size':1,'sha256':'x'}]}))
            z.writestr('models/../oops',b'x')
        with self.assertRaises(ValueError):
            unpack(self.root/'bad.zip',self.root/'new')
        self.assertFalse((self.root/'new').exists())
        self.assertFalse((self.root/'oops').exists())
    def test_all_engine_voice_pack_locks_and_dedup(self):
        from openvoice.voice_assets import pack,unpack,duplicate_files,check_lock,inventory
        root=self.root/'model'
        root.mkdir()
        for name in ('a.pth','b.onnx'):
            (root/name).write_bytes(b'weight')
        hashes=inventory(root)
        self.assertEqual(len(duplicate_files(root)),1)
        path=pack(root,self.root/'p.zip')
        unpack(path,self.root/'installed')
        self.assertEqual(check_lock(self.root/'installed',hashes),[])
        (self.root/'installed'/'a.pth').write_bytes(b'broken')
        self.assertEqual(check_lock(self.root/'installed',hashes)[0]['error'],'modified')
    def test_resume_checks_range_and_checksum(self):
        from openvoice.voice_catalog import _download_verified
        raw=b'known weights'
        digest=hashlib.md5(raw).hexdigest()
        file=self.root/'weights.part'
        file.write_bytes(raw[:4])
        response=io.BytesIO(raw[4:])
        response.status=206
        response.headers={'Content-Range':f'bytes 4-{len(raw)-1}/{len(raw)}'}
        opener=Mock(return_value=response)
        _download_verified('https://example.invalid/model',file,len(raw),digest,opener)
        self.assertEqual(file.read_bytes(),raw)
        self.assertEqual(opener.call_args.args[0].get_header('Range'),'bytes=4-')
        file.write_bytes(raw[:4])
        _download_verified('https://example.invalid/model',file,len(raw),digest,Mock(return_value=io.BytesIO(raw)))
        self.assertEqual(file.read_bytes(),raw)
    def test_resumed_wrong_data_is_rejected(self):
        from openvoice.voice_catalog import _download_verified
        p=self.root/'weights'
        p.write_bytes(b'abc')
        resp=io.BytesIO(b'xxx')
        resp.status=206
        resp.headers={'Content-Range':'bytes 3-5/6'}
        with self.assertRaisesRegex(ValueError,'checksum'):
            _download_verified('https://example.invalid/v',p,6,hashlib.md5(b'abcdef').hexdigest(),Mock(return_value=resp))
        self.assertFalse(p.exists())


class Authors(Workspace):
    def test_rules_protected_terms_and_learning(self):
        from openvoice.editorial_studio import suggestions,apply_suggestions,learn_edits
        text='she are kind. Kim would of agreed. Red Red.'
        fixed=apply_suggestions(text,suggestions(text,{'protected':['Red Red']}))
        self.assertEqual(fixed,'she is kind. Kim would have agreed. Red Red.')
        cfg={}
        for _ in range(2):
            learn_edits('The modem book','The modern book',cfg)
        self.assertEqual(cfg['learned']['modem'],'modern')
    def test_docx_footnote_placement_and_table_narration(self):
        from openvoice.documents import read_document
        ns='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        def cell(v):
            return f'<w:tc><w:p><w:r><w:t>{v}</w:t></w:r></w:p></w:tc>'
        xml=f'<w:document xmlns:w="{ns}"><w:body><w:p><w:r><w:t>Book</w:t><w:footnoteReference w:id="1"/></w:r></w:p><w:tbl><w:tr>{cell("Name")}{cell("Age")}</w:tr><w:tr>{cell("Mira")}{cell("12")}</w:tr></w:tbl></w:body></w:document>'
        with ZipFile(self.root/'book.docx','w') as z:
            z.writestr('word/document.xml',xml)
            z.writestr('word/footnotes.xml',f'<w:footnotes xmlns:w="{ns}"><w:footnote w:id="1"><w:p><w:r><w:t>Note text</w:t></w:r></w:p></w:footnote></w:footnotes>')
        plain=read_document(self.root/'book.docx',footnotes='skip')
        self.assertNotIn('Note text',plain)
        spoken=read_document(self.root/'book.docx',footnotes='end',tables='describe')
        self.assertTrue(spoken.endswith('1. Note text'))
        self.assertIn('Name: Mira. Age: 12',spoken)
    def test_stable_folder_observations(self):
        from openvoice.import_studio import FolderInbox
        watch=FolderInbox(self.root)
        p=self.root/'chapter.txt'
        p.write_text('first')
        self.assertEqual(watch.poll(),[])
        self.assertEqual(watch.poll(),[p])
        self.assertEqual(watch.poll(),[])
    def test_ssml_and_inherited_cast_with_scene_curve(self):
        from openvoice.performance import parse_ssml,plan_score
        xml='<speak>Hello<break time="250ms"/><voice name="Mira"><emphasis>world</emphasis></voice></speak>'
        rows=plan_score({'profiles':{'Narrator':{'engine':'flite'},'Mira':{'extends':'Narrator','voice':'awb'}},
                         'scenes':[{'ssml':xml,'curves':{'pace':[[0,1],[1,.8]]}}]})
        self.assertEqual(rows[1],{'pause':.25})
        self.assertEqual((rows[-1]['engine'],rows[-1]['pace'],rows[-1]['gain_db']),('flite',.8,2))
        with self.assertRaises(ValueError):
            parse_ssml('<speak><unknown>no</unknown></speak>')
    def test_voice_merge_and_split_keep_passage_timings(self):
        from openvoice.character_voices import VoiceProject,CharacterProfile
        from openvoice.character_tools import update,search
        project=VoiceProject([CharacterProfile('Narrator'),CharacterProfile('Kim')],script='[Kim, 2s]One. [Kim]Two.')
        update(project,'Kim','Jo',passages=[2])
        self.assertEqual(project.script,'[Kim, 2s]One. [Jo]Two.')
        update(project,'Jo','Kim',remove=True)
        self.assertEqual(len(search(project,'Kim')),1)
    def test_grid_empty_cells_and_typography(self):
        try:
            from PIL import Image,ImageDraw
            import numpy
        except ImportError:
            self.skipTest('Pillow and NumPy')
        from openvoice.advanced_ocr import ruled_table,HocrStyles,historical
        im=Image.new('L',(200,140),255)
        d=ImageDraw.Draw(im)
        for x in (10,100,190):
            d.line((x,12,x,122),fill=0,width=2)
        for y in (12,67,122):
            d.line((10,y,190,y),fill=0,width=2)
        cells=ruled_table(im,[{'box':[20,20,55,40],'text':'Book'}])
        self.assertEqual([c['text'] for c in cells],['Book','','',''])
        self.assertEqual(historical('ſtraﬀ'),'straff')
        parser=HocrStyles()
        parser.feed('<span class="ocrx_word" title="bbox 1 2 10 9"><strong><em>Book</em></strong></span>')
        self.assertTrue(parser.words[0]['bold'] and parser.words[0]['italic'])
    def test_subtitle_editor_rejects_overlap_and_reopens_export(self):
        from openvoice.subtitle_tools import export_cues
        from openvoice.animated_video import load_cues
        rows=[{'start':0,'end':.8,'text':'এক'},{'start':1,'end':2.3,'text':'two'}]
        for ext in ('.srt','.json','.vtt'):
            target=export_cues(rows,self.root/('times'+ext))
            self.assertEqual([c.text for c in load_cues(target,3)],['এক','two'])
        with self.assertRaises(ValueError):
            export_cues([rows[0],rows[0]],self.root/'bad.srt')


class Reliability(Workspace):
    def test_queue_priority_schedule_atomic_claim_and_retry(self):
        from openvoice.job_queue import enqueue,claim,modify,jobs
        db=self.root/'queue.db'
        a=enqueue(db,['render','A','-w','a.wav'],priority=3)
        b=enqueue(db,['render','B','-w','b.wav'],priority=8)
        enqueue(db,['render','future','-w','later.wav'],ready=4102444800)
        c=enqueue(db,['render','other','-w','b.wav'],priority=6)
        self.assertEqual(claim(db)[0]['id'],b)
        self.assertEqual(claim(db)[0]['id'],a)
        self.assertIsNone(claim(db))
        modify(db,b,'cancel')
        self.assertEqual(claim(db)[0]['id'],c)
        modify(db,b,'retry')
        self.assertEqual(next(r['state'] for r in jobs(db) if r['id']==b),'pending')
    def test_signed_permission_limited_extension_and_tamper(self):
        try:
            import cryptography
        except ImportError:
            self.skipTest('cryptography')
        from openvoice.security_tools import generate_key,signature,run_extension
        key,pub,sig=[self.root/n for n in ('priv','pub','sig')]
        generate_key(key,pub)
        manifest=self.put('extension.json',{'version':1,'operations':[{'action':'replace','from':'teh','to':'the'}]})
        signature(manifest,key,sig)
        self.assertTrue(signature(manifest,pub,sig,verify=True))
        with self.assertRaises(ValueError):
            run_extension(manifest,'teh',trusted_key=pub,signature_file=sig)
        self.assertEqual(run_extension(manifest,'teh',trusted_key=pub,signature_file=sig,permissions=['replace']),'the')
        manifest.write_text('{}')
        with self.assertRaises(ValueError):
            run_extension(manifest,'teh',trusted_key=pub,signature_file=sig,permissions=['replace'])
    def test_encrypted_backup_authenticates_before_replacing(self):
        try:
            import cryptography
        except ImportError:
            self.skipTest('cryptography')
        from openvoice.security_tools import backup
        src,enc,out=[self.root/s for s in ('source','enc','out')]
        src.write_bytes(b'private manuscript'*93000)
        backup(src,enc,'passphrase')
        self.assertNotIn(b'manuscript',enc.read_bytes())
        backup(enc,out,'passphrase',decrypt=True)
        self.assertEqual(out.read_bytes(),src.read_bytes())
        out.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            backup(enc,out,'different',decrypt=True)
        self.assertEqual(out.read_bytes(),b'keep')
    def test_pipeline_rejects_commands_outside_rendering(self):
        from openvoice.production_extras import pipeline
        path=self.put('pipeline.json',{'steps':[['studio','upload','secret','remote:path']]})
        with self.assertRaises(ValueError):
            pipeline(path,dry=True)
    def test_template_and_canvas_safe_area(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow')
        from openvoice.storyboard import template,Storyboard
        from openvoice.subtitle_tools import layout_check
        doc=template('lecture','The book','Mira')
        b=Storyboard(doc)
        img=b.preview(.5,2,(300,180),True)
        self.assertEqual(img.size,(300,180))
        boxes=[]
        a={'type':'text','avoid_overlap':True,'box':[.1,.1,.4,.3]}
        first=b.layout(a,boxes)
        second=b.layout(a,boxes)
        self.assertGreaterEqual(second[1],first[3])
        self.assertTrue(layout_check({'layers':[a,a]}))
    def test_hardware_selftest_language_corpus(self):
        from openvoice.studio_selftest import selftest
        result=selftest('languages')
        self.assertTrue(result['ok'],result)
        self.assertIn('bn',result['checks'])
