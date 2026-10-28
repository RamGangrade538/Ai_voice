#!/usr/bin/env python3
import os
import json
import numpy as np
import soundfile as sf
from kokoro import KPipeline
from src.util import SR

# Classify voices
def classify(v):
    if v.startswith(('hf_', 'if_', 'pf_', 'ef_', 'ff_')):  # Hindi, Italian etc
        lang = 'hi' if v.startswith('hf_') else 'multi'
    elif v.startswith(('jf_', 'jm_')): lang = 'ja'
    elif v.startswith(('zf_', 'zm_')): lang = 'zh'
    elif v.startswith(('bf_', 'bm_')): lang = 'en-gb'
    elif v.startswith(('af_', 'am_')): lang = 'en-us'
    else: lang = 'other'
    male = v.startswith(('am_', 'bm_', 'hm_', 'em_', 'im_', 'jm_', 'pm_', 'zm_'))
    return lang, 'male' if male else 'female'

text_en = "The vault locks were designed to keep something massive locked in."
text_hi = "तिजोरी के ताले बाहर से बंद होने के लिए डिजाइन किए गए हैं।"
text_short = text_en

os.makedirs('out/voices', exist_ok=True)
results = []

voices = sorted([f.replace('.pt','') for f in os.listdir(os.path.expanduser('~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots/f3ff3571791e39611d31c381e3a41a3af07b4987/voices/')) if f.endswith('.pt')])

for v in voices:
    lang, gender = classify(v)
    try:
        if lang in ['en-us', 'en-gb', 'multi', 'other']:
            pipeline = KPipeline(lang_code='a' if lang != 'en-gb' else 'b')
            chunks = []
            for _, _, audio in pipeline(text_short, voice=v, speed=0.9):
                chunks.append(np.asarray(audio, dtype=np.float64))
            if chunks:
                y = np.concatenate(chunks)
                out_path = os.path.join('out/voices', f'{v}_{lang}_{gender}.wav')
                sf.write(out_path, y, SR)
                results.append({'voice': v, 'lang': lang, 'gender': gender, 'file': out_path})
                print('ok', v)
                continue
        elif lang == 'hi':
            pipeline = KPipeline(lang_code='h')
            chunks = []
            for _, _, audio in pipeline(text_hi, voice=v, speed=0.9):
                chunks.append(np.asarray(audio, dtype=np.float64))
            if chunks:
                y = np.concatenate(chunks)
                out_path = os.path.join('out/voices', f'{v}_{lang}_{gender}.wav')
                sf.write(out_path, y, SR)
                results.append({'voice': v, 'lang': lang, 'gender': gender, 'file': out_path})
                print('ok', v)
                continue
    except Exception as e:
        print('err', v, e)
        continue

with open('out/voices/voices_list.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f'Done: {len(results)}')
