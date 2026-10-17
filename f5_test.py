# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
F5-TTS voice tuning bench (alternative cloner to Chatterbox).

F5 conditions directly on your reference audio, so it often matches accent/timbre
better than Chatterbox. Pacing is the `speed` knob (lower = slower). Similarity itself
is model-driven, so the big lever is still a clean reference recording.

Runs in the separate venv_f5 environment:
  venv_f5/bin/python f5_test.py                       # default phrase, sweep speeds
  venv_f5/bin/python f5_test.py --phrase "Hi, I'm Ali."
  venv_f5/bin/python f5_test.py --speed 0.95 --nfe 48 # one exact render, higher quality

Output: f5_test/*.wav  (plus 00_your_real_voice.wav to A/B). Listen in QuickTime.
"""
import argparse
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "f5_test")
DEFAULT_PHRASE = ("Hi, and welcome to this course. I'm a senior software engineer, "
                  "and I'll be your guide from the very first lecture to exam day.")


def pick_reference():
    for name in ("my_voice_clean.wav", "my_voice.wav"):
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            return p, name
    raise SystemExit("No my_voice_clean.wav or my_voice.wav found.")


def save16(path, wav, sr):
    wav = np.asarray(wav, dtype=np.float32)
    peak = np.max(np.abs(wav)) or 1.0
    if peak > 1.0:
        wav = wav / peak
    sf.write(path, wav, sr, subtype="PCM_16")


def floats(s):
    return [round(float(x), 3) for x in str(s).split(",") if x.strip() != ""]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phrase", default=DEFAULT_PHRASE)
    ap.add_argument("--speed", type=float, help="one speed value (pacing; <1 slower)")
    ap.add_argument("--speeds", default="0.9,1.0,1.1", help="speed values to sweep")
    ap.add_argument("--nfe", type=int, default=32, help="sampling steps (higher = better/slower)")
    ap.add_argument("--ref-text", default="", help="transcript of your reference (blank = auto-transcribe)")
    ap.add_argument("--device", default=None, help="mps / cpu (default: auto)")
    args = ap.parse_args()

    speeds = [args.speed] if args.speed is not None else floats(args.speeds)
    ref, refname = pick_reference()
    os.makedirs(OUTDIR, exist_ok=True)

    # real voice for A/B
    real, sr0 = sf.read(ref)
    save16(os.path.join(OUTDIR, "00_your_real_voice.wav"), real, sr0)

    from f5_tts.api import F5TTS
    from f5_tts.infer.utils_infer import preprocess_ref_audio_text

    f5 = F5TTS(model="F5TTS_v1_Base", device=args.device)

    # transcribe the reference once, then reuse for every render
    print("Preparing reference (transcribing if needed) ...")
    ref_proc, ref_text = preprocess_ref_audio_text(ref, args.ref_text)
    print(f"Reference text: {ref_text!r}\n")

    for i, speed in enumerate(speeds, 1):
        wav, sr, _ = f5.infer(ref_file=ref_proc, ref_text=ref_text, gen_text=args.phrase,
                              speed=speed, nfe_step=args.nfe, remove_silence=False)
        name = f"f5_speed{speed}_nfe{args.nfe}.wav"
        save16(os.path.join(OUTDIR, name), wav, sr)
        print(f"[{i}/{len(speeds)}] {name}")

    print(f"\nDone. Listen in QuickTime: open {os.path.relpath(OUTDIR, HERE)}")
    print("Compare each against 00_your_real_voice.wav.")


if __name__ == "__main__":
    main()
