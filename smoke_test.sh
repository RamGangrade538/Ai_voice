#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Run ./setup.sh first."
  exit 1
fi

for style in mantra bhajan lofi; do
  "$PY" make_song.py --style "$style" --repeat 1 --seed 1 --name "smoke_$style" > /dev/null
  test -s "out/smoke_$style.wav"
  test -s "out/smoke_$style.mp3"
done

"$PY" - <<'PY'
import glob
import numpy as np
import soundfile as sf

ok = True
for path in sorted(glob.glob("out/smoke_*.wav")):
    if path.endswith("_premaster.wav"):
        continue
    x, sr = sf.read(path)
    m = x.mean(axis=1)
    peak = float(np.max(np.abs(x)))
    dur = len(m) / sr
    good = 5.0 < dur < 600.0 and 0.05 < peak <= 0.99 and not np.isnan(m).any()
    ok = ok and good
    print(f"{'PASS' if good else 'FAIL'}  {path}  {dur:.1f}s  peak={peak:.2f}")
print("ALL PASS" if ok else "SOME FAILED")
raise SystemExit(0 if ok else 1)
PY
