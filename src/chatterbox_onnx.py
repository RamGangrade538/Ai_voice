"""Optional Chatterbox Multilingual TTS backend (ONNX, CPU friendly).

This is deliberately optional: Kokoro remains the default.  Keep the model
files in their own directory and point CHATTERBOX_MODEL_DIR at it.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
from scipy.signal import resample_poly
from transformers import AutoTokenizer

from .util import fade

SR = 24000
START_SPEECH_TOKEN = 6561
STOP_SPEECH_TOKEN = 6562
SUPPORTED = {
    "ar", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "it",
    "ja", "ko", "ms", "nl", "no", "pl", "pt", "ru", "sv", "sw", "tr", "zh",
}


class RepetitionPenalty:
    def __init__(self, penalty: float = 1.2):
        self.penalty = float(penalty)

    def __call__(self, ids: np.ndarray, scores: np.ndarray) -> np.ndarray:
        score = np.take_along_axis(scores, ids, axis=1)
        score = np.where(score < 0, score * self.penalty, score / self.penalty)
        out = scores.copy()
        np.put_along_axis(out, ids, score, axis=1)
        return out


def _read_mono(path: os.PathLike | str, sr: int = SR) -> np.ndarray:
    y, got = sf.read(str(path), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if got != sr:
        g = np.gcd(int(got), int(sr))
        y = resample_poly(y, sr // g, got // g).astype(np.float32)
    peak = float(np.max(np.abs(y))) + 1e-12
    if peak > 0.95:
        y = y * (0.95 / peak)
    return np.ascontiguousarray(y)


def _punctuate(text: str) -> str:
    text = " ".join(text.split())
    if text and text[-1] not in ".!?।॥":
        text += "।"
    return text


class ChatterboxONNX:
    def __init__(self, model_dir, voice_path=None, threads=4):
        self.dir = Path(model_dir)
        self.sr = SR
        onnx_dir = self.dir / "onnx"
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(threads)
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        def sess(name):
            path = onnx_dir / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing Chatterbox ONNX file: {path}")
            return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])

        self.speech_encoder = sess("speech_encoder.onnx")
        self.embed_tokens = sess("embed_tokens.onnx")
        self.language_model = sess("language_model.onnx")
        self.conditional_decoder = sess("conditional_decoder.onnx")
        self.tokenizer = AutoTokenizer.from_pretrained(str(self.dir))
        self.voice_path = Path(voice_path) if voice_path else self.dir / "default_voice.wav"
        if not self.voice_path.is_file():
            raise FileNotFoundError(f"Chatterbox reference voice not found: {self.voice_path}")
        self.reference = _read_mono(self.voice_path)

    def synth(
        self,
        text: str,
        language_id: str = "hi",
        exaggeration: float = 0.35,
        max_new_tokens: int = 1000,
        temperature: float = 0.8,
        top_p: float = 0.95,
        min_p: float = 0.05,
        seed: int | None = None,
        verbose: bool = False,
    ) -> np.ndarray:
        language_id = language_id.lower()
        if language_id not in SUPPORTED:
            raise ValueError(f"Unsupported Chatterbox language: {language_id}")
        text = _punctuate(text)
        prompt = f"[{language_id}]{text}"
        ids = self.tokenizer(prompt, return_tensors="np")["input_ids"].astype(np.int64)
        if ids.shape[1] < 2:
            raise ValueError(f"Chatterbox tokenizer produced no text for: {text!r}")

        position_ids = np.where(
            ids >= START_SPEECH_TOKEN,
            0,
            np.arange(ids.shape[1])[None, :] - 1,
        ).astype(np.int64)
        embed_inputs = {
            "input_ids": ids,
            "position_ids": position_ids,
            "exaggeration": np.array([float(exaggeration)], dtype=np.float32),
        }

        rep_pen = RepetitionPenalty(1.2)
        rng = np.random.default_rng(seed)
        generated = np.array([[START_SPEECH_TOKEN]], dtype=np.int64)

        layers, heads, head_dim = 30, 16, 64
        past = {
            f"past_key_values.{i}.{kv}": np.zeros(
                (1, heads, 0, head_dim), dtype=np.float32
            )
            for i in range(layers)
            for kv in ("key", "value")
        }
        attention_mask = None
        cond_emb = None
        prompt_token = None
        ref_x = None
        prompt_feat = None

        for i in range(int(max_new_tokens)):
            inputs_embeds = self.embed_tokens.run(None, embed_inputs)[0]
            if i == 0:
                enc = self.speech_encoder.run(
                    None, {"audio_values": self.reference[None, :].astype(np.float32)}
                )
                cond_emb, prompt_token, ref_x, prompt_feat = enc
                inputs_embeds = np.concatenate((cond_emb, inputs_embeds), axis=1)
                attention_mask = np.ones((1, inputs_embeds.shape[1]), dtype=np.int64)

            logits, *present = self.language_model.run(
                None,
                dict(inputs_embeds=inputs_embeds, attention_mask=attention_mask, **past),
            )
            scores = rep_pen(generated, logits[:, -1, :])

            if temperature and temperature > 0:
                scores = scores / float(temperature)
                order = np.argsort(scores, axis=-1)[:, ::-1]
                sorted_scores = np.take_along_axis(scores, order, axis=-1)
                probs = np.exp(sorted_scores - sorted_scores.max(axis=-1, keepdims=True))
                probs /= probs.sum(axis=-1, keepdims=True)
                if min_p > 0.0:
                    probs[probs < float(min_p) * probs.max(axis=-1, keepdims=True)] = 0.0
                    probs /= np.maximum(probs.sum(axis=-1, keepdims=True), 1e-9)
                cumulative = np.cumsum(probs, axis=-1)
                cutoff = cumulative > float(top_p)
                cutoff[:, 1:] = cutoff[:, :-1]
                cutoff[:, 0] = False
                probs[cutoff] = 0.0
                probs /= np.maximum(probs.sum(axis=-1, keepdims=True), 1e-9)
                choice = order[0, rng.choice(len(probs[0]), p=probs[0])]
                nxt = np.array([[choice]], dtype=np.int64)
            else:
                nxt = np.argmax(scores, axis=-1, keepdims=True).astype(np.int64)

            generated = np.concatenate((generated, nxt), axis=-1)
            if (nxt.flatten() == STOP_SPEECH_TOKEN).all():
                break

            embed_inputs["input_ids"] = nxt
            embed_inputs["position_ids"] = np.full((1, 1), i + 1, dtype=np.int64)
            attention_mask = np.concatenate(
                [attention_mask, np.ones((1, 1), dtype=np.int64)], axis=1
            )
            for key, value in zip(past.keys(), present):
                past[key] = value

            if verbose and (i + 1) % 100 == 0:
                print(f"      chatterbox tokens: {i + 1}", flush=True)

        speech_tokens = generated[:, 1:-1]
        speech_tokens = np.concatenate([prompt_token, speech_tokens], axis=1)
        wav = self.conditional_decoder.run(
            None,
            {
                "speech_tokens": speech_tokens,
                "speaker_embeddings": ref_x,
                "speaker_features": prompt_feat,
            },
        )[0]
        wav = np.asarray(wav, dtype=np.float64).squeeze()
        peak = float(np.max(np.abs(wav))) + 1e-12
        if peak > 0.99:
            wav *= 0.99 / peak
        return fade(wav, self.sr, 0.01, 0.04)
