import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.ndimage import uniform_filter1d

from .util import SR, db_to_lin, lin_to_db, rms, to_stereo, to_mono


def lowpass(x, sr, fc, order=2, axis=0):
    fc = min(max(fc, 20.0), sr * 0.49)
    sos = butter(order, fc, btype="low", fs=sr, output="sos")
    return sosfilt(sos, x, axis=axis)


def highpass(x, sr, fc, order=2, axis=0):
    fc = min(max(fc, 10.0), sr * 0.49)
    sos = butter(order, fc, btype="high", fs=sr, output="sos")
    return sosfilt(sos, x, axis=axis)


def bandpass(x, sr, lo, hi, order=2, axis=0):
    sos = butter(order, [lo, hi], btype="band", fs=sr, output="sos")
    return sosfilt(sos, x, axis=axis)


def make_ir(sr, decay=2.0, predelay=0.02, damp=6000, seed=7):
    n = max(1, int(decay * sr))
    t = np.arange(n) / sr
    rng = np.random.default_rng(seed)
    ir = rng.standard_normal((n, 2)) * np.exp(-6.9 * t / max(decay, 0.05))[:, None]
    ir = lowpass(ir, sr, damp, order=2)
    pre = int(predelay * sr)
    if pre > 0:
        ir[:pre] = 0.0
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True)) + 1e-12
    return ir


def reverb(x, sr, decay=2.0, mix=0.2, predelay=0.02, damp=6000, seed=7):
    x = to_stereo(x)
    ir = make_ir(sr, decay, predelay, damp, seed)
    wet = np.stack(
        [fftconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], axis=1
    )
    r = rms(x)
    wr = rms(wet)
    if wr > 1e-9:
        wet *= r / wr
    return (1.0 - mix) * x + mix * wet


def delay(x, sr, time=0.4, feedback=0.3, mix=0.25, pingpong=True):
    x = to_stereo(x)
    n = len(x)
    out = x.copy()
    d = int(time * sr)
    tap = x.copy()
    gain = 1.0
    for i in range(1, 5):
        gain *= feedback
        if d * i >= n:
            break
        shifted = np.zeros_like(x)
        shifted[d * i :] = tap[: n - d * i] * gain
        if pingpong:
            shifted = shifted[:, ::-1]
        out += shifted
    return (1.0 - mix) * x + mix * out


def compressor(x, sr, thresh_db=-18.0, ratio=3.0, release=0.18, makeup_db=0.0):
    x = to_stereo(x)
    mono = np.mean(np.abs(x), axis=1)
    win = max(1, int(0.02 * sr))
    env = uniform_filter1d(mono, win)
    gain = np.ones_like(env)
    over = lin_to_db(env) - thresh_db
    mask = over > 0
    gain[mask] = db_to_lin(-over[mask] * (1.0 - 1.0 / ratio))
    gain = uniform_filter1d(gain, max(1, int(release * sr)))
    return x * (gain * db_to_lin(makeup_db))[:, None]


def soft_clip(x, drive=1.0):
    return np.tanh(np.asarray(x) * drive) / np.tanh(drive)


def stereo_width(x, width=1.0):
    x = to_stereo(x)
    m = x.mean(axis=1, keepdims=True)
    s = x - m
    return m + s * width


def wobble(x, sr, depth=0.0025, rate=0.32):
    x = to_stereo(x)
    n = len(x)
    t = np.arange(n) / sr
    mod = depth * np.sin(2 * np.pi * rate * t + 0.8 * np.sin(2 * np.pi * 0.09 * t))
    src = np.arange(n) + mod * sr
    src = np.clip(src, 0, n - 1)
    return np.stack(
        [np.interp(src, np.arange(n), x[:, c]) for c in range(2)], axis=1
    )


def vinyl(sr, n, gain=0.05, seed=11):
    rng = np.random.default_rng(seed)
    hiss = lowpass(rng.standard_normal(n), sr, 6500) * 0.12
    crack = np.zeros(n)
    count = max(1, int(n / sr * 14))
    idx = rng.integers(0, n, count)
    crack[idx] = rng.uniform(0.3, 1.0, count)
    k = np.exp(-np.arange(max(2, int(0.0025 * sr))) / (0.0006 * sr))
    crack = fftconvolve(crack, k)[:n]
    left = (hiss * 0.4 + crack) * gain
    hiss2 = lowpass(rng.standard_normal(n), sr, 6000) * 0.12
    idx2 = rng.integers(0, n, count)
    crack2 = np.zeros(n)
    crack2[idx2] = rng.uniform(0.3, 1.0, count)
    crack2 = fftconvolve(crack2, k)[:n]
    right = (hiss2 * 0.4 + crack2) * gain
    return np.stack([left, right], axis=1)


def breath(sr, dur=0.22, seed=3, lo=700, hi=5200):
    n = max(2, int(dur * sr))
    rng = np.random.default_rng(seed)
    y = rng.standard_normal(n)
    y = bandpass(y, sr, lo, hi, order=2)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return y * env


def deess(x, sr, amount=0.35):
    x = to_stereo(x)
    hi = bandpass(x, sr, 5000, min(11000, sr * 0.45), order=2)
    env = uniform_filter1d(np.mean(np.abs(hi), axis=1), max(1, int(0.01 * sr)))
    thresh = np.percentile(env, 92) + 1e-9
    gain = np.ones_like(env)
    mask = env > thresh
    gain[mask] = 1.0 - amount * np.clip((env[mask] - thresh) / (thresh + 1e-9), 0, 1)
    return x - hi * (1.0 - gain)[:, None]


def _shelf(x, sr, fc, gain_db, high=False, q=0.707):
    """RBJ low/high shelf. gain_db may be negative."""
    x = np.asarray(x, dtype=np.float64)
    if abs(gain_db) < 1e-6:
        return x
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * min(max(fc, 20.0), sr * 0.49) / sr
    cw = np.cos(w0)
    sw = np.sin(w0)
    alpha = sw / (2.0 * q)
    rooted = 2.0 * np.sqrt(A) * alpha
    if high:
        b0 = A * ((A + 1.0) + (A - 1.0) * cw + rooted)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cw)
        b2 = A * ((A + 1.0) + (A - 1.0) * cw - rooted)
        a0 = (A + 1.0) - (A - 1.0) * cw + rooted
        a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cw)
        a2 = (A + 1.0) - (A - 1.0) * cw - rooted
    else:
        b0 = A * ((A + 1.0) - (A - 1.0) * cw + rooted)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cw)
        b2 = A * ((A + 1.0) - (A - 1.0) * cw - rooted)
        a0 = (A + 1.0) + (A - 1.0) * cw + rooted
        a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cw)
        a2 = (A + 1.0) + (A - 1.0) * cw - rooted
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sosfilt(sos, x, axis=0)


def low_shelf(x, sr, fc=180.0, gain_db=1.5, q=0.707):
    return _shelf(x, sr, fc, gain_db, high=False, q=q)


def high_shelf(x, sr, fc=6500.0, gain_db=-1.0, q=0.707):
    return _shelf(x, sr, fc, gain_db, high=True, q=q)


def saturate(x, drive=1.5, mix=0.15):
    x = np.asarray(x, dtype=np.float64)
    if mix <= 0:
        return x
    y = np.tanh(x * max(float(drive), 1e-6)) / np.tanh(max(float(drive), 1e-6))
    return (1.0 - mix) * x + mix * y
