import math
from pathlib import Path
import tempfile
import unittest
import wave
from openvoice.timeline_tags import parse_duration, parse_timeline, has_timeline_tags
from openvoice.timeline_audio import Clip, plan_timeline, mix_timeline, duration_ms, resolve_sfx
from openvoice.fftools import find_binary
from openvoice.character_voices import CharacterProfile, VoiceProject
from openvoice.project_archive import ProjectData, save_project, load_project


def tone(path, seconds=1.0, hz=440, rate=16000):
    import struct
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b''.join(struct.pack('<h', int(5000*math.sin(i*hz*2*math.pi/rate)))
                                 for i in range(int(seconds*rate))))


class DurationTests(unittest.TestCase):
    def test_units_and_variations(self):
        expected = {'520ms':520, '0.9s':900, 'five seconds':5000,
                    '1m 30s':90000, '1 hour 2 min 3.19 sec':3723190,
                    '01:02:03.190':3723190, '2h':7200000,
                    'half a second':500, '.25 hr':900000}
        for fmt, milliseconds in expected.items():
            with self.subTest(fmt=fmt):
                self.assertEqual(parse_duration(fmt), milliseconds)
        for bad in ('nan seconds', '-3s', '999h', '3 elephants', '1:89', '5s nonsense'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError): parse_duration(bad)

    def test_examples(self):
        a = parse_timeline('[Mary][pause: 2s] Hi!', ['Mary'])
        self.assertEqual((a.passages[0].speaker,a.passages[0].pause_ms),('Mary', 2000))
        b = parse_timeline('[John][p:0.9s]How are you?', ['John'])
        self.assertEqual(b.passages[0].pause_ms,900)
        c = parse_timeline('[Mary, 3s]Hi!', ['Mary'])
        self.assertEqual(c.passages[0].duration_ms,3000)
        self.assertEqual(c.passages[0].pause_ms,0)
        d = parse_timeline('[John][5 seconds]How are you?', ['John'])
        self.assertEqual(d.passages[0].pause_ms,5000)
        e = parse_timeline('[Alice, 520ms, sfx:abc.mp3(200ms-510ms), 3.19s, '
                           'sfx:def.mp3(2s-3s)]Please will you go to my party?', ['Alice'])
        p = e.passages[0]
        self.assertEqual((p.pause_ms,p.duration_ms),(520,3190))
        self.assertEqual([(q.name,q.start_ms,q.length_ms,q.anchor) for q in p.cues],
                         [('abc.mp3',200,310,'pause'),('def.mp3',2000,1000,'speech')])

    def test_informal_speaker_overlap_and_ipa(self):
        text = '[spoken by Mary, speak for 2 seconds]Hi! [John speaks, interrupt after 0.5s]Stop!' \
               '[background:street.mp3]'
        result = parse_timeline(text, ['Mary','John'])
        self.assertEqual([p.speaker for p in result.passages],['Mary','John'])
        self.assertEqual(result.passages[1].interrupt_ms,500)
        self.assertEqual(result.sounds[0].anchor,'background')
        self.assertFalse(has_timeline_tags('[Mary]Hello'))
        self.assertTrue(has_timeline_tags('[Mary, 2s]Hello'))
        ipa = parse_timeline('[Mary][ipa: həˈloʊ|hello]!', ['Mary'])
        self.assertIn('<ipa:həˈloʊ|hello>',ipa.passages[0].text)


class AudioTests(unittest.TestCase):
    def test_persistent_sound_asset_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sound = root/'door.wav'
            tone(sound,0.4)
            voice = VoiceProject([CharacterProfile('Narrator')],sound_files=[str(sound)])
            archive = root/'scene.oamproj'
            save_project(archive,ProjectData(text='[sfx:door.wav]Hello',voice_project=voice))
            loaded = load_project(archive,root/'restored')
            self.assertEqual(len(loaded.voice_project.sound_files),1)
            self.assertTrue(Path(loaded.voice_project.sound_files[0]).is_file())
            self.assertEqual(resolve_sfx('door.wav',loaded.voice_project.sound_files).name,'door.wav')

    @unittest.skipUnless(find_binary('ffmpeg'), 'FFmpeg unavailable')
    def test_timed_wav_mix(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            voice=root/'voice.wav';fx=root/'abc.wav';fx2=root/'def.wav'
            tone(voice,1.5);tone(fx,1.5,700);tone(fx2,1.5,250)
            scene=parse_timeline('[Alice, 520ms, sfx:abc.wav(200ms-510ms), '
                                 '3.19s, sfx:def.wav(2s-3s)]Please!', ['Alice'])
            clips,end=plan_timeline(scene,[voice],[str(fx),str(fx2)],default_pause_ms=0)
            self.assertEqual(end,3710)
            self.assertEqual([(clip.start_ms,clip.length_ms) for clip in clips],
                             [(520,3190),(200,310),(2520,1000)])
            output=root/'mixed.wav'
            mix_timeline(clips,output,end)
            self.assertAlmostEqual(duration_ms(output),end,delta=15)

    @unittest.skipUnless(find_binary('ffmpeg'), 'FFmpeg unavailable')
    def test_full_renderer_with_speech_stub(self):
        from openvoice.multivoice import render_multivoice
        from openvoice.engines.base import SpeechSettings
        class TestEngine:
            key = 'test'
            supports_volume = False
            supports_pitch = False
            def render_wav(self, text, output, settings, control=None):
                tone(output, 0.8)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tone(root/'street.wav',0.5)
            project = VoiceProject([CharacterProfile('Narrator',design_strength=0),
                                    CharacterProfile('Mary',design_strength=0),
                                    CharacterProfile('John',design_strength=0)],
                                   sound_files=[str(root/'street.wav')])
            content = '[background:street.wav][Mary, pause:200ms, duration:1.5s]Hi! ' \
                      '[John, overlap:500ms]Good morning.'
            output = root/'scene.wav'
            render_multivoice(content, output, project, default_engine=TestEngine(),
                              default_settings=SpeechSettings())
            self.assertTrue(output.is_file())
            self.assertGreater(duration_ms(output), 1600)

    @unittest.skipUnless(find_binary('ffmpeg'), 'FFmpeg unavailable')
    def test_interrupt_and_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ('voice1.wav','voice2.wav','street.wav'):
                tone(root/name,1.2)
            scene=parse_timeline('[background:street.wav][Alice]Hello!'
                                 '[Bob, interrupt after 300ms]Stop!', ['Alice','Bob'])
            clips,end=plan_timeline(scene,[root/'voice1.wav',root/'voice2.wav'],
                                    [str(root/'street.wav')],default_pause_ms=0)
            self.assertEqual(clips[0].length_ms,300)
            self.assertEqual(clips[1].start_ms,300)
            self.assertTrue(clips[2].loop)
            mixed=root/'scene.wav'
            mix_timeline(clips,mixed,end)
            self.assertAlmostEqual(duration_ms(mixed),end,delta=15)

if __name__=='__main__':unittest.main()
