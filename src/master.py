import os
import subprocess

import numpy as np
from scipy.ndimage import maximum_filter1d, uniform_filter1d

from .util import SR, db_to_lin, normalize


def limiter(x, sr=SR, ceiling_db=-1.0, hold=0.01, smooth_ms=0.03):
    ceiling = db_to_lin(ceiling_db)
    peak = np.max(np.abs(x), axis=1)
    env = maximum_filter1d(peak, size=max(1, int(hold * sr)))
    env = uniform_filter1d(env, max(1, int(smooth_ms * sr)))
    gain = np.minimum(1.0, ceiling / np.maximum(env, 1e-9))
    return x * gain[:, None]


def loudnorm(in_path, out_path, lufs=-14.0, tp=-1.0, sr=44100):
    cmd = [
        "ffmpeg", "-y", "-i", in_path,
        "-af", f"loudnorm=I={lufs}:TP={tp}:LRA=11",
        "-ar", str(sr), "-c:a", "pcm_s16le", out_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-2000:])
    return out_path


def match(target_path, reference_path, out_path):
    import matchering as mg

    mg.process(
        target=target_path,
        reference=reference_path,
        results=[mg.pcm16(out_path)],
    )
    return out_path


def to_mp3(wav_path, mp3_path, bitrate="192k"):
    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-codec:a", "libmp3lame", "-b:a", bitrate, mp3_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr[-2000:])
    return mp3_path


def finalize(x, sr, out_wav, lufs=-14.0, reference=None, ceiling_db=-1.0):
    x = normalize(x, db_to_lin(ceiling_db - 0.5))
    x = limiter(x, sr, ceiling_db=ceiling_db)
    x = np.clip(x, -1.0, 1.0)

    import soundfile as sf

    premaster = os.path.splitext(out_wav)[0] + "_premaster.wav"
    sf.write(premaster, x, sr, subtype="PCM_24")
    loudnorm(premaster, out_wav, lufs=lufs)

    paths = {"wav": out_wav, "premaster": premaster}
    paths["mp3"] = to_mp3(out_wav, os.path.splitext(out_wav)[0] + ".mp3")

    if reference:
        matched = os.path.splitext(out_wav)[0] + "_matched.wav"
        match(out_wav, reference, matched)
        paths["matched_wav"] = matched
        paths["matched_mp3"] = to_mp3(matched, os.path.splitext(matched)[0] + ".mp3")

    return paths
