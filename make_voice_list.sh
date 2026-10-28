#!/bin/bash
cd /home/ubuntu/Desktop/Audio
source .venv/bin/activate
PYTHONPATH=/home/ubuntu/Desktop/Audio python << 'PY'
import os, json, numpy as np, soundfile as sf
from kokoro import KPipeline
from src.util import SR

def classify(v):
    if v.startswith('hf_'): lang='hi'
    elif v.startswith(('if_','pf_','ef_','ff_')): lang='multi'
    elif v.startswith(('jf_','jm_')): lang='ja'
    elif v.startswith(('zf_','zm_')): lang='zh'
    elif v.startswith(('bf_','bm_')): lang='en-gb'
    elif v.startswith(('af_','am_')): lang='en-us'
    elif v.startswith(('em_','im_')): lang='multi'
    elif v.startswith('hm_'): lang='hi'
    elif v.startswith('pm_'): lang='pt'
    else: lang='other'
    male = v.startswith(('am_', 'bm_', 'hm_', 'em_', 'im_', 'jm_', 'pm_', 'zm_'))
    return lang, 'male' if male else 'female'

text_en = "The vault locks were designed to keep something massive locked in."
text_hi = "तिजोरी के ताले बाहर से बंद होने के लिए डिजाइन किए गए हैं।"

os.makedirs('out/voices', exist_ok=True)
results = []
voices_dir = os.path.expanduser('~/.cache/huggingface/hub/models--hexgrad--Kokoro-82M/snapshots/f3ff3571791e39611d31c381e3a41a3af07b4987/voices/')
voices = sorted([f.replace('.pt','') for f in os.listdir(voices_dir) if f.endswith('.pt')])

# Skip already done
done = set([f.split('_')[0] for f in os.listdir('out/voices') if f.endswith('.wav')])

for v in voices:
    if v in done:
        lang, gender = classify(v)
        results.append({'voice': v, 'lang': lang, 'gender': gender, 'file': f'out/voices/{v}_{lang}_{gender}.wav'})
        continue
    lang, gender = classify(v)
    try:
        if lang == 'hi':
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
        else:
            # try english
            pipeline = KPipeline(lang_code='b' if lang == 'en-gb' else 'a')
            chunks = []
            for _, _, audio in pipeline(text_en, voice=v, speed=0.9):
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
    json.dump(sorted(results, key=lambda x: (x['lang'], x['gender'], x['voice'])), f, indent=2)

print(f'Done: {len(results)}')
PY
