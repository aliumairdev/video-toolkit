#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
One command that runs the whole pipeline:

    clean reference  ->  clone_voice.py  ->  build_video.py  ->  video.mp4

Usage:
    python make_video.py                 # full run: narrate + final 1080p video
    python make_video.py --preview       # narrate, then just write previews/overview.jpg and stop
    python make_video.py --draft         # faster 720p render (good for checking timing)
    python make_video.py --no-music      # narration only, no background music
    python make_video.py --skip-narration# reuse the existing narration.wav / timeline.json
    python make_video.py --force-ref     # rebuild my_voice_clean.wav even if it looks current

Everything else (brand, colours, voice settings) still lives at the top of
build_video.py and clone_voice.py.
"""
import argparse
import os
import shutil
import subprocess
import sys

import project

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # use the same interpreter (your 3.11 venv) for the sub-scripts

# ffmpeg filter that turns a raw take into a clean cloning reference:
# high-pass rumble, light denoise, strip long silences, normalise to ~-20 LUFS / -2 dB peak.
REF_FILTER = (
    "highpass=f=80,afftdn=nr=12:nf=-25,"
    "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:"
    "stop_periods=-1:stop_silence=0.3:stop_threshold=-40dB:detection=peak,"
    "loudnorm=I=-19:TP=-2:LRA=11"
)


def run(cmd, label, retries=0):
    print(f"\n=== {label} ===\n$ {' '.join(cmd)}")
    for attempt in range(retries + 1):
        try:
            subprocess.run(cmd, check=True, cwd=HERE)
            return
        except subprocess.CalledProcessError:
            if attempt >= retries:
                raise
            print(f"  (step crashed; retrying {attempt + 1}/{retries} — cached clips are reused)")


def ensure_clean_reference(force=False):
    """Build my_voice_clean.wav from my_voice.wav when it's missing or out of date."""
    raw = os.path.join(HERE, "my_voice.wav")
    clean = os.path.join(HERE, "my_voice_clean.wav")
    if not os.path.exists(raw):
        if os.path.exists(clean):
            return  # user supplied a clean reference directly; use it
        sys.exit("No my_voice.wav (or my_voice_clean.wav) found. Add a 10-20s recording of your voice.")
    stale = force or not os.path.exists(clean) or os.path.getmtime(clean) < os.path.getmtime(raw)
    if not stale:
        return
    if not shutil.which("ffmpeg"):
        print("ffmpeg not found; clone_voice.py will fall back to the raw my_voice.wav.")
        return
    run(["ffmpeg", "-y", "-i", raw, "-af", REF_FILTER,
         "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", clean],
        "Clean voice reference -> my_voice_clean.wav")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="narrate, then only write previews/ and stop")
    ap.add_argument("--draft", action="store_true", help="faster 720p render")
    ap.add_argument("--no-music", action="store_true", help="narration only, no background music")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--out", default="video.mp4")
    ap.add_argument("--skip-narration", action="store_true",
                    help="reuse the existing narration.wav / timeline.json")
    ap.add_argument("--force-ref", action="store_true", help="rebuild my_voice_clean.wav")
    ap.add_argument("--engine", choices=["f5", "chatterbox"], default="f5",
                    help="which voice cloner to narrate with (default: f5)")
    ap.add_argument("--no-audit", action="store_true",
                    help="skip the pronunciation/pacing audit of the script")
    args = ap.parse_args()

    outdir = project.output_dir(os.path.join(HERE, "script.txt"))
    rel = os.path.relpath(outdir, HERE)

    if not args.skip_narration:
        if not args.no_audit:
            run([PY, "audit_script.py", "--fix"], "Audit script (fix pronunciations, flag issues)")
        ensure_clean_reference(force=args.force_ref)
        narrator = "clone_f5.py" if args.engine == "f5" else "clone_voice.py"
        run([PY, narrator], f"Narrate script in your cloned voice ({args.engine})", retries=5)
    elif not os.path.exists(os.path.join(outdir, "timeline.json")):
        sys.exit(f"--skip-narration set but no timeline.json in {rel}/ yet. Run without it once first.")

    build = [PY, "build_video.py", "--fps", str(args.fps), "--out", args.out]
    if args.preview:
        build.append("--preview")
    if args.draft:
        build.append("--draft")
    if args.no_music:
        build.append("--no-music")
    run(build, "Render video")

    if args.preview:
        print(f"\nDone. Review {rel}/previews/overview.jpg, then run without --preview for the final video.")
    else:
        print(f"\nDone. Wrote {rel}/{args.out}, captions.srt and thumbnail.jpg.")


if __name__ == "__main__":
    main()
