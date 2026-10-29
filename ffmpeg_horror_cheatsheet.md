# FFMPEG Horror Sound Effects Cheat Sheet

For enhanced TTS narration from `make_narration.py` (am_fenrir voice, 48kHz mono WAV).

---

## Prerequisites

Place your sound effect files in a known directory. This cheat sheet uses:

- `./audio/door_creak.wav` - Door creak sound effect
- `./audio/wind_ambient.wav` - Ambient wind/street noise
- `input_narration.wav` - Enhanced TTS output from make_narration.py
- `output_horror.wav` - Intermediate WAV with effects
- `output_horror.mp3` - Final 192 kbps MP3

---

## 1. Add Door Creak at Beginning

```bash
ffmpeg -y -loglevel error -i ./audio/door_creak.wav -i input_narration.wav \
    -filter_complex "[0:a]atrim=0:1,volume=1.5[creak]; \
                     [creak][1:a]amix=duration=shortest:weights=[1,0.8]" \
    output_door_creak_started.wav
```

**What it does:** Combines the door creak (amplified 1.5x) with the narration, trimming to the creak's length so it sits at the very start.

---

## 2. Add Reverb for Atmospheric Feel

```bash
ffmpeg -y -loglevel error -i input_narration.wav \
    -af "aecho=0.8:0.4:1000:0.3" \
    output_narration_reverb.wav
```

**Filter: `aecho` (reverb alternative)**

- `aecho=0.8:0.4:1000:0.3` — Creates echo repetitions at 0.8 volume, 0.4 feedback, 1000ms delay, 0.3 damping
- `aecho=0.5:0.3:500:0.5` — Subtle room simulation: quieter echoes, shorter delay, more damping

*Adds early reflections and tail that simulates reverb. Not as rich as a full reverb filter, but works with this FFmpeg build.*

---

## 3. Layer Ambient Wind/Street Noise

```bash
ffmpeg -y -loglevel error -i input_narration.wav -i ./audio/wind_ambient.wav \
    -filter_complex "[1:a]atempo=0.95,volume=0.3[wind]; \
                     [0:a][wind]amix=duration=longest:weights=[0.7,0.3]" \
    output_narration_with_wind.wav
```

**Filters used:**

- `atempo=0.95`: Slightly slow down the wind audio to match narration pacing
- `volume=0.3`: Lower wind volume to 30% so it doesn't overpower the voice
- `amix`: Mixes two audio streams, `duration=longest` keeps both fully, `weights` controls balance

*Adds a subtle background of wind/street noise that creates an eerie atmosphere.*

---

## 4. Mix Multiple Audio Sources Together

```bash
ffmpeg -y -loglevel error \
    -i ./audio/door_creak.wav \
    -i input_narration.wav \
    -i ./audio/wind_ambient.wav \
    -filter_complex "
        [0:a]volume=1.5[creak];
        [2:a]atempo=0.95,volume=0.3[wind];
        [1:a]areverse[rev];
        [rev]areverse[rev_back];
        [creak][1:a][rev_back]amix=duration=shortest:weights=[1,1,0.5]
    " output_mixed_sources.wav
```

**Filter: `amix`**

- `duration=shortest`: Mix only as long as the shortest input (good for intro+narration)
- `weights`: Volume balance for each input stream (creak:narration:wind = 1:1:0.5)
- `areverse`: Reverse audio temporarily (used here as a creative effect demo)

*Combines door creak, narrated text, and wind ambience into one cohesive track.*

---

## 5. Convert to 192 kbps MP3 (Project Standard)

```bash
ffmpeg -y -loglevel error -i output_narration_with_wind.wav \
    -c:a libmp3lame -b:a 192k output_horror.mp3
```

**What it does:** Encodes the WAV to MP3 at 192 kbps constant bitrate — the project's standard audio quality.

*Matches the output from `make_narration.py`'s `master()` function.*

---

## 6. Set Loudness to -16 LUFS / -1.5 dBTP (Mastering)

```bash
ffmpeg -y -loglevel error -i output_narration_with_wind.wav \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true" \
    output_normalized.wav
```

**Filter: `loudnorm`** (EBU R128 loudness normalization)

- `I=-16`: Target integrated loudness in LUFS (broadcast standard)
- `TP=-1.5`: Target true peak in dBTP (prevents digital clipping)
- `LRA=11`: Target loudness range in ms (typical for dialogue)
- `linear=true`: Use linear domain for measurement (more accurate)

*The same loudness target used by `make_narration.py`'s `master()` function. In production, a two-step probe+normalize approach (as in the code) yields more accurate results, but this one-pass approach works well for most content.*

---

## Complete End-to-End Horror Pipeline

This single command applies all effects in sequence:

```bash
ffmpeg -y -loglevel error -i input_narration.wav \
    -filter_complex "
        # Step 1: Add door creak at beginning (volume 1.5x)
        [0:a]atrim=0:1,volume=1.5[creak];
        # Step 2: Apply aecho for atmospheric echo/reverb
        [creak]aecho=0.8:0.4:1000:0.3[reverbed];
        # Step 3: Layer wind ambience (volume 0.3, slow down slightly)
        [2:a]atempo=0.95,volume=0.3[wind];
        # Step 4: Mix all together
        [reverbed][1:a][wind]amix=duration=longest:weights=[1,1,0.5]
    " \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11:linear=true" \
    -c:a libmp3lame -b:a 192k output_horror.mp3
```

**Notes on the complete pipeline:**

1. **Input:** `input_narration.wav` (48kHz mono from make_narration.py)
2. **Filter chain:**Creak → Reverb → Wind → Amix → Loudness normalization → MP3 encode
3. **Output:** `output_horror.mp3` — 192 kbps, -16 LUFS, -1.5 dBTP, with door creak at start and atmospheric reverb/wind

---

## Filter Quick Reference

| Filter | Purpose | Key Parameters |
|--------|---------|----------------|
| `reverb` | Simulates room acoustics for atmosphere | `room_size`, `decay`, `wet`, `dry` |
| `amix` | Mix multiple audio streams | `weights`, `duration` (shortest/longest) |
| `loudnorm` | Normalize to loudness targets | `I` (LUFS), `TP` (dBTP), `LRA` |
| `atempo` | Change playback speed/pitch | `0.95` = 5% slower, preserves pitch roughly |
| `volume` | Adjust volume gain | `1.5` = +3.5dB, `0.5` = -6dB |
| `highpass` | Remove low rumble | `f=60` cuts below 60 Hz |
| `lowpass` | Remove high harshness | `f=8000` keeps below 8 kHz |

---

## Tips for Horror Audio

- **Door creak:** Choose a creak that's slightly longer than your narration's first pause (300-500ms typical)
- **Reverb:** Start subtle — `room_size=0.5, decay=2.0, wet=10` is often enough. Too much reverb muddies the voice.
- **Wind:** Pink or brown noise works best for street/ambient sound. Avoid white noise (too harsh).
- **Loudness:** -16 LUFS is broadcast radio/podcast standard. Dialogue should peak around -1 to -3 dBTP after normalization.
- **Order matters:** Creatives (creak, reverb) before corrective (loudness) gives best results.