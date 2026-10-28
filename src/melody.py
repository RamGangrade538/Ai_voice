import numpy as np
import pyworld as pw
import soundfile as sf
from scipy.signal import resample_poly, medfilt

from .util import SR, smooth


def load_mono(path, sr=SR):
    y, fs = sf.read(path, always_2d=False)
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 2:
        y = y.mean(axis=1)
    if fs != sr:
        from math import gcd

        g = gcd(int(fs), int(sr))
        y = resample_poly(y, sr // g, fs // g)
    return y


def extract_contour(path, sr=SR, frame_period=5.0, snap=0):
    y = load_mono(path, sr)
    f0, _ = pw.harvest(y, sr, 70.0, 500.0, frame_period)
    voiced = f0 > 0
    if voiced.sum() < 10:
        raise ValueError(f"No pitched melody found in {path}")
    x = np.arange(len(f0))
    f0i = np.interp(x, x[voiced], f0[voiced])
    f0i = medfilt(f0i, kernel_size=9)
    f0i = smooth(f0i, 3)
    f0i[~voiced] = 0.0
    idx = np.where(voiced)[0]
    lo, hi = int(idx[0]), int(idx[-1]) + 1
    if hi - lo > 6:
        lo += 2
        hi -= 2
    f0 = f0i[lo:hi]
    voiced_f0 = f0[f0 > 0]
    tail = voiced_f0[-max(3, int(0.08 * len(voiced_f0))) :]
    tonic = float(np.median(tail))
    semis = 12.0 * np.log2(np.maximum(f0, 1e-9) / tonic)
    semis[f0 <= 0] = np.nan
    if snap:
        valid = ~np.isnan(semis)
        semis[valid] = np.round(semis[valid] * snap) / snap
    return semis, tonic, len(y) / sr


def contour_to_frames(semis, n):
    x = np.arange(len(semis))
    valid = ~np.isnan(semis)
    if valid.sum() < 2:
        return np.zeros(n)
    filled = np.interp(x, x[valid], semis[valid])
    filled = smooth(filled, 3)
    return np.interp(np.linspace(0, len(filled) - 1, n), x, filled)


def estimate_tempo(path, sr=SR, bpm_min=50.0, bpm_max=180.0):
    from scipy.signal import stft

    y = load_mono(path, sr)
    if len(y) < sr:
        return 72.0
    _, _, z = stft(y, fs=sr, nperseg=1024, noverlap=768, boundary=None)
    mag = np.abs(z)
    flux = np.sum(np.maximum(0.0, np.diff(mag, axis=1)), axis=0)
    if len(flux) < 16:
        return 72.0
    env = flux - flux.mean()
    env /= np.std(env) + 1e-9
    ac = np.correlate(env, env, mode="full")[len(env) - 1 :]
    ac /= ac[0] + 1e-9
    lags = np.arange(len(ac), dtype=np.float64)
    hop = 1024 - 768
    bpm = 60.0 * sr / np.maximum(lags * hop, 1e-9)
    mask = (bpm >= bpm_min) & (bpm <= bpm_max)
    if not mask.any():
        return 72.0
    idx = int(np.argmax(np.where(mask, ac, -1.0)))
    return float(np.clip(bpm[idx], bpm_min, bpm_max))
