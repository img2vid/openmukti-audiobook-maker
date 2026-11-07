from __future__ import annotations
import math
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from .engines.base import EngineError, RunControl, invoke
from .fftools import find_binary


@dataclass(frozen=True)
class VoiceDesign:
    semitones: float = 0.0
    speed_adjust: int = 0
    bass_db: float = 0.0
    treble_db: float = 0.0
    energy_db: float = 0.0
    compression: float = 0.0
    name: str = "Natural"


AGE_DESIGNS = {
    "unspecified": (0.0, 0, 0.0, 0.0),
    "child": (4.0, 1, -1.0, 1.2),
    "teen": (1.7, 1, -0.3, 0.5),
    "young adult": (0.0, 0, 0.0, 0.0),
    "adult": (0.0, 0, 0.0, 0.0),
    "middle aged": (-0.7, -1, 0.8, -0.3),
    "senior": (-1.6, -2, 1.0, -0.8),
    "elderly": (-1.6, -2, 1.0, -0.8),
}

GENDER_DESIGNS = {
    "unspecified": (0.0, 0.0),
    "female": (2.3, -0.7),
    "male": (-2.3, 1.3),
    "nonbinary": (0.0, 0.0),
    "androgynous": (0.0, 0.0),
}

STYLE_DESIGNS = {
    "natural": (0.0, 0, 0.0, 0.0, 0.0, 0.0),
    "warm": (-0.2, -1, 1.8, -0.6, 0.0, 0.0),
    "calm": (-0.4, -2, 0.4, -0.2, -0.8, 0.0),
    "expressive": (0.6, 1, 0.2, 0.8, 1.0, 0.35),
    "serious": (-0.6, -1, 0.9, -0.2, 0.0, 0.15),
    "cheerful": (0.9, 2, -0.5, 1.1, 0.9, 0.15),
    "dramatic": (-0.2, -1, 1.0, 0.9, 1.4, 0.65),
    "gentle": (0.3, -2, 0.3, -1.0, -1.0, 0.0),
    "soft": (0.0, -2, 0.3, -1.2, -1.2, 0.0),
    "energetic": (0.7, 3, -0.3, 1.2, 1.4, 0.45),
    "mysterious": (-1.0, -2, 2.0, -1.1, -0.5, 0.1),
    "gruff": (-1.8, -1, 2.5, -1.5, 0.0, 0.2),
    "whispery": (0.0, -3, -0.7, -2.0, -2.2, 0.0),
    "angry": (-0.4, 2, 1.4, 0.8, 1.2, 0.5),
    "sad": (-0.7, -3, 0.0, -1.0, -1.0, 0.0),
    "shy": (0.4, -2, 0.0, -0.9, -1.6, 0.0),
    "confident": (-0.4, 0, 1.0, 0.6, 1.0, 0.4),
    "robotic": (0.0, -1, -1.0, -1.3, -0.5, 0.7),
    "villainous": (-1.4, -2, 2.2, -1.2, 0.5, 0.5),
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def design_for_profile(profile) -> VoiceDesign:
    strength = _clamp(float(getattr(profile, "design_strength", 85)), 0, 100) / 100
    pitch = _clamp(float(getattr(profile, "pitch", 0)), -10, 10) * 0.55 * strength
    age = str(getattr(profile, "age", "Unspecified")).strip().casefold()
    gender = str(getattr(profile, "gender", "Unspecified")).strip().casefold()
    age_pitch, age_rate, age_bass, age_treble = AGE_DESIGNS.get(
        age, AGE_DESIGNS["unspecified"]
    )
    gender_pitch, gender_bass = GENDER_DESIGNS.get(
        gender, GENDER_DESIGNS["unspecified"]
    )
    style_names = [
        s.strip().casefold()
        for s in str(getattr(profile, "characteristics", "natural"))
        .replace(";", ",")
        .split(",")
        if s.strip()
    ]
    if not style_names:
        style_names = ["natural"]
    style_effects = [STYLE_DESIGNS[s] for s in style_names if s in STYLE_DESIGNS]
    if not style_effects:
        style_effects = [STYLE_DESIGNS["natural"]]
    style_pitch = sum(e[0] for e in style_effects) / len(style_effects)
    style_rate = sum(e[1] for e in style_effects) / len(style_effects)
    style_bass = sum(e[2] for e in style_effects) / len(style_effects)
    style_treble = sum(e[3] for e in style_effects) / len(style_effects)
    style_energy = sum(e[4] for e in style_effects) / len(style_effects)
    style_compression = max(e[5] for e in style_effects)
    return VoiceDesign(
        semitones=round(
            _clamp(
                pitch + strength * (age_pitch + gender_pitch + style_pitch), -9.0, 9.0
            ),
            2,
        ),
        speed_adjust=int(round(_clamp(strength * (age_rate + style_rate), -5, 5))),
        bass_db=round(
            _clamp(strength * (age_bass + gender_bass + style_bass), -6, 6), 2
        ),
        treble_db=round(_clamp(strength * (age_treble + style_treble), -6, 6), 2),
        energy_db=round(_clamp(strength * style_energy, -4, 4), 2),
        compression=round(strength * style_compression, 3),
        name=", ".join(style_names),
    )


@lru_cache(maxsize=8)
def _supports_rubberband(ffmpeg: str) -> bool:
    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
        return result.returncode == 0 and any(
            "rubberband" in line.split() for line in result.stdout.splitlines()
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def audio_filters(
    design: VoiceDesign,
    *,
    rubberband: bool,
    sample_rate: int = 24000,
    gain: float = 1.0,
) -> list[str]:
    parts = []
    if abs(design.semitones) > 0.03:
        pitch = 2.0 ** (design.semitones / 12.0)
        if rubberband:
            parts.append(
                f"rubberband=pitch={pitch:.6f}:transients=smooth:detector=compound"
            )
        else:
            parts.extend(
                [
                    f"aresample={sample_rate}",
                    f"asetrate={round(sample_rate * pitch)}",
                    f"aresample={sample_rate}",
                    f"atempo={1 / pitch:.6f}",
                ]
            )
    if abs(design.bass_db) > 0.05:
        parts.append(f"bass=g={design.bass_db:.2f}:f=160")
    if abs(design.treble_db) > 0.05:
        parts.append(f"treble=g={design.treble_db:.2f}:f=3500")
    if design.compression > 0.05:
        ratio = 1.0 + design.compression * 3.0
        parts.append(
            f"acompressor=threshold=0.28:ratio={ratio:.2f}:attack=12:release=130"
        )
    if abs(design.energy_db) > 0.05:
        parts.append(f"volume={design.energy_db:.2f}dB")
    if not math.isfinite(gain) or not 0 <= gain <= 1:
        raise ValueError("Character volume gain must be between 0 and 1")
    if gain != 1.0:
        parts.append(f"volume={gain:.6f}")
    return parts


def process_character_audio(
    source: Path,
    output: Path,
    design: VoiceDesign,
    *,
    control: RunControl | None = None,
    gain: float = 1.0,
) -> Path:
    ffmpeg = find_binary("ffmpeg")
    if not ffmpeg:
        raise EngineError(
            "FFmpeg is required for the character voice effects. Bundle FFmpeg or install it first."
        )
    filters = audio_filters(design, rubberband=_supports_rubberband(ffmpeg), gain=gain)
    if control:
        control.check()
    args = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-ar",
        "24000",
        "-ac",
        "1",
        "-af",
        ",".join(filters) if filters else "anull",
        "-c:a",
        "pcm_s16le",
        str(output),
    ]
    invoke(args, control=control)
    if not output.is_file() or output.stat().st_size < 44:
        raise EngineError(
            f"Character audio effect failed to produce WAV: {output.name}"
        )
    return output
