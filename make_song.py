#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time

import numpy as np
import soundfile as sf
import yaml

from src.util import SR, db_to_lin, rms, mix_at, to_stereo, fade
from src.voice import split_script, synth_phrase, syllables
from src.sing import sing_phrase, estimate_tonic
from src.melody import extract_contour, estimate_tempo
from src.bed import render_bed
from src.fx import (
    reverb,
    delay,
    compressor,
    deess,
    highpass,
    low_shelf,
    high_shelf,
    saturate,
)
from src.master import finalize, limiter
from src.fx import breath


def load_style(name):
    if os.path.isfile(name):
        path = name
    else:
        path = os.path.join(os.path.dirname(__file__), "styles", f"{name}.yaml")
    if not os.path.isfile(path):
        raise SystemExit(f"Style not found: {name}")
    with open(path, "r", encoding="utf-8") as f:
        style = yaml.safe_load(f)
    style.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    return style


def melody_slice(style, index):
    mel = style.get("melody") or [0, 2, 0]
    start = (index * 2) % len(mel)
    n = style.get("notes_per_phrase", 2)
    return [mel[(start + i) % len(mel)] for i in range(n)]


def main():
    ap = argparse.ArgumentParser(description="Render a devotional AI-sung track.")
    ap.add_argument("--style", default="mantra", help="mantra | bhajan | lofi | path.yaml")
    ap.add_argument("--text", default=None)
    ap.add_argument("--text-file", default=None)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--backend", choices=("kokoro", "chatterbox"), default=None)
    ap.add_argument("--chatterbox-model", default=None)
    ap.add_argument("--chatterbox-voice", default=None)
    ap.add_argument("--exaggeration", type=float, default=None)
    ap.add_argument("--speed", type=float, default=None)
    ap.add_argument("--repeat", type=int, default=None)
    ap.add_argument("--no-sing", action="store_true")
    ap.add_argument("--tonic", type=float, default=None)
    ap.add_argument("--reference", default=None, help="Reference track for Matchering")
    ap.add_argument(
        "--melody-audio",
        default=None,
        help="Hummed (or owned) mono clip whose melody the singer follows",
    )
    ap.add_argument(
        "--tempo-from-melody",
        action="store_true",
        help="Estimate BPM from --melody-audio instead of the style",
    )
    ap.add_argument("--bpm", type=float, default=None)
    ap.add_argument("--call-response", dest="call_response", action="store_true", default=None)
    ap.add_argument("--no-call-response", dest="call_response", action="store_false")
    ap.add_argument("--lufs", type=float, default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--keep-stems", action="store_true")
    args = ap.parse_args()

    style = load_style(args.style)
    seed = args.seed if args.seed is not None else int(time.time()) % 100000
    rng = np.random.default_rng(seed)
    voice = args.voice or style.get("default_voice", "hm_psi")
    speed = args.speed if args.speed is not None else style.get("default_speed", 0.85)
    repeat = args.repeat if args.repeat is not None else style.get("default_repeat", 1)
    sing = not args.no_sing and style.get("sing", True)
    backend = (args.backend or style.get("backend", "kokoro")).lower()
    cb = None
    cb_cfg = style.get("chatterbox") or {}
    cb_lang = cb_cfg.get("language", "hi")
    cb_exag = (
        args.exaggeration
        if args.exaggeration is not None
        else float(cb_cfg.get("exaggeration", 0.35))
    )
    cb_temp = float(cb_cfg.get("temperature", 0.8))
    cb_top_p = float(cb_cfg.get("top_p", 0.95))
    cb_min_p = float(cb_cfg.get("min_p", 0.05))
    cb_max = int(cb_cfg.get("max_new_tokens", 1000))
    if backend == "chatterbox":
        from src.chatterbox_onnx import ChatterboxONNX

        model_dir = (
            args.chatterbox_model
            or os.environ.get("CHATTERBOX_MODEL_DIR")
            or cb_cfg.get("model_dir")
            or "assets/chatterbox_onnx"
        )
        if not os.path.isdir(model_dir):
            raise SystemExit(
                f"Chatterbox model dir not found: {model_dir}\n"
                "Download the ONNX model and set CHATTERBOX_MODEL_DIR."
            )
        voice_path = args.chatterbox_voice or cb_cfg.get("voice") or None
        print(f"      TTS backend = chatterbox ({model_dir})")
        cb = ChatterboxONNX(
            model_dir,
            voice_path=voice_path,
            threads=int(cb_cfg.get("threads", os.cpu_count() or 4)),
        )

    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        text = style.get("default_text", "ॐ नमः शिवाय।")

    events = split_script(text)
    phrases = [v for k, v in events if k == "phrase"]
    if not phrases:
        raise SystemExit("No lyrics found in the text.")

    ref_semis = None
    ref_tonic = None
    if args.melody_audio:
        ref_semis, ref_tonic, ref_dur = extract_contour(args.melody_audio)
        print(f"      melody reference = {ref_dur:.2f}s, tonic {ref_tonic:.1f} Hz")

    if args.bpm is not None:
        bpm = float(args.bpm)
    elif args.tempo_from_melody and args.melody_audio:
        bpm = estimate_tempo(args.melody_audio)
    else:
        bpm = float(style["bpm"])
    beat = 60.0 / bpm
    bar = 4.0 * beat

    print(f"[1/6] voice synthesis: {len(phrases)} phrases x {repeat}")
    raw = {}
    for p in phrases:
        if backend == "chatterbox":
            raw[p] = cb.synth(
                p,
                language_id=cb_lang,
                exaggeration=cb_exag,
                max_new_tokens=cb_max,
                temperature=cb_temp,
                top_p=cb_top_p,
                min_p=cb_min_p,
                seed=seed + len(raw),
                verbose=True,
            )
        else:
            raw[p] = synth_phrase(p, voice=voice, speed=speed)

    orn = style.get("ornament") or {}
    sing_kwargs = {
        "vibrato": float(orn.get("vibrato", 0.22)),
        "vibrato_rate": float(orn.get("vibrato_rate", 4.8)),
        "vibrato_onset": float(orn.get("vibrato_onset", 0.35)),
        "scoop": float(orn.get("scoop", 0.5)),
        "glide_ms": float(orn.get("glide_ms", 55.0)),
        "kan": float(orn.get("kan", 0.0)),
        "taan": float(orn.get("taan", 0.0)),
        "sustain": float(
            cb_cfg.get("sustain", style.get("sustain", 1.0))
            if backend == "chatterbox"
            else style.get("sustain", 1.0)
        ),
        "ref_semis": ref_semis,
        "drift_cents": float(orn.get("drift_cents", 0.0)),
        "drift_rate": float(orn.get("drift_rate", 0.13)),
        "vibrato_irregular": float(orn.get("vibrato_irregular", 0.20)),
    }

    cr = dict(style.get("call_response") or {})
    if args.call_response is not None:
        cr["enabled"] = args.call_response
    cr_on = bool(cr.get("enabled", False)) and sing
    raw_resp = {}
    resp_voice = None
    if cr_on:
        resp_voice = cr.get("voice") or (
            "chatterbox" if backend == "chatterbox"
            else ("hm_omega" if voice.startswith("hf") else "hf_alpha")
        )
        print(f"      call-response voice = {resp_voice}")
        for p in phrases:
            if backend == "chatterbox":
                raw_resp[p] = cb.synth(
                    p,
                    language_id=cb_lang,
                    exaggeration=min(0.7, cb_exag + 0.10),
                    max_new_tokens=cb_max,
                    temperature=cb_temp,
                    seed=seed + 1000 + len(raw_resp),
                    verbose=True,
                )
            else:
                raw_resp[p] = synth_phrase(
                    p, voice=resp_voice, speed=speed * float(cr.get("speed", 1.0))
                )

    if args.tonic is not None:
        tonic = float(args.tonic)
    elif ref_tonic is not None:
        tonic = float(ref_tonic)
        if voice.startswith("hf"):
            while tonic < 160.0:
                tonic *= 2.0
            while tonic > 340.0:
                tonic /= 2.0
        else:
            while tonic < 90.0:
                tonic *= 2.0
            while tonic > 210.0:
                tonic /= 2.0
    else:
        probe = np.concatenate([raw[p] for p in phrases[:3]])
        tonic = estimate_tonic(probe, SR, float(style.get("tonic_hz", 130.81)))
    print(f"      tonic = {tonic:.2f} Hz, bpm = {bpm:g}, sing = {sing}")

    intro = float(style.get("intro_bars", 1.5)) * bar
    outro = float(style.get("outro_bars", 1.5)) * bar + 2.5
    cursor = int(intro * SR)
    grid = max(1, int(beat / 2.0 * SR))
    timeline = []
    sung_cache = {}

    print("[2/6] singing + humanizing")
    n_phrases = len(phrases)
    section_pause = float(style.get("section_pause_sec", 2.0))
    for rep in range(repeat):
        phrase_idx = 0
        for kind, value in events:
            if kind == "pause":
                sec = section_pause * float(value) * rng.uniform(0.9, 1.15)
                cursor += int(round(sec * SR / grid)) * grid
                continue
            p = value
            idx = phrase_idx
            global_idx = rep * n_phrases + idx
            base = raw[p]
            if sing:
                offsets = melody_slice(style, global_idx)
                pitch_j = float(style.get("pitch_jitter_cents", 0.0))
                phrase_tonic = tonic
                if pitch_j > 0.0:
                    phrase_tonic = tonic * 2.0 ** (
                        rng.uniform(-pitch_j, pitch_j) / 1200.0
                    )
                natural = len(base) / SR
                target = max(
                    natural * 0.98,
                    syllables(p) * float(style.get("syllable_sec", 0.34)),
                )
                if p.strip() in ("ॐ", "ओम"):
                    target = max(target, float(style.get("om_sec", 0.0)))
                target = max(beat, round(target / (beat / 2.0)) * (beat / 2.0))
                tj = float(style.get("timing_jitter", 0.01))
                target *= rng.uniform(1.0 - tj, 1.0 + tj)
                pt = round(phrase_tonic, 3)
                deep_seed = int(seed + rep * 10000 + idx * 37)
                if ref_semis is not None:
                    key = ("lead-ref", p, round(target, 3), pt, deep_seed)
                else:
                    key = ("lead", p, tuple(offsets), round(target, 3), pt, deep_seed)
                if key not in sung_cache:
                    kw = dict(sing_kwargs)
                    kw["seed"] = deep_seed
                    sung_cache[key] = sing_phrase(
                        base, SR, target, offsets, phrase_tonic, **kw
                    )
                sung = sung_cache[key]
            else:
                sung = fade(base, SR, 0.01, 0.04)

            breath_gain = float(style.get("breath", 0.0))
            if breath_gain > 0.0:
                lead = np.concatenate(
                    [breath(SR, 0.20, seed=seed + rep * 17 + idx) * breath_gain,
                     np.zeros(int(0.05 * SR))]
                )
            else:
                lead = np.zeros(int(0.05 * SR))
            onset = int(round(cursor / grid)) * grid
            start = max(0, onset - len(lead))
            seg = np.concatenate([lead, sung])
            lj = float(style.get("level_jitter", 0.06))
            seg = seg * rng.uniform(1.0 - lj, 1.0 + lj)
            timeline.append((start, seg))
            cursor = onset + len(sung)

            every = max(1, int(cr.get("every", 2)))
            if cr_on and global_idx % every == 0:
                rbase = raw_resp[p]
                rtarget = max(
                    beat,
                    round(
                        (target * float(cr.get("dur", 1.0))) / (beat / 2.0)
                    )
                    * (beat / 2.0),
                )
                transpose = float(cr.get("transpose", 0.0))
                if transpose != 0.0:
                    transpose = (
                        -abs(transpose)
                        if resp_voice.startswith("hm")
                        else abs(transpose)
                    )
                r_offsets = offsets
                rtonic = tonic * 2.0 ** (transpose / 12.0)
                rseed = int(seed + 500000 + rep * 10000 + idx * 37)
                if ref_semis is not None:
                    rkey = ("resp-ref", p, round(rtarget, 3), rseed)
                else:
                    rkey = ("resp", p, tuple(r_offsets), round(rtarget, 3), rseed)
                if rkey not in sung_cache:
                    kw = dict(sing_kwargs)
                    kw["seed"] = rseed
                    sung_cache[rkey] = sing_phrase(
                        rbase, SR, rtarget, r_offsets, rtonic, **kw
                    )
                resp = sung_cache[rkey] * float(cr.get("gain", 0.6))
                cursor += int(float(cr.get("gap", 0.12)) * SR)
                ronset = int(round(cursor / grid)) * grid
                timeline.append((ronset, resp))
                cursor = ronset + len(resp)

            pause_j = float(style.get("pause_jitter", 0.175))
            pause = float(style.get("pause", 0.5)) * rng.uniform(
                1.0 - pause_j, 1.0 + pause_j
            )
            if (idx + 1) % 4 == 0:
                pause += 0.35
            if idx == n_phrases - 1:
                pause *= 1.8
            cursor += int(pause * SR)
            phrase_idx += 1

    total = cursor + int(outro * SR)
    n = total
    print(f"      track length = {n / SR:.1f}s")

    bed_tonic = float(tonic)
    while bed_tonic > 220.0:
        bed_tonic /= 2.0
    while bed_tonic < 110.0:
        bed_tonic *= 2.0

    print("[3/6] building the music bed")
    bed = render_bed(style, n / SR, SR, bed_tonic, seed=seed)
    if len(bed) < n:
        bed = np.pad(bed, ((0, n - len(bed)), (0, 0)))
    bed = bed[:n]

    print("[4/6] mixing vocal")
    vt = np.zeros(n)
    for start, seg in timeline:
        mix_at(vt, seg, start, 1.0)

    vcfg = style.get("vocal") or {}
    vs = to_stereo(vt)
    vs = highpass(vs, SR, vcfg.get("lowcut", 90), order=2)
    vs = low_shelf(
        vs,
        SR,
        float(vcfg.get("warmth_hz", 180.0)),
        float(vcfg.get("warmth", 1.5)),
    )
    vs = high_shelf(
        vs,
        SR,
        float(vcfg.get("presence_hz", 6500.0)),
        float(vcfg.get("presence", -1.0)),
    )
    sat = float(vcfg.get("saturation", 0.0))
    if sat > 0.0:
        vs = saturate(vs, drive=float(vcfg.get("saturation_drive", 1.5)), mix=sat)
    vs = deess(vs, SR, vcfg.get("deess", 0.25))
    vs = compressor(vs, SR, thresh_db=vcfg.get("thresh", -19), ratio=vcfg.get("ratio", 2.5))
    intensity = min(1.5, max(0.5, float(vcfg.get("intensity", 1.0))))
    target_rms = -18.0 + 3.0 * (intensity - 1.0)
    vs *= db_to_lin(target_rms) / max(rms(vs), 1e-9)
    if not np.all(np.isfinite(vs)):
        raise RuntimeError("Non-finite vocal samples after processing")
    vs = reverb(
        vs, SR,
        decay=vcfg.get("reverb_decay", 2.0),
        mix=vcfg.get("reverb", 0.22),
        predelay=vcfg.get("predelay", 0.02),
        seed=seed + 21,
    )
    ecfg = vcfg.get("echo") or {}
    if ecfg.get("enabled", False):
        vs = delay(
            vs, SR,
            time=ecfg.get("time", 0.45),
            feedback=ecfg.get("feedback", 0.25),
            mix=ecfg.get("mix", 0.16),
        )
    vs = limiter(vs, SR, ceiling_db=-2.0)

    mcfg = style.get("mix") or {}
    bed *= db_to_lin(-18.0 + mcfg.get("bed_db", -8.0)) / max(rms(bed), 1e-9)
    mix = vs + bed
    mix = mix[:n]

    if args.keep_stems:
        os.makedirs(args.outdir, exist_ok=True)
        tag = args.name or f"{style['name']}_{int(time.time())}"
        sf.write(os.path.join(args.outdir, f"{tag}_voice.wav"), vs, SR)
        sf.write(os.path.join(args.outdir, f"{tag}_bed.wav"), bed, SR)

    print("[5/6] mastering")
    os.makedirs(args.outdir, exist_ok=True)
    tag = args.name or f"{style['name']}_{voice}_{int(time.time())}"
    out_wav = os.path.join(args.outdir, f"{tag}.wav")
    lufs = args.lufs if args.lufs is not None else (style.get("master") or {}).get("lufs", -14)
    paths = finalize(mix, SR, out_wav, lufs=lufs, reference=args.reference)

    print("[6/6] metadata")
    meta = {
        "style": style["name"],
        "text": text,
        "phrases": phrases,
        "voice": voice,
        "backend": backend,
        "speed": speed,
        "repeat": repeat,
        "sing": sing,
        "bpm": bpm,
        "tonic_hz": tonic,
        "melody_audio": args.melody_audio,
        "sustain": float(
            cb_cfg.get("sustain", style.get("sustain", 1.0))
            if backend == "chatterbox"
            else style.get("sustain", 1.0)
        ),
        "ornament": orn,
        "chatterbox": (
            {"language": cb_lang, "exaggeration": cb_exag, "temperature": cb_temp}
            if backend == "chatterbox"
            else None
        ),
        "call_response": ({**cr, "voice": resp_voice} if cr_on else None),
        "seed": seed,
        "duration_sec": round(n / SR, 2),
        "paths": paths,
    }
    meta_path = os.path.join(args.outdir, f"{tag}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(json.dumps(paths, indent=2))
    print(f"metadata: {meta_path}")


if __name__ == "__main__":
    sys.exit(main())
