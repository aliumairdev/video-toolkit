# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
Voice tuning bench. Generate ONE short phrase across a grid of settings so you can
quickly find the pacing / expressiveness / accent that best matches your real voice,
then copy the winning numbers into clone_voice.py.

The model loads once, so a whole sweep takes about as long as a single sentence.

Examples:
  python voice_test.py                              # default phrase, sweep of settings
  python voice_test.py --phrase "Hi, I'm Ali."      # your own phrase
  python voice_test.py --cfgs 0.2,0.3 --exags 0.4   # custom sweep
  python voice_test.py --cfg 0.3 --exag 0.4 --temp 0.7   # a single exact render

Output: voice_test/*.wav  (plus 00_your_real_voice.wav to A/B against).
Open them in QuickTime (NOT the VS Code preview) and pick the closest to you.
Then tell me the filename, or edit CFG_WEIGHT / EXAGGERATION / TEMPERATURE in clone_voice.py.
"""
import argparse
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import torch

if not torch.cuda.is_available():
    _orig_load = torch.load
    def _load_cpu(*a, **k):
        k.setdefault("map_location", torch.device("cpu"))
        return _orig_load(*a, **k)
    torch.load = _load_cpu

import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 24000
OUTDIR = os.path.join(HERE, "voice_test")
DEFAULT_PHRASE = ("Hi, and welcome to this course. I'm a senior software engineer, "
                  "and I'll be your guide from the very first lecture to exam day.")


def pick_reference():
    for name in ("my_voice_clean.wav", "my_voice.wav"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            return p, name
    raise SystemExit("No my_voice_clean.wav or my_voice.wav found.")


def trim_silence(wav, thresh_db=-40.0, keep_ms=60):
    amp = wav.abs().max(dim=0).values
    thresh = amp.max() * (10 ** (thresh_db / 20.0))
    loud = (amp > thresh).nonzero()
    if loud.numel() == 0:
        return wav
    margin = int(SR * keep_ms / 1000)
    return wav[:, max(0, int(loud[0]) - margin):min(wav.shape[1], int(loud[-1]) + margin)]


def save16(path, wav):
    ta.save(path, wav.clamp(-1, 1), SR, encoding="PCM_S", bits_per_sample=16)


def floats(s):
    return [round(float(x), 3) for x in str(s).split(",") if x.strip() != ""]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phrase", default=DEFAULT_PHRASE, help="short text to narrate")
    # single-render shortcuts
    ap.add_argument("--cfg", type=float, help="one cfg_weight value (pacing)")
    ap.add_argument("--exag", type=float, help="one exaggeration value")
    ap.add_argument("--temp", type=float, help="one temperature value")
    # sweep ranges (comma-separated); used when the single values above are omitted
    ap.add_argument("--cfgs", default="0.2,0.3,0.4", help="cfg_weight values to sweep (pacing)")
    ap.add_argument("--exags", default="0.4,0.6", help="exaggeration values to sweep")
    ap.add_argument("--temps", default="0.8", help="temperature values to sweep")
    args = ap.parse_args()

    cfgs = [args.cfg] if args.cfg is not None else floats(args.cfgs)
    exags = [args.exag] if args.exag is not None else floats(args.exags)
    temps = [args.temp] if args.temp is not None else floats(args.temps)
    combos = [(c, e, t) for e in exags for c in cfgs for t in temps]

    ref, refname = pick_reference()
    os.makedirs(OUTDIR, exist_ok=True)

    # copy the real voice in for side-by-side comparison
    real, _ = ta.load(ref)
    save16(os.path.join(OUTDIR, "00_your_real_voice.wav"), real)

    device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
    try:
        model = ChatterboxTTS.from_pretrained(device=device)
    except Exception as e:
        print(f"Could not load on {device} ({e}); using CPU.")
        model = ChatterboxTTS.from_pretrained(device="cpu")
    print(f"Loaded on {device}. Reference: {refname}. Rendering {len(combos)} variation(s).\n")

    for i, (cfg, exag, temp) in enumerate(combos, 1):
        wav = model.generate(args.phrase, audio_prompt_path=ref,
                             exaggeration=exag, cfg_weight=cfg, temperature=temp)
        wav = trim_silence(wav.cpu())
        name = f"cfg{cfg}_exag{exag}_temp{temp}.wav"
        save16(os.path.join(OUTDIR, name), wav)
        print(f"[{i}/{len(combos)}] {name}  ({wav.shape[1] / SR:.1f}s)")

    print(f"\nDone. Listen in QuickTime: open {os.path.relpath(OUTDIR, HERE)}")
    print("Compare each against 00_your_real_voice.wav, then set the winning")
    print("CFG_WEIGHT / EXAGGERATION / TEMPERATURE in clone_voice.py.")


if __name__ == "__main__":
    main()
