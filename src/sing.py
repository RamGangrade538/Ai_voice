import numpy as np
import pyworld as pw
from scipy.signal import find_peaks

from .melody import contour_to_frames
from .util import smooth, fade


def _sample(M, idx):
    m = len(M)
    i0 = np.clip(np.floor(idx).astype(np.int64), 0, m - 1)
    i1 = np.clip(i0 + 1, 0, m - 1)
    f = idx - i0
    if M.ndim == 1:
        return M[i0] * (1.0 - f) + M[i1] * f
    return M[i0] * (1.0 - f)[:, None] + M[i1] * f[:, None]


def _stretch(M, n):
    m = len(M)
    if m == n:
        return np.array(M, copy=True)
    return _sample(M, np.linspace(0, m - 1, n))


def _warp_index(f0, n, sustain):
    m = len(f0)
    if sustain <= 1.0001 or m < 2:
        return np.linspace(0, m - 1, n)
    w = np.where(f0 > 0, sustain, 1.0 / sustain)
    cum = np.cumsum(w)
    cum -= cum[0]
    if cum[-1] <= 1e-9:
        return np.linspace(0, m - 1, n)
    cum /= cum[-1]
    return np.interp(np.linspace(0.0, 1.0, n), cum, np.arange(m))


def _syllable_bounds(y, n, sr, frame_period):
    hop = max(1, int(frame_period / 1000.0 * sr))
    win = max(2, int(0.03 * sr))
    frames = list(range(0, max(1, len(y) - win), hop))
    if len(frames) < 4:
        return None
    env = np.array([np.sqrt(np.mean(y[i : i + win] ** 2)) for i in frames])
    env = smooth(env, 3)
    env = _stretch(env, n)
    peak = float(np.max(env)) + 1e-9
    env = env / peak
    peaks, _ = find_peaks(
        env,
        distance=max(1, int(0.11 * 1000.0 / frame_period)),
        prominence=0.10,
        height=0.12,
    )
    if len(peaks) < 2:
        return None
    cuts = [0]
    for a, b in zip(peaks[:-1], peaks[1:]):
        cuts.append(int((a + b) / 2))
    cuts.append(n)
    return cuts


def _note_curve(notes, n, bounds=None):
    if bounds and len(bounds) >= 3:
        cuts = bounds
        k = len(cuts) - 1
    else:
        k = len(notes)
        cuts = [int(round(i * n / k)) for i in range(k + 1)]
    curve = np.zeros(n)
    for j in range(k):
        a, b = cuts[j], cuts[j + 1]
        curve[a:b] = notes[j % len(notes)]
    return curve


def _add_kan(curve, bounds, semitones):
    if semitones <= 0 or not bounds or len(bounds) < 3:
        return curve
    out = np.array(curve, copy=True)
    for b in bounds[1:-1]:
        i0 = max(0, b - 2)
        i1 = min(len(out), b + 1)
        if i1 > i0:
            out[i0:i1] += semitones * np.linspace(1.0, 0.0, i1 - i0)
    return out


def _add_taan(curve, n, frame_period, semitones, rate=9.0, start=0.80):
    if semitones <= 0 or n < 4:
        return curve
    dur = n * frame_period / 1000.0
    t = np.arange(n) * frame_period / 1000.0
    ramp = np.clip((t - start * dur) / max(1e-3, (1.0 - start) * dur), 0.0, 1.0)
    mod = 2.0 ** ((semitones / 12.0) * np.sin(2 * np.pi * rate * t) * ramp)
    return curve * mod


def estimate_tonic(y, sr, base_tonic=130.81):
    f0, _ = pw.harvest(
        np.ascontiguousarray(y, dtype=np.float64), sr, 60.0, 420.0, 5.0
    )
    voiced = f0[f0 > 0]
    if not len(voiced):
        return base_tonic
    median = float(np.median(voiced))
    octave = int(round(np.log2(max(median, 1e-6) / base_tonic)))
    tonic = base_tonic * (2.0 ** octave)
    while tonic < 90.0:
        tonic *= 2.0
    while tonic > 280.0:
        tonic /= 2.0
    return tonic


def sing_phrase(
    y,
    sr,
    target_dur,
    offsets,
    tonic,
    frame_period=5.0,
    vibrato=0.22,
    vibrato_rate=4.8,
    vibrato_onset=0.35,
    scoop=0.5,
    glide_ms=55.0,
    kan=0.0,
    taan=0.0,
    sustain=1.0,
    ref_semis=None,
    drift_cents=0.0,
    drift_rate=0.13,
    vibrato_irregular=0.20,
    seed=0,
):
    y = np.ascontiguousarray(y, dtype=np.float64)
    f0, t = pw.harvest(y, sr, 60.0, 420.0, frame_period)
    sp = pw.cheaptrick(y, f0, t, sr)
    ap = pw.d4c(y, f0, t, sr)

    m = len(f0)
    n = max(8, int(round(target_dur * 1000.0 / frame_period)))
    bounds = None
    if sustain > 1.0001 and m >= 2:
        src = _warp_index(f0, n, sustain)
        src_i = np.clip(np.round(src).astype(np.int64), 0, m - 1)
        f0r = f0[src_i]
        spr = _sample(sp, src)
        apr = _sample(ap, src)
        if ref_semis is None:
            sb = _syllable_bounds(y, m, sr, frame_period)
            if sb and len(sb) >= 3:
                mapped = [0]
                mapped.extend(int(np.searchsorted(src, b)) for b in sb[1:-1])
                mapped.append(n)
                bounds = [mapped[0]]
                for x in mapped[1:]:
                    x = int(np.clip(x, 0, n))
                    if x > bounds[-1]:
                        bounds.append(x)
                if len(bounds) < 3:
                    bounds = None
    else:
        f0r = _stretch(f0, n)
        spr = _stretch(sp, n)
        apr = _stretch(ap, n)
        if ref_semis is None:
            bounds = _syllable_bounds(y, n, sr, frame_period)
    voiced = f0r > 0

    if ref_semis is not None and len(ref_semis) > 1:
        semis = contour_to_frames(ref_semis, n)
        curve = tonic * 2.0 ** (semis / 12.0)
    else:
        notes = [tonic * 2.0 ** (o / 12.0) for o in offsets]
        curve = _note_curve(notes, n, bounds)
        curve = _add_kan(curve, bounds, kan)
        curve = smooth(curve, max(1, int(glide_ms / frame_period)))

        k = max(2, int(80.0 / frame_period))
        ramp = np.linspace(0.0, 1.0, min(k, n))
        curve[: len(ramp)] *= 2.0 ** (-scoop / 12.0 * (1.0 - ramp))

    curve = _add_taan(curve, n, frame_period, taan)
    curve = np.clip(curve, 60.0, 800.0)

    tt = np.arange(n) * frame_period / 1000.0
    rng = np.random.default_rng(int(seed))
    phase_a, phase_b = rng.uniform(0.0, 2.0 * np.pi, 2)
    if drift_cents > 0.0:
        drift = (drift_cents / 12.0) * (
            0.65 * np.sin(2.0 * np.pi * drift_rate * tt + phase_a)
            + 0.35 * np.sin(2.0 * np.pi * drift_rate * 2.37 * tt + phase_b)
        )
        curve *= 2.0 ** drift

    wobble = vibrato_irregular * (
        0.7 * np.sin(2.0 * np.pi * 0.17 * tt + phase_b)
        + 0.3 * np.sin(2.0 * np.pi * 0.43 * tt + phase_a)
    )
    vib = 2.0 ** (
        (vibrato / 12.0)
        * np.sin(2.0 * np.pi * vibrato_rate * tt + wobble)
        * np.minimum(1.0, tt / max(0.05, vibrato_onset))
    )
    f0n = np.where(voiced, curve * vib, 0.0)

    out = pw.synthesize(f0n, spr, apr, sr, frame_period)
    return fade(out, sr, 0.01, 0.03)
