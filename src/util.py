import numpy as np

SR = 24000


def db_to_lin(db):
    return 10.0 ** (db / 20.0)


def lin_to_db(x):
    return 20.0 * np.log10(np.maximum(np.asarray(x, dtype=np.float64), 1e-12))


def rms(x):
    x = np.asarray(x, dtype=np.float64)
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def normalize(x, peak=0.95):
    x = np.asarray(x, dtype=np.float64)
    m = np.max(np.abs(x)) + 1e-12
    return x * (peak / m)


def fade(x, sr, fin=0.01, fout=0.05):
    x = np.array(x, dtype=np.float64, copy=True)
    ni = min(len(x), int(fin * sr))
    no = min(len(x), int(fout * sr))
    if ni > 0:
        curve = np.linspace(0.0, 1.0, ni) ** 0.5
        x[:ni] *= curve[:, None] if x.ndim == 2 else curve
    if no > 0:
        curve = np.linspace(1.0, 0.0, no) ** 0.5
        x[-no:] *= curve[:, None] if x.ndim == 2 else curve
    return x


def to_stereo(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    return x


def to_mono(x):
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 2:
        return x.mean(axis=1)
    return x


def mix_at(dst, src, start, gain=1.0):
    if start < 0:
        src = src[-start:]
        start = 0
    end = min(len(dst), start + len(src))
    if end <= start:
        return
    dst[start:end] += src[: end - start] * gain


def smooth(x, n):
    n = max(1, int(n))
    if n == 1:
        return x
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def seconds_to_samples(sec, sr=SR):
    return int(round(sec * sr))


def make_silence(sec, sr=SR):
    return np.zeros(max(1, int(round(sec * sr))), dtype=np.float64)
