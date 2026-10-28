import random
import re

import numpy as np

_PIPELINES = {}
_CACHE = {}

VOICES = {
    "hf_alpha": "Hindi female, warm",
    "hf_beta": "Hindi female, bright",
    "hm_omega": "Hindi male, deep",
    "hm_psi": "Hindi male, soft",
}


def _lang_code(voice):
    return voice[0]


def get_pipeline(voice):
    from kokoro import KPipeline

    code = _lang_code(voice)
    if code not in _PIPELINES:
        _PIPELINES[code] = KPipeline(lang_code=code, repo_id="hexgrad/Kokoro-82M")
    return _PIPELINES[code]


def split_script(text):
    lines = text.replace("\r", "\n").split("\n")
    events = []
    pending = 0
    for line in lines:
        line = line.strip()
        if not line or not re.search(r"\w", line, flags=re.UNICODE):
            if events:
                pending += 1
            continue
        parts = re.split(r"[।\|;]+", line)
        for part in parts:
            part = part.strip(" \t,،….")
            if not part:
                continue
            if pending:
                events.append(("pause", pending))
                pending = 0
            if len(part) > 28 and "," in part:
                subs = [p.strip() for p in part.split(",") if p.strip()]
            else:
                subs = [part]
            for sub in subs:
                events.append(("phrase", sub))
    return events or [("phrase", text.strip())]


def split_phrases(text):
    return [v for k, v in split_script(text) if k == "phrase"] or [text.strip()]


def syllables(text):
    clean = re.sub(r"[^\u0900-\u097F]", "", text)
    if not clean:
        clean = re.sub(r"\s+", "", text)
    return max(1, int(round(len(clean) * 0.5)))


def _join_chunks(chunks, sr=24000, fade_ms=8.0):
    if not chunks:
        return np.zeros(1)
    if len(chunks) == 1:
        return chunks[0]
    out = np.array(chunks[0], dtype=np.float64, copy=True)
    n = max(2, int(fade_ms / 1000.0 * sr))
    for chunk in chunks[1:]:
        chunk = np.asarray(chunk, dtype=np.float64)
        m = min(len(out), len(chunk), n)
        if m > 1:
            t = np.linspace(0.0, 1.0, m)
            out[-m:] = out[-m:] * np.sqrt(1.0 - t) + chunk[:m] * np.sqrt(t)
            out = np.concatenate([out, chunk[m:]])
        else:
            out = np.concatenate([out, chunk])
    return out


def synth_phrase(text, voice="hm_psi", speed=0.85):
    key = (text, voice, round(speed, 3))
    if key in _CACHE:
        return _CACHE[key].copy()
    if not re.search(r"[\u0900-\u097F]", text):
        raise ValueError(
            "Kokoro Hindi needs Devanagari. Transliterate Roman Hindi/Sanskrit first, "
            f"got: {text[:40]!r}"
        )
    pipeline = get_pipeline(voice)
    import torch

    torch.manual_seed(1234)
    random.seed(1234)
    np.random.seed(1234)
    chunks = []
    for _, _, audio in pipeline(text, voice=voice, speed=speed):
        chunks.append(np.asarray(audio, dtype=np.float64))
    y = _join_chunks(chunks) if chunks else np.zeros(1)
    _CACHE[key] = y
    return y.copy()
