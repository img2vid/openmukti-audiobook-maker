import http.client
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from unittest.mock import patch
from zipfile import ZipFile

from openvoice.engines import SpeechSettings
from openvoice.service import JobOptions
from test_studio_workflows import Demo, Workspace, make_wav


class InterfaceTests(Workspace):
    def test_loopback_accessible_workspace_and_cross_origin_denial(self):
        from openvoice.accessible_workspace import start_workspace
        server,url=start_workspace('</textarea> বাংলায়',Demo(),SpeechSettings(),JobOptions())
        try:
            target=urlsplit(url)
            conn=http.client.HTTPConnection(target.hostname,target.port,timeout=6)
            conn.request('GET',target.path)
            response=conn.getresponse()
            body=response.read().decode()
            self.assertEqual(response.status,200)
            self.assertIn('&lt;/textarea&gt;',body)
            self.assertIn('aria-live="polite"',body)
            payload=json.dumps({'text':'Hello'})
            headers={'Content-Type':'application/json'}
            conn.request('POST',target.path+'audio',payload,headers)
            r=conn.getresponse()
            self.assertEqual(r.status,200)
            self.assertEqual(r.read()[8:12],b'WAVE')
            conn.request('POST',target.path+'audio',payload,{**headers,'Origin':'https://external.invalid'})
            r=conn.getresponse()
            self.assertEqual(r.status,403)
            r.read()
            conn.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_streaming_speech_server_protocol(self):
        from openvoice.local_speech import serve
        import queue
        ready=queue.Queue()
        th=threading.Thread(target=serve,args=(0,Demo(),SpeechSettings(),JobOptions(chunk_size=100)),kwargs={'ready':ready.put},daemon=True)
        th.start()
        server=ready.get(timeout=5)
        try:
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST','/stream',json.dumps({'text':'Another page. '*20}),{'Content-Type':'application/json'})
            r=conn.getresponse()
            rows=[json.loads(v) for v in r.read().splitlines()]
            import base64
            self.assertEqual(r.status,200)
            self.assertEqual(rows[-1],{'complete':True})
            self.assertTrue(all(base64.b64decode(row['wav'])[8:12]==b'WAVE' for row in rows[:-1]))
            conn.close()
        finally:
            server.shutdown()
            th.join(5)

    def test_structured_undo_redo_and_branch(self):
        try:
            from openvoice.studio_windows import DesignHistory
        except ImportError:
            self.skipTest('Tk unavailable')
        history=DesignHistory()
        history.remember({'gain':0})
        history.remember({'gain':1})
        self.assertEqual(history.move(-1),{'gain':0})
        self.assertEqual(history.move(1),{'gain':1})
        history.move(-1)
        history.remember({'gain':2})
        with self.assertRaises(ValueError):
            history.move(1)

    def test_icubased_transliteration_and_bengali_cardinals(self):
        from openvoice.bengali_numbers import spoken
        from openvoice.icu_tools import transliterate
        self.assertEqual(spoken(125000),'এক লক্ষ পঁচিশ হাজার')
        try:
            result=transliterate('বাংলা','Bengali-Latin')
        except (OSError,RuntimeError):
            self.skipTest('ICU runtime unavailable')
        self.assertTrue('b' in result and 'ব' not in result)

    def test_mixed_scripts_keep_offsets_and_change_cast(self):
        from openvoice.localization_tools import language_spans
        from openvoice.performance import plan_score
        text='Hello, বাংলা বই!'
        spans=language_spans(text)
        self.assertEqual(''.join(s['text'] for s in spans),text)
        self.assertEqual(spans[-1]['language'],'bn')
        score={'profiles':{'Narrator':{'voice':'amy'},'Mira':{'voice':'bn-reader'}},'cast_by_language':{'bn':'Mira'},
               'scenes':[{'passages':[{'text':text}]}]}
        self.assertEqual(plan_score(score)[-1]['voice'],'bn-reader')

    def test_local_grammar_utf16_offset(self):
        from openvoice.editorial_studio import suggestions
        from unittest.mock import Mock
        conn=Mock()
        response=conn.getresponse.return_value
        response.status=200
        response.read.return_value=json.dumps({'matches':[{'offset':3,'length':3,'replacements':[{'value':'book'}]}]}).encode()
        with patch('http.client.HTTPConnection',return_value=conn):
            issues=suggestions('📖 bok',{'engines':[],'languagetool':{'language':'en'}})
        self.assertEqual(issues[0]['original'],'bok')

    def test_local_ai_adapter_rejects_non_image(self):
        from openvoice.integrations import illustration
        from unittest.mock import Mock
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow unavailable')
        conn=Mock()
        conn.getresponse.return_value.status=200
        conn.getresponse.return_value.read.return_value=b'{"images":["YWJj"]}'
        with patch('http.client.HTTPConnection',return_value=conn),self.assertRaises(OSError):
            illustration('A cover',self.root/'cover.png')
        self.assertFalse((self.root/'cover.png').exists())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg and FFprobe required')
class MediaIntegration(Workspace):
    def test_mix_stems_loop_and_measured_duration(self):
        from openvoice.sound_studio import mix_session,export_stems
        from openvoice.video import audio_duration
        wav=self.root/'speech.wav'
        make_wav(wav,frames=8000)
        m=self.put('sound.json',{'duck_music':True,'tracks':[{'file':wav.name,'role':'narration'},
                   {'file':wav.name,'role':'music','duration':1.5,'loop':True,'loop_crossfade':.05,
                    'start':.25,'gain':.2,'curve':[[0,0],[.1,1]]}]})
        mixed=mix_session(m,self.root/'mix.wav')
        self.assertAlmostEqual(audio_duration(mixed),1.75,delta=.05)
        self.assertEqual(len(export_stems(m,self.root/'stems')),2)

    def test_real_mp3_daisy_links_and_metadata(self):
        from openvoice.distribution import daisy,compliance
        from openvoice.production_extras import distribution_metadata
        from xml.etree import ElementTree as X
        src=self.root/'s.wav'
        make_wav(src,frames=8000)
        mp3=self.root/'s.mp3'
        subprocess.run([shutil.which('ffmpeg'),'-loglevel','error','-i',str(src),str(mp3)],check=True)
        manifest=self.put('book.json',{'title':'Window & Book','publisher':'Studio','language':'en','chapters':[{'title':'Opening','audio':'s.mp3'}]})
        with ZipFile(daisy(manifest,self.root/'book.zip')) as z:
            nav=X.fromstring(z.read('ncc.html'))
            link=nav.find('.//{*}a').attrib['href'].split('#')[0]
            smil=X.fromstring(z.read(link))
            self.assertIn(smil.find('.//audio').attrib['src'],z.namelist())
        xml=distribution_metadata(manifest,self.root/'book.xml')
        self.assertIn('Window &amp; Book',xml.read_text())
        self.assertTrue(compliance([mp3],{'codec':['mp3']})[0]['passed'])
        self.assertFalse(compliance([mp3],{'codec':['aac']})[0]['passed'])

    def test_actual_prosody_processing_and_software_fallback_video(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow unavailable')
        from openvoice.prosody import shape_recording
        from openvoice.video import audio_duration,VideoOptions,render_video
        wav=self.root/'speech.wav'
        make_wav(wav,frames=12000)
        shaped=self.root/'shaped.wav'
        shape_recording(wav,shaped,{'gain_db':[[0,-3],[1,1]],'pace':[[0,1],[1,1.04]]})
        self.assertGreater(audio_duration(shaped),.3)
        p=self.root/'p.png'
        Image.new('RGB',(100,70),'navy').save(p)
        v=render_video([p],self.root/'book.mp4',audio=shaped,video_options=VideoOptions(dimensions='160x100',fps=24))
        self.assertGreater(v.stat().st_size,1000)

    def test_egl_shader_reference_when_available(self):
        from openvoice.job_queue import cli_process
        cmd,env=cli_process()
        r=subprocess.run([*cmd,'_gl-probe','--software-test'],env=env,timeout=15,capture_output=True)
        if r.returncode:
            self.fail(r.stderr.decode(errors='replace'))
        x=json.loads(r.stdout)
        if not x['available']:
            self.skipTest('EGL ES2 unavailable')
        self.assertEqual(x['pixel_test'][3],255)
        self.assertGreater(x['pixel_test'][0],115)


class CastingRules(Workspace):
    def test_project_phrase_rule_changes_actual_render_passages_and_survives_save(self):
        from openvoice.character_voices import VoiceProject, CharacterProfile, parse_passages
        from openvoice.project_archive import ProjectData, save_project, load_project
        cast=VoiceProject([CharacterProfile('Narrator'),CharacterProfile('Mira')],speaker_rules={'my catchphrase':'Mira'})
        archive=save_project(self.root/'cast.oamproj',ProjectData(voice_project=cast))
        restored=load_project(archive,self.root/'assets').voice_project
        parts=parse_passages('“My catchphrase is back.”',restored.profiles,auto_tag=True,speaker_rules=restored.speaker_rules)
        self.assertTrue(any(p.speaker=='Mira' and 'catchphrase' in p.text for p in parts))


class FinalCoverage(Workspace):
    def test_native_handwriting_handles_every_modern_hangul_syllable(self):
        from openvoice.native_strokes import trajectories
        from openvoice.stroke_library import _check_entry
        for code in range(0xAC00, 0xD7A4):
            glyph=chr(code)
            _check_entry(glyph,trajectories(glyph))
        self.assertEqual(len(trajectories('一')),1)
        self.assertEqual(len(trajectories('木')),4)
        self.assertIsNone(trajectories('Latin'))

    def test_permission_policy_denies_paths_network_and_processes(self):
        import sys
        code="""
from pathlib import Path
import sys,subprocess
from openvoice.access_policy import configure
root=Path(sys.argv[1]);allowed=root/'allowed';allowed.mkdir()
configure({'permissions':{'folders':[str(allowed)],'network':False,'external_tools':False}})
(allowed/'chapter.txt').write_text('approved')
denials=0
for fn in (lambda:(root/'outside.txt').write_text('denied'),lambda:subprocess.run([sys.executable,'-V']),lambda:sys.audit('socket.connect',None,('203.0.113.25',443))):
    try:fn()
    except PermissionError:denials+=1
assert denials==3
"""
        env=dict(os.environ,OPENMUKTI_NEURAL_HOME=str(self.root/'app-data'/'engines'))
        r=subprocess.run([sys.executable,'-c',code,str(self.root)],capture_output=True,text=True,env=env)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_display_scale_and_locale_generation(self):
        from openvoice.windowing import scale_factor
        self.assertEqual(scale_factor(144,100),2)
        self.assertEqual(scale_factor(96,150),2)
        with self.assertRaises(ValueError):scale_factor(96,1000)
        try:from openvoice.interface_language import compile_pack
        except ImportError:self.skipTest('Tk bindings unavailable')
        output=self.root/'bn.json'
        stats=compile_pack(Path(__file__).resolve().parents[1],'bn',output)
        self.assertGreater(stats['entries'],500)
        self.assertGreater(stats['translated_entries'],100)
        self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['File'],'ফাইল')

    def test_accessible_controls_use_same_origin_and_session(self):
        from openvoice.accessible_workspace import start_workspace
        from unittest.mock import Mock
        bridge=Mock()
        bridge.request.side_effect=lambda method,data=None: [{'id':'button-1','label':'Save project','kind':'action'}] if method=='list' else {'accepted':True}
        server,url=start_workspace('text',Demo(),SpeechSettings(),JobOptions(),bridge=bridge)
        try:
            origin=urlsplit(url)
            c=http.client.HTTPConnection(origin.hostname,origin.port,timeout=5)
            c.request('GET',origin.path+'controls')
            r=c.getresponse();self.assertEqual(json.loads(r.read())[0]['label'],'Save project')
            c.request('POST',origin.path+'control',json.dumps({'id':'button-1'}),{'Content-Type':'application/json'})
            r=c.getresponse();self.assertTrue(json.loads(r.read())['accepted'])
            c.request('POST',origin.path+'control','{}',{'Content-Type':'application/json','Origin':'https://example.invalid'})
            r=c.getresponse();self.assertEqual(r.status,403);r.read();c.close()
        finally:
            server.shutdown();server.server_close()

    def test_separate_margin_transcription(self):
        try:
            from PIL import Image,ImageDraw,ImageFont
            import numpy
        except ImportError:self.skipTest('Pillow and NumPy unavailable')
        from openvoice.ocr import OCRSettings,find_tesseract
        if not find_tesseract():self.skipTest('Tesseract unavailable')
        from openvoice.page_layout import analyze_page
        image=Image.new('RGB',(1500,1000),'white');draw=ImageDraw.Draw(image)
        try:font=ImageFont.truetype('DejaVuSans.ttf',38)
        except OSError:self.skipTest('Font fixture unavailable')
        draw.text((18,95),'NOTE',fill='black',font=font)
        draw.text((380,95),'The main manuscript begins here.',fill='black',font=font)
        img=self.root/'page.png';image.save(img)
        report,_=analyze_page(img,OCRSettings(psm=6,deskew=False,denoise=False,auto_rotate=False),
                              margin_boxes=[(15,85,240,200)],margin_language='eng')
        self.assertIn('note',report['marginal_notes'][0]['text'].lower())
        self.assertIn('manuscript',report['body_text'].lower())
        self.assertNotIn('note',report['body_text'].lower())


class LocalizationRelease(Workspace):
    def test_bundled_gui_catalogs_and_status_placeholders(self):
        try:
            from openvoice.interface_language import static_catalog,translated_frame,web_page
        except ImportError:
            self.skipTest('Tk bindings unavailable')
        from openvoice.accessible_workspace import PAGE
        from openvoice.studio_desk import BN,ES
        for lang,extra in [('bn',BN),('es',ES)]:
            catalog={**static_catalog(lang),**extra}
            self.assertGreater(len(catalog),675)
            self.assertNotEqual(catalog['Set Up Piper Voices'],'Set Up Piper Voices')
            translated=translated_frame('Video saved: /tmp/আমার বই.mp4',lang)
            self.assertIsNotNone(translated)
            self.assertIn('/tmp/আমার বই.mp4',translated)
            self.assertNotIn('Video saved:',translated)
            page=web_page(PAGE,lang)
            self.assertIn(f'lang="{lang}"',page)
            self.assertNotIn('>Generate narration<',page)
            self.assertIn('INITIAL_TEXT',page)
