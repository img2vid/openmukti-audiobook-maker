"""Fast regression tests: all neural integrations without downloading models."""
from __future__ import annotations
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from openvoice.neural_runtime import (NEURAL_ENGINES, install_plan, python_path,
    is_installed, DEFAULT_VOICES, KOKORO_VOICES, KITTEN_VOICES, POCKET_VOICES)
from openvoice.engines import all_engines
from openvoice.character_voices import CharacterProfile, VoiceProject
from openvoice.project_archive import ProjectData, load_project, save_project


class NeuralIntegrationTests(unittest.TestCase):
    def test_all_four_engines_are_registered_and_have_voices(self):
        registry = all_engines()
        self.assertTrue(set(NEURAL_ENGINES).issubset(registry))
        for key in NEURAL_ENGINES:
            self.assertEqual(registry[key].key, key)
            self.assertTrue(hasattr(registry[key], 'render_wav'))
            self.assertTrue(hasattr(registry[key], 'speak'))
        self.assertEqual(len(KOKORO_VOICES), 54)
        self.assertEqual(len(KITTEN_VOICES), 8)
        self.assertGreaterEqual(len(POCKET_VOICES), 20)
        self.assertEqual(registry['kokoro'].voices(), list(KOKORO_VOICES))
        self.assertEqual(registry['kitten'].voices(), list(KITTEN_VOICES))
        self.assertEqual(registry['pocket'].voices(), list(POCKET_VOICES))

    def test_isolated_cpu_dependency_plans(self):
        for engine in NEURAL_ENGINES:
            steps = install_plan(engine)
            self.assertTrue(steps)
            args = ' '.join(' '.join(step) for step in steps)
            self.assertNotIn('CUDA', args)
        self.assertIn('coqui-tts', install_plan('coqui')[-1])
        self.assertIn('pocket-tts', install_plan('pocket')[-1])
        kokoro_plan = install_plan('kokoro')
        self.assertTrue(any('kokoro>=0.9.2' in step for step in kokoro_plan))
        self.assertFalse(any('misaki[ja' in step for step in kokoro_plan))
        self.assertTrue(any('pyopenjtalk-plus>=0.4.1.post8' in step for step in kokoro_plan))
        self.assertTrue(any('unidic-lite' in step for step in kokoro_plan))
        self.assertFalse(any('torchaudio' in step for step in kokoro_plan))
        self.assertTrue(any('.whl' in arg for arg in install_plan('kitten')[0]))
        with patch('openvoice.neural_runtime.sys.platform', 'linux'):
            self.assertIn('https://download.pytorch.org/whl/cpu', install_plan('coqui')[0])
            self.assertIn('https://download.pytorch.org/whl/cpu', install_plan('pocket')[0])

    def test_automatic_uv_python_and_engine_installer(self):
        import openvoice.neural_runtime as runtime
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ, {'OPENMUKTI_NEURAL_HOME':directory}), \
             patch.object(runtime,'bundled_uv',return_value='/bundled/uv'), \
             patch.object(runtime,'_run') as run:
            def emulate(command, **kwargs):
                if command[1] == 'venv':
                    binary = python_path('pocket')
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_bytes(b'fake python')
            run.side_effect = emulate
            self.assertFalse(is_installed('pocket'))
            self.assertEqual(runtime.ensure_installed('pocket'),python_path('pocket'))
            self.assertTrue(is_installed('pocket'))
            commands = [x.args[0] for x in run.call_args_list]
            self.assertEqual(commands[0][:4],['/bundled/uv','venv','--python','3.12'])
            self.assertTrue(any(x[:3] == ['/bundled/uv','pip','install'] for x in commands))
            self.assertTrue(any('pocket-tts' in x for x in commands))
            before = len(commands)
            self.assertEqual(runtime.ensure_installed('pocket'),python_path('pocket'))
            self.assertEqual(len(run.call_args_list), before)

    def test_project_round_trip_non_piper_voice_names_and_model_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            profiles=[CharacterProfile('Narrator',engine='kokoro',voice='jf_alpha'),
                      CharacterProfile('A',engine='kitten',voice='Bella',model='KittenML/kitten-tts-mini-0.8'),
                      CharacterProfile('B',engine='pocket',voice='alba',model='english_7m_2026-10'),
                      CharacterProfile('C',engine='coqui',voice='',model='tts_models/en/ljspeech/tacotron2-DDC')]
            source=ProjectData(text='Test book',voice_project=VoiceProject(profiles),
                settings={'engine':'coqui','model':'tts_models/en/vctk/vits','voice':'p225'})
            zipfile=folder/'book.oamproj'
            save_project(zipfile,source)
            read=load_project(zipfile,folder/'extracted')
            self.assertEqual([p.voice for p in read.voice_project.profiles],[p.voice for p in profiles])
            self.assertEqual([p.model for p in read.voice_project.profiles],[p.model for p in profiles])
            self.assertEqual([p.engine for p in read.voice_project.profiles],[p.engine for p in profiles])
            self.assertEqual(read.settings['model'],'tts_models/en/vctk/vits')
            self.assertEqual(read.settings['voice'],'p225')
            saved=folder/'project.json'
            read.voice_project.save(saved)
            loaded=VoiceProject.load(saved)
            self.assertEqual(loaded.profiles[-1].engine,'coqui')

    def test_cli_parser_for_neural_engine_installation(self):
        from openvoice.cli import make_parser
        parser=make_parser()
        self.assertEqual(parser.parse_args(['engine-install','all']).engine,'all')
        for key in NEURAL_ENGINES:
            self.assertEqual(parser.parse_args(['render','--engine',key,'-t','Hello','-w','out.wav']).engine,key)

    def test_worker_resource_follows_worker_module(self):
        from importlib.resources import files
        resource=files('openvoice').joinpath('resources/neural_worker.txt').read_bytes()
        source=Path(__file__).resolve().parents[1]/'openvoice/neural_worker.py'
        self.assertEqual(source.read_bytes(),resource)

    def test_persistent_neural_worker_protocol(self):
        from openvoice.engines.neural import _Worker
        with tempfile.TemporaryDirectory() as d:
            script=Path(d)/'fake_worker.py'
            script.write_text('''import sys,json\nfor line in sys.stdin:\n p=json.loads(line)\n open(p["output"],"wb").write(b"RIFF"+b"0"*44)\n print(json.dumps({"ok":True}),flush=True)\n''')
            worker=_Worker(Path(sys.executable),script,'pocket')
            try:
                one=Path(d)/'1.wav'
                two=Path(d)/'2.wav'
                worker.request({'output':str(one)})
                proc=worker.process
                worker.request({'output':str(two)})
                self.assertIs(worker.process,proc)
                self.assertTrue(one.is_file())
                self.assertTrue(two.is_file())
            finally:
                worker.close()
            self.assertIsNone(worker.process)

    def test_parent_recovers_from_legacy_native_stdout_chatter(self):
        """Unstructured native output must not be parsed as a worker response."""
        from openvoice.engines.neural import _Worker
        with tempfile.TemporaryDirectory() as d, \
             patch.dict(os.environ, {'OPENMUKTI_NEURAL_HOME':d}):
            script = Path(d) / 'noisy_legacy_worker.py'
            script.write_text('''import os,sys,json
for line in sys.stdin:
 os.write(1, b"native library diagnostic\\n")
 print(json.dumps({'ok': True, 'engine': 'kokoro'}), flush=True)
''', encoding='utf-8')
            worker = _Worker(Path(sys.executable), script, 'kokoro')
            try:
                self.assertEqual(worker.request({'action':'download'})['engine'], 'kokoro')
            finally:
                worker.close()
            self.assertIn('native library diagnostic', worker.log_path.read_text())

    def test_worker_isolates_native_and_child_process_stdout(self):
        """C writes and child program output must go to worker.log, never JSON."""
        from openvoice.engines.neural import _Worker
        source_root = str(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as d, \
             patch.dict(os.environ, {'OPENMUKTI_NEURAL_HOME':d}):
            script = Path(d) / 'native_noisy_worker.py'
            script.write_text('''import sys, os, subprocess
sys.path.insert(0, {source_root!r})
import openvoice.neural_worker as nw
def fake_process(payload):
    os.write(1,b"native library message\\n")
    subprocess.run([sys.executable,'-c','print(\"child output\")'],check=True)
    print('python logging')
    return {'engine':'kokoro'}
nw.process = fake_process
nw.main()
'''.replace('{source_root!r}', repr(source_root)), encoding='utf-8')
            worker = _Worker(Path(sys.executable), script, 'kokoro', allow_download=True)
            try:
                self.assertEqual(worker.request({'action':'test'})['engine'], 'kokoro')
                self.assertEqual(worker.request({'action':'test'})['ok'], True)
            finally:
                worker.close()
            log = worker.log_path.read_text(encoding='utf-8')
            self.assertIn('native library message', log)
            self.assertIn('child output', log)
            self.assertIn('python logging', log)
            self.assertNotIn('non-protocol stdout', log)


class FakeInferenceTests(unittest.TestCase):
    def setUp(self):
        from openvoice import neural_worker as worker
        self.worker=worker
        worker._MODEL_CACHE.clear()
        worker._VOICE_CACHE.clear()
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.counter={}

    def output(self,key):
        self.counter[key]=self.counter.get(key,0)+1
        target=Path(self.temp.name)/f'{key}{self.counter[key]}.wav'
        return str(target)

    @staticmethod
    def fake_soundfile(path, samples, sample_rate):
        Path(path).write_bytes(b'RIFF'+b'0'*44)

    def test_kokoro_languages_and_model_reuse(self):
        import numpy as np
        instances=[]
        class Pipeline:
            def __init__(self,lang_code,device):
                self.lang_code,self.device=lang_code,device
                instances.append(self)
            def __call__(self,text,voice,speed):
                self.last=(text,voice,speed)
                yield (None,None,np.zeros(400,dtype=np.float32))
        with patch.dict(sys.modules, {'kokoro':types.SimpleNamespace(KPipeline=Pipeline),
                                      'soundfile':types.SimpleNamespace(write=self.fake_soundfile)}):
            self.worker.synthesize({'engine':'kokoro','text':'こんにちは','voice':'jf_alpha',
                                    'output':self.output('kokoro'), 'rate':3})
            self.worker.synthesize({'engine':'kokoro','text':'もう一度','voice':'jm_kumo',
                                    'output':self.output('kokoro'), 'rate':0})
        self.assertEqual(len(instances),1)
        self.assertEqual(instances[0].lang_code,'j')
        self.assertEqual(instances[0].device,'cpu')
        self.assertEqual(instances[0].last[1],'jm_kumo')

    def test_kitten_speaker_and_speed(self):
        models=[]
        class Kitten:
            available_voices=['Bella','Jasper']
            def __init__(self, model):
                self.model=model
                models.append(self)
            def generate(self,text,voice,speed):
                self.call=(text,voice,speed)
                return [0.0]*100
        with patch.dict(sys.modules, {'kittentts':types.SimpleNamespace(KittenTTS=Kitten),
                                      'soundfile':types.SimpleNamespace(write=self.fake_soundfile)}):
            self.worker.synthesize({'engine':'kitten','text':'Hi','voice':'Jasper',
                                    'output':self.output('kitten'), 'rate':5})
            self.worker.synthesize({'engine':'kitten','text':'Again','voice':'Bella',
                                    'output':self.output('kitten'), 'rate':0})
        self.assertEqual(len(models),1)
        self.assertEqual(models[0].call[1],'Bella')
        self.assertEqual(models[0].model,'KittenML/kitten-tts-nano-0.8')

    def test_pocket_cpu_voice_state_cache(self):
        import numpy as np
        models=[]
        class Audio:
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return np.zeros(200,dtype=np.float32)
        class Model:
            sample_rate=24000
            def __init__(self):
                models.append(self)
                self.states=[]
            @classmethod
            def load_model(cls, **kwargs): return cls()
            def get_state_for_audio_prompt(self,voice):
                self.states.append(voice)
                return voice
            def generate_audio(self,prompt,text): return Audio()
        saved=[]
        def write(path,rate,audio):
            saved.append((path,rate))
            Path(path).write_bytes(b'RIFF'+b'0'*44)
        scipy_stub = types.ModuleType('scipy')
        scipy_stub.__path__ = []
        io_stub = types.ModuleType('scipy.io')
        io_stub.__path__ = []
        wavfile_stub = types.ModuleType('scipy.io.wavfile')
        wavfile_stub.write = write
        scipy_stub.io = io_stub
        io_stub.wavfile = wavfile_stub
        with patch.dict(sys.modules, {'pocket_tts': types.SimpleNamespace(TTSModel=Model),
                                      'scipy': scipy_stub, 'scipy.io': io_stub,
                                      'scipy.io.wavfile': wavfile_stub}):
            self.worker.synthesize({'engine':'pocket','text':'Hello','voice':'alba','output':self.output('pocket')})
            self.worker.synthesize({'engine':'pocket','text':'Again','voice':'alba','output':self.output('pocket')})
        self.assertEqual(len(models),1)
        self.assertEqual(models[0].states,['alba'])
        self.assertEqual(len(saved),2)

    def test_coqui_speakers_and_languages(self):
        models=[]
        class Coqui:
            speakers=['p225','p226']
            languages=['en','fr']
            def __init__(self, name):
                self.name=name
                models.append(self)
            def to(self,device):
                self.device=device
                return self
            def tts_to_file(self, **kwargs):
                self.kwargs=kwargs
                Path(kwargs['file_path']).write_bytes(b'RIFF'+b'0'*44)
        with patch.dict(sys.modules, {'TTS':types.ModuleType('TTS'),
                                      'TTS.api':types.SimpleNamespace(TTS=Coqui)}):
            self.assertEqual(self.worker.process({'action':'voices','engine':'coqui','model':'tts_models/en/vctk/vits'})['voices'],['p225','p226'])
            self.worker.synthesize({'engine':'coqui','text':'Bonjour','model':'tts_models/en/vctk/vits',
                                    'voice':'p226','language':'fr','output':self.output('coqui')})
            self.assertEqual(len(models),1)
            self.assertEqual(models[0].device,'cpu')
            self.assertEqual(models[0].kwargs['speaker'],'p226')
            self.assertEqual(models[0].kwargs['language'],'fr')


if __name__ == '__main__': unittest.main()
