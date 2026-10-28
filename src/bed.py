import numpy as np

from .fx import lowpass, highpass, bandpass, reverb, stereo_width, vinyl, wobble
from .util import SR, mix_at, fade, to_stereo


def _pluck(freq, dur, sr, bright=0.45, rng=None):
    n = max(2, int(dur * sr))
    t = np.arange(n) / sr
    y = np.zeros(n)
    n_h = int(6 + 14 * bright)
    for k in range(1, n_h + 1):
        amp = (1.0 / k ** 1.15) * np.exp(-t * (0.55 + 0.10 * k) / max(dur, 0.1))
        y += amp * np.sin(2 * np.pi * freq * k * t + 0.03 * k * np.sin(2 * np.pi * 3.1 * t))
    if rng is not None:
        na = max(2, int(0.02 * sr))
        y[:na] += rng.standard_normal(na) * 0.12 * np.exp(-np.arange(na) / (0.004 * sr))
    y *= np.minimum(1.0, t / 0.003) * np.exp(-t / max(dur * 0.85, 0.1))
    return y


def tanpura(dur, sr, tonic, rng, cfg):
    gain = cfg.get("gain", 0.3)
    step = cfg.get("step", 1.6)
    decay = cfg.get("decay", 6.0)
    pattern = cfg.get("pattern", [0, 7, 0, 0])
    n = int(dur * sr)
    out = np.zeros(n + int(decay * sr))
    t = 0.0
    i = 0
    while t < dur:
        f = tonic * 2 ** (pattern[i % len(pattern)] / 12.0)
        note = _pluck(f, decay, sr, bright=0.5, rng=rng)
        mix_at(out, note, int(t * sr), gain * (0.9 + 0.1 * rng.random()))
        t += step
        i += 1
    tt = np.arange(n) / sr
    out[:n] += 0.045 * np.sin(2 * np.pi * tonic / 2 * tt)
    out[:n] += 0.025 * np.sin(2 * np.pi * tonic * 1.5 * tt)
    return out[:n]


def _chord_tone(freq, dur, sr, harmonics=6, vibrato=4.8, drift=0.3):
    n = max(2, int(dur * sr))
    t = np.arange(n) / sr
    y = np.zeros(n)
    for k in range(1, harmonics + 1):
        amp = 0.55 ** k
        for cents in (-4.0, 3.0):
            fd = freq * 2 ** (cents / 1200.0)
            ph = 2 * np.pi * fd * k * t + drift * np.sin(2 * np.pi * vibrato * t + k)
            y += amp * np.sin(ph)
    y *= np.minimum(1.0, t / 0.6) * np.minimum(1.0, (dur - t) / 0.6)
    return y


def room_tone(dur, sr, rng, cfg):
    n = max(2, int(dur * sr))
    noise = rng.standard_normal(n)
    noise = highpass(noise, sr, cfg.get("highpass", 80), order=2)
    noise = lowpass(noise, sr, cfg.get("lowpass", 1800), order=2)
    t = np.arange(n) / sr
    mod = 1.0 + cfg.get("mod", 0.35) * np.sin(
        2 * np.pi * cfg.get("rate", 0.06) * t + rng.random() * 6.28
    )
    return noise * mod * cfg.get("gain", 0.012)


def harmonium_bar(freqs, dur, sr, gain=0.08):
    y = np.zeros(max(2, int(dur * sr)))
    for f in freqs:
        y += _chord_tone(f, dur, sr, harmonics=6, vibrato=5.0)
    return y * gain / max(1, len(freqs))


def rhodes_bar(freqs, dur, sr, gain=0.10, rng=None):
    n = max(2, int(dur * sr))
    t = np.arange(n) / sr
    y = np.zeros(n)
    for f in freqs:
        mod = 0.9 * np.exp(-t / 0.5)
        y += np.sin(2 * np.pi * f * t + mod * np.sin(2 * np.pi * f * 2 * t))
        y += 0.25 * np.sin(2 * np.pi * f * 2.002 * t) * np.exp(-t / 1.2)
    trem = 1.0 + 0.12 * np.sin(2 * np.pi * 4.2 * t + 0.4)
    env = np.minimum(1.0, t / 0.02) * np.exp(-t / 2.4) * trem
    return y * env * gain / max(1, len(freqs))


def tabla_hit(kind, sr, rng):
    if kind == "dha":
        n = int(0.55 * sr)
        t = np.arange(n) / sr
        f = 88 * np.exp(-t * 4.0) + 52
        y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.30)
        y += 0.25 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.10)
        y += 0.5 * lowpass(rng.standard_normal(n), sr, 2500) * np.exp(-t / 0.012)
        return y
    if kind == "tin":
        n = int(0.32 * sr)
        t = np.arange(n) / sr
        y = np.sin(2 * np.pi * 310 * t) * np.exp(-t / 0.12)
        y += 0.45 * np.sin(2 * np.pi * 468 * t) * np.exp(-t / 0.075)
        y += 0.3 * lowpass(rng.standard_normal(n), sr, 5000) * np.exp(-t / 0.008)
        return y
    if kind == "na":
        n = int(0.22 * sr)
        t = np.arange(n) / sr
        y = np.sin(2 * np.pi * 520 * t) * np.exp(-t / 0.06)
        y += 0.3 * bandpass(rng.standard_normal(n), sr, 1500, 6000) * np.exp(-t / 0.012)
        return y
    n = int(0.4 * sr)
    t = np.arange(n) / sr
    f = 70 * np.exp(-t * 5.0) + 45
    return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.22)


def manjira(sr, rng):
    n = int(0.30 * sr)
    t = np.arange(n) / sr
    y = np.zeros(n)
    for f, d in [(2100, 0.12), (3170, 0.09), (4430, 0.07), (5900, 0.05)]:
        y += np.sin(2 * np.pi * f * t + rng.random() * 6.28) * np.exp(-t / d)
    y += 0.35 * highpass(rng.standard_normal(n), sr, 5000) * np.exp(-t / 0.006)
    return y * 0.35


def bell(freq, sr, gain=0.2):
    dur = 4.0
    n = int(dur * sr)
    t = np.arange(n) / sr
    y = np.zeros(n)
    for mult, amp, d in [(1.0, 1.0, 3.2), (2.76, 0.55, 2.2), (5.4, 0.3, 1.2), (8.93, 0.18, 0.7)]:
        y += amp * np.sin(2 * np.pi * freq * mult * t) * np.exp(-t / d)
    y *= np.minimum(1.0, t / 0.004)
    return y * gain


def kick(sr, rng=None):
    n = int(0.35 * sr)
    t = np.arange(n) / sr
    f = 120 * np.exp(-t * 35) + 42
    y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.20)
    if rng is not None:
        y[: int(0.006 * sr)] += rng.standard_normal(int(0.006 * sr)) * 0.25
    return y


def snare(sr, rng):
    n = int(0.20 * sr)
    t = np.arange(n) / sr
    y = 0.5 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.08)
    y += 0.6 * bandpass(rng.standard_normal(n), sr, 1200, 6000) * np.exp(-t / 0.05)
    return y


def hat(sr, rng, open_=False):
    n = int((0.18 if open_ else 0.05) * sr)
    t = np.arange(n) / sr
    y = highpass(rng.standard_normal(n), sr, 7000)
    return y * np.exp(-t / (0.06 if open_ else 0.012)) * 0.5


def shaker(sr, rng):
    n = int(0.09 * sr)
    t = np.arange(n) / sr
    y = bandpass(rng.standard_normal(n), sr, 3000, 9000)
    return y * np.exp(-t / 0.025) * 0.4


def _render_drums(style, dur, sr, rng, n):
    out = np.zeros(n)
    beat = 60.0 / style["bpm"]
    bar = 4 * beat
    cfg = style["drums"]
    kind = cfg.get("kind", "tabla")
    bars = int(np.ceil(dur / bar)) + 1
    if kind == "tabla":
        pattern = cfg.get("pattern", [[0.0, "dha", 0.9], [1.0, "tin", 0.6]])
        for b in range(bars):
            for off, hit_kind, g in pattern:
                hit = tabla_hit(hit_kind, sr, rng)
                mix_at(out, hit, int((b * bar + off * beat) * sr), g)
            if cfg.get("manjira", True):
                for off in (0.0, 2.0):
                    mix_at(out, manjira(sr, rng), int((b * bar + off * beat) * sr), 0.35)
    else:
        swing = cfg.get("swing", 0.12)
        for b in range(bars):
            base = b * bar
            for off in cfg.get("kick", [0.0, 2.5]):
                mix_at(out, kick(sr, rng), int((base + off * beat) * sr), 0.95)
            for off in cfg.get("snare", [1.0, 3.0]):
                mix_at(out, snare(sr, rng), int((base + off * beat) * sr), 0.45)
            for i in range(8):
                off = i * 0.5 + (swing * beat if i % 2 else 0.0)
                mix_at(out, hat(sr, rng), int((base + off * beat) * sr), 0.25 if i % 2 else 0.15)
            for i in range(16):
                off = i * 0.25
                mix_at(out, shaker(sr, rng), int((base + off * beat) * sr), 0.10)
    return out


def render_bed(style, dur, sr, tonic, seed=0):
    rng = np.random.default_rng(seed)
    n = int(dur * sr)
    beat = 60.0 / style["bpm"]
    bar = 4 * beat
    bed = np.zeros(n)

    drone = style.get("drone") or {}
    if drone.get("enabled", False):
        bed += tanpura(dur, sr, tonic, rng, drone)

    pad = style.get("pad") or {}
    if pad.get("enabled", False):
        chord = pad.get("chord", [0, 7])
        octave = pad.get("octave", 1)
        is_rhodes = pad.get("kind") == "rhodes"
        progression = pad.get("progression") or [0]
        bars = int(np.ceil(dur / bar)) + 1
        for b in range(bars):
            root = progression[b % len(progression)]
            freqs = [tonic * octave * 2 ** ((root + s) / 12.0) for s in chord]
            if is_rhodes:
                seg = rhodes_bar(freqs, bar + 0.3, sr, pad.get("gain", 0.08), rng)
            else:
                seg = harmonium_bar(freqs, bar + 0.3, sr, pad.get("gain", 0.08))
            mix_at(bed, seg, int(b * bar * sr), 1.0)

    room = style.get("room") or {}
    if room.get("enabled", False):
        bed += room_tone(dur, sr, rng, room)

    if style.get("drums"):
        bed += _render_drums(style, dur, sr, rng, n)

    bcfg = style.get("bell") or {}
    if bcfg.get("enabled", False):
        freq = tonic * bcfg.get("ratio", 2.0)
        mix_at(bed, bell(freq, sr, bcfg.get("gain", 0.2)), 0, 1.0)
        every = bcfg.get("every")
        if every:
            t = every
            while t < dur - 1.0:
                mix_at(bed, bell(freq, sr, bcfg.get("gain", 0.2) * 0.6), int(t * sr), 1.0)
                t += every

    texture = style.get("texture") or {}
    bed = lowpass(bed, sr, texture.get("lowpass", 15000), order=2)
    bed = highpass(bed, sr, texture.get("highpass", 35), order=2)
    st = to_stereo(np.stack([bed, np.roll(bed, 37)], axis=1))

    rv = style.get("reverb") or {}
    st = reverb(
        st,
        sr,
        decay=rv.get("decay", 2.2),
        mix=rv.get("mix", 0.22),
        predelay=rv.get("predelay", 0.02),
        damp=rv.get("damp", 6000),
        seed=seed + 5,
    )

    if texture.get("vinyl", 0.0) > 0:
        st += vinyl(sr, len(st), gain=texture["vinyl"], seed=seed + 9)
    if texture.get("wobble", 0.0) > 0:
        st = wobble(st, sr, depth=texture["wobble"], rate=texture.get("wobble_rate", 0.32))

    st = stereo_width(st, texture.get("width", 1.0))
    st = fade(st, sr, 0.05, 0.8)
    return st
