#!/usr/bin/env python3
"""Render natural-sounding narration with the local Kokoro voices.

Instead of a single fixed speed, every sentence gets its own speed, micro-pause,
pitch offset and level, so the delivery breathes like a person talking.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline

from src.util import SR


def split_paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", text.strip())
    return [" ".join(b.split()) for b in blocks if b.strip()]


def split_sentences(paragraph: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", paragraph)
    return [p.strip() for p in parts if p.strip()]


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def sentence_speed(sentence: str, idx: int, base: float, rng: random.Random) -> float:
    n = len(sentence)
    speed = base
    if sentence.endswith("?"):
        speed -= 0.02
    if n < 45:
        speed += 0.03
    elif n > 150:
        speed -= 0.03
    speed += 0.02 * math.sin(idx * 0.7)
    speed += rng.uniform(-0.025, 0.025)
    return clamp(speed, base - 0.10, base + 0.08)


def sentence_pause(sentence: str, rng: random.Random) -> float:
    pause = 0.30 + rng.uniform(0.0, 0.12)
    if sentence.endswith("?"):
        pause += 0.15
    if len(sentence) < 40:
        pause += 0.05
    return pause


def render_sentence(text, voice, speed, pitch_cents, gain_db, pipe, tmpdir, use_pitch):
    chunks = [np.asarray(a, dtype=np.float32) for _, _, a in pipe(text, voice=voice, speed=speed)]
    y = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    if use_pitch and abs(pitch_cents) >= 3:
        raw = tmpdir / "raw.wav"
        proc = tmpdir / "proc.wav"
        sf.write(raw, y, SR)
        ratio = 2.0 ** (pitch_cents / 1200.0)
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
                "-af", f"rubberband=pitch={ratio:.6f}:formant=preserved",
                "-ar", str(SR), "-ac", "1", str(proc),
            ],
            check=True,
        )
        y, _ = sf.read(proc, dtype="float32")
    return y * (10.0 ** (gain_db / 20.0))


def build(text, voice, base_speed, seed, use_pitch):
    rng = random.Random(seed)
    lang = "b" if voice.startswith(("bf_", "bm_")) else "a"
    pipe = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    pieces: list[np.ndarray] = []
    idx = 0
    paragraphs = split_paragraphs(text)
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for p_i, paragraph in enumerate(paragraphs):
            sentences = split_sentences(paragraph)
            for s_i, sentence in enumerate(sentences):
                speed = sentence_speed(sentence, idx, base_speed, rng)
                pitch = 18.0 * math.sin(idx * 0.43) + rng.uniform(-18.0, 18.0)
                gain = rng.uniform(-1.0, 1.0)
                audio = render_sentence(
                    sentence, voice, speed, pitch, gain, pipe, tmpdir, use_pitch
                )
                pieces.append(audio)
                idx += 1
                if s_i < len(sentences) - 1:
                    pieces.append(np.zeros(int(SR * sentence_pause(sentence, rng)), dtype=np.float32))
            if p_i < len(paragraphs) - 1:
                gap = 0.65 + rng.uniform(0.0, 0.20)
                if len(paragraph) < 60 or paragraph.endswith("?"):
                    gap += 0.30
                pieces.append(np.zeros(int(SR * gap), dtype=np.float32))
    y = np.concatenate(pieces).astype(np.float32)
    peak = float(np.max(np.abs(y))) + 1e-12
    if peak > 0.97:
        y *= 0.97 / peak
    return y


def master(src: Path, out_wav: Path, out_mp3: Path, lufs: float = -16.0, tp: float = -1.5):
    pre = (
        "highpass=f=70,"
        "acompressor=threshold=-20dB:ratio=2.5:attack=15:release=250:makeup=1"
    )
    probe = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(src), "-af",
         f"{pre},loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    stats = json.loads(probe.stderr[probe.stderr.rfind("{"):])
    norm = (
        f"loudnorm=I={lufs}:TP={tp}:LRA=11:"
        f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
        f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
        f"offset={stats['target_offset']}:linear=true"
    )
    chain = f"{pre},{norm},afade=t=in:st=0:d=0.08,aresample=48000"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", chain,
         "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(out_wav),
         "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
        check=True,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text-file", required=True)
    ap.add_argument("--voice", default="am_fenrir")
    ap.add_argument("--speed", type=float, default=0.95, help="base speed; each sentence varies around it")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--max-words", type=int, default=0, help="limit for auditions")
    ap.add_argument("--no-master", action="store_true")
    ap.add_argument("--no-pitch", action="store_true")
    args = ap.parse_args()

    text = Path(args.text_file).read_text(encoding="utf-8")
    if args.max_words:
        words = text.split()
        text = " ".join(words[: args.max_words])
        if not text.rstrip().endswith((".", "!", "?")):
            text += "."

    y = build(text, args.voice, args.speed, args.seed, not args.no_pitch)
    out_wav = Path(f"{args.out_prefix}.wav")
    out_mp3 = Path(f"{args.out_prefix}.mp3")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_wav, y, SR)
    print(f"raw: {len(y) / SR:.1f}s -> {out_wav}")

    if not args.no_master:
        raw = out_wav.with_name(out_wav.stem + ".raw.wav")
        out_wav.rename(raw)
        master(raw, out_wav, out_mp3)
        raw.unlink()
        print(f"master: {out_wav}  {out_mp3}")


if __name__ == "__main__":
    main()
