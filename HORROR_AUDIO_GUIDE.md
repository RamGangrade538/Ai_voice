# Horror-Adaptive Music Bed Generation Guide

This guide covers generating a horror-adaptive lofi/devotional bed with `make_song.py`, modifying style YAMLs for darker tones, matching bed length to narration, and mixing with enhanced TTS using FFMPEG.

---

## 1. Generate a Lofi/Devotional Bed with Horror Atmosphere

### Prerequisite: Modify the style YAML for horror

The `make_song.py` project uses style YAML files for music generation. The default `styles/lofi.yaml` is bright and devotional. For horror, apply these modifications by editing `styles/lofi.yaml`:

| Parameter | Horror Modification | Rationale |
|-----------|---------------------|-----------|
| `bpm` | **55** (down from 68) | Slower tempo = heavier, more dread |
| `tonic_hz` | **110.0** (down from 130.81) | Lower pitch = darker, more ominous |
| `drone.gain` | **0.25** (up from 0.18) | More constant low-end presence |
| `pad.gain` | **0.15** (up from 0.09) | Fuller harmonic bed |
| `texture.lowpass` | **4500** (down from 8500) | Muffled, submerged, "from beyond the grave" quality |
| `reverb.decay` | **4.0** (up from 2.6) | More spacious, eerie tail |
| `reverb.mix` | **0.35** (up from 0.26) | More wet/reverb |
| `mix.bed_db` | **-5** (up from -8) | Bed more present in mix |
| `drums` | **null** (disable) | Remove rhythmic pulse that feels too musical |
| `ornament.vibrato` | **0.40** (up from 0.26) | Wider, more unstable pitch modulation |
| `ornament.scoop` | **0.7** (up from 0.4) | More glissando, unsettling slides |

### Apply horror style modifications

Edit `styles/lofi.yaml` with the values above (or use the backup and re-apply):

```bash
cp styles/lofi.yaml styles/lofi.yaml.bak
# Then edit with your preferred editor, applying the changes above
```

### Generate the bed WAV

```bash
# Using the modified lofi style with Hindi horror text (make_song.py requires Devanagari)
.venv/bin/python make_song.py --style lofi --text "ॐ नमः शिवाय। भयानक वातावरण। खौफनाक अनुभव।" --voice hm_psi --speed 0.85 --outdir out
```

**Alternative**: Use English text by working around the Devanagari check (see the "Workflow Notes" section below).

**Output**: `out/lofi_hm_psi_<timestamp>.wav` (full render) and `out/lofi_hm_psi_<timestamp>_bed.wav` (isolated bed).

### Working with am_fenrir English narration

`make_song.py`'s `synth_phrase()` function requires Devanagari (Sanskrit/Hindi) text. For English `am_fenrir` narration from `make_narration.py`, generate the bed separately and mix:

```bash
# Step 1: Generate enhanced TTS narration (Works with am_fenrir)
.venv/bin/python make_narration.py \
    --text-file story_horror.txt \
    --voice am_fenrir \
    --speed 0.85 \
    --seed 7 \
    --out-prefix out/tts_enhanced
# Produces: out/tts_enhanced.wav + out/tts_enhanced.mp3

# Step 2: Generate horror bed (using Hindi text or pre-rendered)
# ...see step 3 below

# Step 3: Mix (see Section 4)
```

---

## 2. YAML Style Modifications for Darker, Ominous Tones

### From `styles/lofi.yaml` → Horror Configuration

```yaml
name: lofi
bpm: 55                          # Slower = heavier dread
tonic_hz: 110.0                  # Lower pitch = darker

# Drone - constant low-end presence
drone:
  enabled: true
  gain: 0.25                     # More presence
  step: 2.4
  decay: 8.0
  pattern: [0, 7, 0, 0]

# Pad - harmonic foundation with descending progression
pad:
  enabled: true
  kind: rhodes
  gain: 0.15                     # Fuller harmonics
  chord: [0, 3, 7, 10]
  octave: 1
  progression: [0, -3, -5, -7]   # Descending = gloom

# Drums - disabled for horror
drums: null

# Texture - muffled, submerged
texture:
  lowpass: 4500                  # Cuts high frequencies
  highpass: 40
  width: 1.15
  vinyl: 0.06
  wobble: 0.0018
  wobble_rate: 0.28

# Reverb - larger, eerie space
reverb:
  decay: 4.0                     # More tail
  mix: 0.35                      # More wet
  predelay: 0.025
  damp: 5000

# Bed - more prominent
mix:
  bed_db: -5                     # Bed sits more present

# Ornament - unstable pitch
ornament:
  vibrato: 0.40                  # Wider vibrato
  scoop: 0.7                     # More glissando
  vibrato_rate: 4.9
  vibrato_onset: 0.42
  glide_ms: 85
  kan: 1.0
  taan: 0.0

# Vocal processing (subtle for horror)
vocal:
  lowcut: 95
  deess: 0.3
  thresh: -19
  ratio: 2.5
  reverb: 0.24
  reverb_decay: 2.4
  predelay: 0.025
  echo:
    enabled: true
    time: 0.35
    feedback: 0.22
    mix: 0.12

# Mastering
master:
  lufs: -14
```

### From `styles/bhajan.yaml` → Horror Configuration

```yaml
name: bhajan
bpm: 60                          # Slower than default 72
tonic_hz: 108.0                  # Lower than default 130.81

drone:
  enabled: true
  gain: 0.22                     # Increased from 0.16

pad:
  enabled: true
  kind: harmonium
  gain: 0.12                     # Increased from 0.07

texture:
  lowpass: 5000                  # Down from 13000
  highpass: 40

reverb:
  decay: 3.5                     # Up from 2.2
  mix: 0.30                      # Up from 0.25

mix:
  bed_db: -6                     # Up from -9

drums: null                      # Disable tabla rhythm

ornament:
  vibrato: 0.35
  scoop: 0.6

# Master
master:
  lufs: -14
```

### Core principles for horror YAML design

1. **Lower BPM** = slower, heavier feel
2. **Lower tonic** = deeper, darker pitch range
3. **Descending chord progressions** = sense of decline/gloom
4. **Lower lowpass cutoff** = muffled, submerged quality
5. **Higher reverb decay/mix** = larger, eerie space
6. **Reduced/removed drums** = avoid military/pulsing rhythms
7. **Increased bed_db** = bed present without overwhelming voice
8. **Higher scoop/vibrato** = unstable, unsettling pitch modulation

---

## 3. Trim/Extend Bed to Match Narration Length

`make_song.py` automatically adjusts the bed to the narration length:

### Automatic length matching (inside `make_song.py`)

```python
# Calculate total narration duration from cursor position after all phrases
total = cursor + int(outro * SR)
n = total  # target length in samples

# Render bed to target duration
bed = render_bed(style, n / SR, SR, bed_tonic, seed=seed)

# Pad or truncate to exact match
if len(bed) < n:
    bed = np.pad(bed, ((0, n - len(bed)), (0, 0)))   # pad with zeros
bed = bed[:n]                                         # truncate if longer
```

### Manual length adjustment (if needed)

#### Extend bed (if bed too short)

```bash
# Using FFMPEG to pad/loop the bed
ffmpeg -y -loglevel error -i out/lofi_bed.wav \
    -filter_complex "atrim=0:10,arepeat=3:limit=10" \
    -c:a pcm_s16le out/lofi_bed_padded.wav
```

#### Trim bed (if bed too long)

```bash
# Trim to exact narration length (e.g., 13.2 seconds)
ffmpeg -y -loglevel error -i out/lofi_bed.wav \
    -af "atrim=0:13.2" \
    -c:a pcm_s16le out/lofi_bed_trimmed.wav
```

### Verify bed length

```bash
# Check duration
ffprobe -show_format out/lofi_bed.wav 2>&1 | grep Duration
```

### Matching bed to specific narration

1. Generate narration with `make_narration.py` and note its duration
2. Generate bed with `make_song.py` -- the bed will be auto-sized to the narration
3. Or manually trim/pad using the commands above

---

## 4. Mix the Bed with Enhanced TTS Narration using FFMPEG

### Prerequisites

- Enhanced TTS WAV from `make_narration.py`: 48kHz mono, -16 LUFS, am_fenrir voice
- Bed WAV from `make_song.py`: same duration as narration (trimmed/padded if needed)
- Both files: 48kHz mono WAV (project standard)

### FFMPEG mixing approach

**Note**: FFMPEG 4.2.7 has a quirk where `amix` with resampled inputs may report "unconnected output" non-fatally. The workaround is to resample both inputs to 48000 Hz before mixing.

```bash
# Step 1: Resample both inputs to 48kHz (if needed)
ffmpeg -y -loglevel error -i enhanced_tts.wav -af "aresample=48000" /tmp/tts_resampled.wav
ffmpeg -y -loglevel error -i horror_bed.wav -af "aresample=48000" /tmp/bed_resampled.wav

# Step 2: Mix with amix
ffmpeg -y -loglevel error -i /tmp/tts_resampled.wav -i /tmp/bed_resampled.wav \
    -filter_complex "amix=duration=longest:weights=[1,0.5]" \
    -c:a pcm_s16le output_mixed.wav
```

### Balance weights reference

The `weights` parameter in `amix` controls the volume balance:

| Weights | Narration:Bed Ratio | dB Difference | Usage |
|---------|---------------------|---------------|-------|
| `[1, 0.3]` | 1:0.3 | -10.5 dB | Narration dominant, bed very subtle |
| `[1, 0.5]` | 1:0.5 | -6.0 dB | **Recommended starting point** - bed supports without overpowering |
| `[1, 0.8]` | 1:0.8 | -1.9 dB | Bed nearly equal to narration |
| `[1, 1.0]` | 1:1 | 0.0 dB | Equal prominence |
| `[1, 1.5]` | 1:1.5 | +3.5 dB | Bed louder than narration (atmospheric effect) |

### Practical horror recommendations

1. **Start with `[1, 0.5]`** - narration leads, bed provides subtle horror atmosphere
2. **If narration overpowers the horror feel**, increase bed: `[1, 0.6]` or `[1, 0.7]`
3. **If bed feels too dominant**, reduce: `[1, 0.4]`
4. **For "voice from beyond" effect**: try `[1, 1.2]` with heavy reverb on bed only
5. **Always test** with headphones - horror is often heard on varied systems

### Full end-to-end mixing pipeline

```bash
# Step 1: Resample both to 48kHz
ffmpeg -y -loglevel error -i out/tts_enhanced.wav -af "aresample=48000" /tmp/tts_48k.wav
ffmpeg -y -loglevel error -i out/lofi_bed.wav -af "aresample=48000" /tmp/bed_48k.wav

# Step 2: Mix with amix (narration:bed = 1:0.5)
ffmpeg -y -loglevel error -i /tmp/tts_48k.wav -i /tmp/bed_48k.wav \
    -filter_complex "amix=duration=longest:weights=[1,0.5]" \
    -c:a pcm_s16le /tmp/mixed_raw.wav

# Step 3: Normalize to -16 LUFS / -1.5 dBTP and encode MP3
ffmpeg -y -loglevel error -i /tmp/mixed_raw.wav \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true" \
    -c:a libmp3lame -b:a 192k \
    out/horror_story_final.mp3
```

### numpy-based mixing alternative (FFMPEG amix workaround)

If the `amix` filter has issues with your FFMPEG version, use Python/numpy:

```bash
.venv/bin/python -c "
import numpy as np
import soundfile as sf
import subprocess
import json
from src.util import db_to_lin, rms

# Load files
nar, sr = sf.read('out/tts_enhanced.wav')
bed, sr_bed = sf.read('out/lofi_bed.wav')

# Ensure mono
if bed.ndim > 1:
    bed = bed.mean(axis=1)

# Trim/pad bed to match narration length
target_len = len(nar)
if len(bed) < target_len:
    bed = np.pad(bed, (0, target_len - len(bed)))
elif len(bed) > target_len:
    bed = bed[:target_len]

# Mix with weights [1, 0.5]
mixed = nar + bed * 0.5

# Normalize to -16 LUFS
target_rms_lin = db_to_lin(-18.0)
current_rms = rms(mixed)
gain = target_rms_lin / max(current_rms, 1e-9)
mixed_norm = mixed * gain

sf.write('/tmp/mixed_norm.wav', mixed_norm, sr)

# loudnorm + MP3
probe = subprocess.run(
    ['ffmpeg', '-hide_banner', '-i', '/tmp/mixed_norm.wav', '-af',
     'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'],
    capture_output=True, text=True,
)
stats = json.loads(probe.stderr[probe.stderr.rfind('{'):])
norm = (f'loudnorm=I=-16:TP=-1.5:LRA=11:'
        f'measured_I={stats[\"input_i\"]}:measured_TP={stats[\"input_tp\"]}:'
        f'measured_LRA={stats[\"input_lra\"]}:measured_thresh={stats[\"input_thresh\"]}:'
        f'offset={stats[\"target_offset\"]}:linear=true')

subprocess.run(
    ['ffmpeg', '-y', '-loglevel', 'error', '-i', '/tmp/mixed_norm.wav', '-af', norm,
     '-ac', '1', '-c:a', 'pcm_s16le', '/tmp/final_wav.wav'],
    check=True,
)
subprocess.run(
    ['ffmpeg', '-y', '-loglevel', 'error', '-i', '/tmp/final_wav.wav',
     '-c:a', 'libmp3lame', '-b:a', '192k', 'out/horror_story_final.mp3'],
    check=True,
)
print('Done! out/horror_story_final.mp3')
"
```

---

## 5. Adjust Balance (Weights Parameter) Between Narration Voice and Music Bed

The `weights` parameter in the `amix` FFMPEG filter controls the volume balance between narration and music bed. Format: `weights=[narration_gain, bed_gain]`.

### How weights map to dB difference

```
dB difference = 20 * log10(weight_bed / weight_narration)

weights=[1, 0.3]  → -10.5 dB (bed quieter)
weights=[1, 0.5]  → -6.0 dB  (bed quieter - recommended)
weights=[1, 0.8]  → -1.9 dB  (bed nearly equal)
weights=[1, 1.0]  →   0.0 dB  (equal)
weights=[1, 1.5]  →  +3.5 dB  (bed louder)
```

### Common horror balance scenarios

| Goal | Weights | Description |
|------|---------|-------------|
| **Narration dominant** (voice clear, bed subtle) | `[1, 0.3]` | Bed is 10.5dB lower - good for clear story delivery |
| **Balanced** (voice and bed equal) | `[1, 1.0]` | Equal prominence - bed supports but doesn't overpower |
| **Bed dominant** (atmospheric, voice submerged) | `[1, 1.5]` | Bed is 3.5dB louder - for ambient horror where words are secondary |
| **Subtle atmosphere** (bed very faint) | `[1, 0.2]` | Bed is 14dB lower - barely perceptible texture |

### Practical adjustment workflow

1. **Start with `[1, 0.5]`** - this is the recommended default for horror
2. **Test the mix**: Listen with headphones - can you hear both the story and the horror atmosphere?
3. **Adjust upward** (increase bed presence): `[1, 0.6]`, `[1, 0.7]`
4. **Adjust downward** (reduce bed): `[1, 0.4]`, `[1, 0.3]`
5. **For specific effects**:
   - **"Ghostly whisper"**: `[1, 1.2]` with reverb on bed only
   - **"Distant memory"**: `[1, 0.3]` with lowpass on bed
   - **"Inescapable atmosphere"**: `[1, 1.5]` with full reverb

### Example: Interactive balance adjustment script

```bash
#!/bin/bash
NARRATION="out/tts_enhanced.wav"
BED="out/lofi_bed.wav"

for ratio in 0.3 0.5 0.6 0.7; do
    ffmpeg -y -loglevel error -i "$NARRATION" -i "$BED" \
        -filter_complex "amix=duration=longest:weights=[1,$ratio]" \
        -c:a libmp3lame -b:a 192k \
        "test_weight_${ratio}.mp3"
    echo "Tested weight=$ratio - listen and adjust"
done
```

### Balancing tip for horror

In horror, the bed is often more effective when it's **subtle enough** that the listener barely notices it on first listen, but reveals its atmosphere on repeated listens. Start at `[1, 0.5]` and adjust based on whether the story feels "enhanced" or "overshadowed" by the music.

---

## Complete End-to-End Workflow

```bash
# Step 1: Generate enhanced TTS narration
.venv/bin/python make_narration.py \
    --text-file /home/ubuntu/Desktop/Audio/story_horror.txt \
    --voice am_fenrir \
    --speed 0.85 \
    --seed 7 \
    --out-prefix /home/ubuntu/Desktop/Audio/out/tts_enhanced
# Output: out/tts_enhanced.wav + out/tts_enhanced.mp3

# Step 2: Generate horror-adaptive music bed
# (style YAML already modified for horror as described in Section 2)
.venv/bin/python make_song.py \
    --style lofi \
    --text "ॐ नमः शिवाय। भयानक वातावरण। खौफनाक अनुभव।" \
    --voice hm_psi \
    --speed 0.85 \
    --outdir /home/ubuntu/Desktop/Audio/out
# Output: out/lofi_hm_psi_*.wav (bed auto-sized to text length)

# Step 3: Resample both to 48kHz (if bed uses different sample rate)
ffmpeg -y -loglevel error -i out/tts_enhanced.wav -af "aresample=48000" /tmp/tts_48k.wav
ffmpeg -y -loglevel error -i out/lofi_bed.wav -af "aresample=48000" /tmp/bed_48k.wav

# Step 4: Mix with amix (balance = 1:0.5 = narration:bed)
ffmpeg -y -loglevel error -i /tmp/tts_48k.wav -i /tmp/bed_48k.wav \
    -filter_complex "amix=duration=longest:weights=[1,0.5]" \
    -c:a pcm_s16le /tmp/mixed_raw.wav

# Step 5: Normalize to -16 LUFS / -1.5 dBTP and encode MP3
ffmpeg -y -loglevel error -i /tmp/mixed_raw.wav \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true" \
    -c:a libmp3lame -b:a 192k \
    out/horror_story_final.mp3

echo "Complete! Output: out/horror_story_final.mp3"
# Duration should match narration: ~13s for 20-word excerpt, full story will vary
```

---

## Workflow Notes

### make_song.py text constraint

`make_song.py` uses `src/voice.py:synth_phrase()` which requires Devanagari/Sanskrit text (checks for `[\u0900-\u097F]`). For English `am_fenrir` narration:

- **Option A**: Generate the bed with Hindi devotional text, then mix with the English narration
- **Option B**: Use the numpy-mixing alternative (Section 4) which works with any WAV files
- **Option C**: If you have Devanagari horror text, make_song.py will generate the bed directly

### Sample rate compatibility

- `make_narration.py` outputs **48kHz** WAV (project standard)
- `make_song.py` may output at **44.1kHz** or **48kHz** depending on the Kokoro pipeline version
- Always resample to 48kHz before mixing: `ffmpeg -i input.wav -af "aresample=48000" output.wav`

### CPU-only constraint

- Render one job at a time; never run parallel TTS jobs
- Both `make_narration.py` and `make_song.py` are CPU-only with Kokoro + WORLD
- Rendering times: ~1-3x real-time on typical CPU

### Output contract

- 48 kHz mono WAV
- -16 LUFS / -1.5 dBTP loudness
- 192 kbps MP3
- Output written to `out/` (git-ignored)