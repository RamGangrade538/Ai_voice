# Devotional Studio (open source, CPU-first)

Render Hindi/Sanskrit **mantra, bhajan and lofi devotional** tracks from text:
Kokoro TTS → WORLD pitch/time singing → humanization → style-based music bed →
Matchering/loudness master.

Everything runs locally on CPU. No cloud, no paid API.

## Quick start

```bash
./setup.sh
source .venv/bin/activate

python make_song.py --style mantra --repeat 8 --name om_namah_shivaya
python make_song.py --style bhajan --repeat 4 --text "श्री राम जय राम जय जय राम।"
python make_song.py --style lofi  --repeat 3 --voice hm_omega
python make_song.py --style mantra --text-file lyrics.txt --reference assets/refs/ref.wav
python make_song.py --style bhajan --melody-audio my_hum.wav --tempo-from-melody --repeat 2
python make_song.py --style shiva_temple --text-file lyrics/shiva_temple.txt
```

Outputs land in `out/`: `.wav` (44.1 kHz, −14 LUFS), `.mp3`, a pre-master, and a
`.json` with all render settings. `--keep-stems` also writes the vocal and bed.

```bash
python preview_voices.py     # audition all four Hindi voices
```

## Test

```bash
./smoke_test.sh     # renders all 3 styles + checks duration/peak/NaN/mp3
```

## Styles

| File | Feel | Tempo | What is synthesized |
|---|---|---|---|
| `styles/mantra.yaml` | temple chant | 55 BPM | tanpura, low harmonium, bell, long reverb, no drums |
| `styles/bhajan.yaml` | harmonium bhajan | 72 BPM | tanpura, harmonium, tabla, manjira, echo |
| `styles/lofi.yaml` | lofi devotional | 68 BPM | tanpura, Rhodes chords, soft kick/snare/hats, vinyl, tape wobble |
| `styles/shiva_temple.yaml` | early-morning Shiva temple chant | 50 BPM | tanpura, distant bell, stone-room ambience, no drums |

Copy any YAML, change `bpm`, `melody` (semitones), `chords`, `drums`, reverb and
texture values, and pass `--style my_style.yaml`. The `ornament` block controls
meend (glide), kan swar, vibrato and taan; `call_response` alternates a second
voice (octave up by default) for the answer line. `sustain` (1.0–2.0) stretches
vowels and compresses consonants: higher values sound more legato/sung, lower
values more speech-like.

## Text rules

- Use **Devanagari**. Kokoro's Hindi G2P is used for both Hindi and Sanskrit.
- `।`, `|`, `;`, newlines split phrases; commas split long phrases. Each phrase
  gets its own melodic contour, breath and pause.
- **Blank lines are section pauses.** One blank line inserts `section_pause_sec`
  (default 2 s) before the next phrase; consecutive blank lines add up. A line
  with only punctuation also counts as a pause.
- The parser is Unicode-aware, so Hindi, Sanskrit and Devanagari text import
  cleanly. The Kokoro Hindi voice itself still expects Devanagari; transliterate
  other Indic scripts first.
- Sanskrit pronunciation is close but not perfect (visarga, `ज्ञ`, anusvāra).
  Workaround: respell problem words phonetically in Devanagari, or fine-tune a
  TTS model on Sanskrit data.
- `--no-sing` keeps the natural spoken voice over the bed.

## Flags worth knowing

| Flag | Meaning |
|---|---|
| `--voice hf_alpha` | female voice (`hf_alpha`, `hf_beta`) |
| `--voice hm_psi` | male voice (`hm_psi` soft, `hm_omega` deep) |
| `--speed 0.82` | slower = more chant-like |
| `--repeat 8` | repeat the phrase block N times |
| `--tonic 146.83` | force the key instead of auto-matching the voice |
| `--reference ref.wav` | Matchering tonal/level match to a released track |
| `--melody-audio hum.wav` | follow the melody you hum/sing (mono, any key) |
| `--tempo-from-melody` | estimate BPM from `--melody-audio` |
| `--bpm 84` | override the style tempo |
| `--no-call-response` | disable the bhajan answer voice |
| `--lufs -16` | override loudness target |
| `--seed 42` | reproducible humanization |
| `--keep-stems` | export vocal and bed separately |

## How the "singing" works on CPU

`pyworld` (WORLD vocoder) analyzes each TTS phrase into f0, spectral envelope
and aperiodicity. The frames are time-stretched to the musical phrase length,
the f0 track is replaced with either a raga-flavoured note contour or the pitch
curve extracted from `--melody-audio`, and WORLD resynthesizes with preserved
formants. That is why it sounds sung rather than chipmunk-shifted.

Melodic ornaments: portamento (meend), grace touches (kan swar), delayed
vibrato, optional fast taan at phrase ends, and a second voice answering in the
next octave (`call_response`). The humanization layer adds real breath noise,
level/timing jitter, de-essing, compression, room/temple reverb and echo.

For a melody, hum **one line/phrase** (10–20 s) into any recorder; the clip's
last note is treated as Sa, so end on the tonic or pass `--tonic`. Do not feed a
copyrighted singer's recording into a cloning model; use your own voice or a
clip you have rights to.

## Honest quality ceiling

This CPU stack is a **draft**, not a release master. Two upgrades matter:

1. **Voice**: on a GPU, swap Kokoro for `Chatterbox Multilingual` (MIT, emotion
   control), `Orpheus 3B` (Apache-2.0, breath/sigh tags) or `IndicF5` (zero-shot
   clone from 5–10 s). This removes most of the remaining "AI" sheen.
2. **Instruments**: replace the synthesized tanpura/tabla/harmonium with CC0
   sample libraries (FreePats, VSCO2) inside the `_pluck` / `_render_drums`
   functions, or arrange in LMMS/Ardour and feed the stem in.
3. **Full songs**: `ACE-Step 1.5` (Apache-2.0) generates complete Hindi vocal +
   instrumental songs and is the closest open-source equivalent to Suno. It needs
   a GPU (about 4 GB VRAM); this CPU-only box cannot run it. Use `RVC` on a real
   take for a devotional timbre.
4. **Best result**: record one real human take, use it as the lead vocal, and
   keep AI only for the bed. Nothing beats a real voice for "not AI".

## Licenses

- Kokoro-82M: Apache-2.0. Chatterbox: MIT. Orpheus: Apache-2.0. ACE-Step: Apache-2.0.
- XTTS-v2 and several cloned-voice weights are **non-commercial**; avoid them for
  monetized uploads.
- Never clone a singer's voice without written consent.
- Verify the license of every sample pack you add.

## Layout

```
make_song.py        CLI / timeline / mix
preview_voices.py   A/B the four voices
src/voice.py        Kokoro TTS, phrase splitting
src/sing.py         WORLD pitch + time singing, ornaments
src/melody.py       hum/audio melody extraction + tempo estimate
src/bed.py          tanpura, harmonium, tabla, lofi drums, bells
src/fx.py           reverb, delay, compressor, de-esser, vinyl, wobble
src/master.py       limiter, loudnorm, Matchering, mp3
styles/*.yaml       style presets
```
