from __future__ import annotations
from openvoice.acceleration import load_voice
import argparse
import sys
import wave
from pathlib import Path


def to_phonemes(ipa: str, mapping: dict) -> list[str]:
    known = sorted((key for key in mapping if isinstance(key, str) and key and key not in {'^','$','_'}), key=len, reverse=True)
    sequence = []
    index = 0
    while index < len(ipa):
        if ipa[index].isspace() or ipa[index] in '.|/[]':
            index += 1
            continue
        token = next((item for item in known if ipa.startswith(item, index)), None)
        if token is None:
            raise ValueError(f'The selected Piper voice does not contain IPA symbol {ipa[index]!r}. Choose a compatible model or provide a spoken fallback.')
        sequence.append(token)
        index += len(token)
    if not sequence:
        raise ValueError('No supported IPA phonemes were found')
    return sequence


def main() -> int:
    parser = argparse.ArgumentParser(description='Bundled Piper synthesis helper for Openmukti')
    parser.add_argument('--health', action='store_true')
    parser.add_argument('--mode', choices=('ipa', 'text'))
    parser.add_argument('--model')
    parser.add_argument('--config')
    parser.add_argument('--output')
    parser.add_argument('--ipa', default='')
    parser.add_argument('--text', default='')
    parser.add_argument('--speaker-id', type=int)
    parser.add_argument('--length-scale', type=float, default=1.0)
    args = parser.parse_args()
    try:
        from piper.voice import PiperVoice
        from piper.config import SynthesisConfig
        import onnxruntime
        if args.health:
            print('Piper worker ready; ONNX Runtime', onnxruntime.__version__)
            return 0
        if not args.model or not args.config or not args.output or not args.mode:
            parser.error('mode, model, config, and output are required for synthesis')
        if not (0.2 <= args.length_scale <= 4.0):
            parser.error('length-scale is outside safe range')
        voice = load_voice(PiperVoice, args.model, args.config)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        options = SynthesisConfig(length_scale=args.length_scale, speaker_id=args.speaker_id)
        with wave.open(str(output), 'wb') as wav:
            if args.mode == 'text':
                voice.synthesize_wav(args.text, wav, syn_config=options)
            else:
                tokens = to_phonemes(args.ipa, voice.config.phoneme_id_map)
                ids = voice.phonemes_to_ids(tokens)
                if len(ids) < 3:
                    raise ValueError('IPA could not be converted to phoneme IDs')
                audio = voice.phoneme_ids_to_audio(ids, syn_config=options)
                import numpy as np
                pcm = (np.clip(np.asarray(audio), -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(voice.config.sample_rate)
                wav.writeframes(pcm)
        return 0
    except Exception as exc:
        print(f'Piper synthesis failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
