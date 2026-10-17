# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
Narrate script.txt in your voice with F5-TTS, writing the same outputs build_video.py expects:
  narration.wav    full narration (16-bit so it plays everywhere)
  timeline.json    slide + sentence start/end times

Runs in the F5 environment:
  source venv_f5/bin/activate
  python clone_f5.py

Per-sentence clips are cached in .f5_cache/ (keyed by text + reference + settings), so edits
only regenerate changed lines. Delete .f5_cache/ to force a full re-render.
"""
import argparse
import hashlib
import json
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
# macOS stability: the tokenizers lib forks after threading, which crashes a multiprocessing
# helper (SIGABRT, "PYTHONHASHSEED must be ..."). These prevent that.
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["PYTHONHASHSEED"] = "0"
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
import numpy as np
import soundfile as sf

import project
import vscript

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "script.txt")
CACHE_DIR = os.path.join(HERE, ".f5_cache")   # shared across projects (keyed by sentence text)

REF = "my_voice_clean.wav"      # falls back to my_voice.wav
# Transcript of the reference clip (F5 needs it). This is what Whisper heard; it only has to
# roughly match the audio. Leave as "" to auto-transcribe (downloads a Whisper model).
REF_TEXT = ("Hi, I'm Ali Omer and welcome to today we are going to learn how the cloud really "
            "works. Step by step, don't worry if it feels complex at first. With a little "
            "practice, it get much easier.")

SR = 24000                      # F5 (vocos-mel-24khz) output rate
SPEED = 0.9                     # pacing: <1 slower, >1 faster. <1 gives F5 more time per line,
                                #   which stops it rushing/garbling mid-sentence.
NFE = 32                        # sampling steps. 32 is reliable on the M1; 48 hangs on long lines.
PAUSE_SECONDS = 0.30            # silence between sentences
HOLD_SECONDS = 2.5             # how long a slide with no spoken text stays up
TRIM_DB = -40.0                 # strip each clip's own leading/trailing silence


def ref_path():
    p = os.path.join(HERE, REF)
    if not os.path.exists(p) and os.path.exists(os.path.join(HERE, "my_voice.wav")):
        return os.path.join(HERE, "my_voice.wav")
    return p


def trim_silence(wav, thresh_db=TRIM_DB, keep_ms=60):
    amp = np.abs(wav)
    peak = amp.max()
    if peak == 0:
        return wav
    thr = peak * (10 ** (thresh_db / 20.0))
    idx = np.where(amp > thr)[0]
    if len(idx) == 0:
        return wav
    m = int(SR * keep_ms / 1000)
    return wav[max(0, idx[0] - m):min(len(wav), idx[-1] + m)]


def cache_path(text, ref_sig):
    key = f"{text}|f5|{REF}|{ref_sig}|{SPEED}|{NFE}"
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".wav")


# ---- lazy F5 loader: only pay the model-load cost if something needs generating ----
_state = {}
def get_f5():
    if "model" not in _state:
        from f5_tts.api import F5TTS
        from f5_tts.infer.utils_infer import preprocess_ref_audio_text
        _state["model"] = F5TTS(model="F5TTS_v1_Base")
        ref_proc, ref_text = preprocess_ref_audio_text(ref_path(), REF_TEXT)
        _state["ref_proc"], _state["ref_text"] = ref_proc, ref_text
        print(f"Loaded F5. Reference text: {ref_text!r}")
    return _state["model"]


def synth(text, ref_sig):
    cp = cache_path(text, ref_sig)
    if os.path.exists(cp):
        wav, _ = sf.read(cp, dtype="float32")
        return wav
    model = get_f5()
    wav, sr, _ = model.infer(ref_file=_state["ref_proc"], ref_text=_state["ref_text"],
                             gen_text=text, speed=SPEED, nfe_step=NFE, remove_silence=False)
    wav = trim_silence(np.asarray(wav, dtype=np.float32))
    sf.write(cp, wav, SR, subtype="PCM_16")
    return wav


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--speed", type=float, help="override pacing for this run")
    args = ap.parse_args()
    if args.speed is not None:
        global SPEED
        SPEED = args.speed

    os.makedirs(CACHE_DIR, exist_ok=True)
    rp = ref_path()
    ref_sig = f"{os.path.getmtime(rp):.0f}:{os.path.getsize(rp)}"

    slides = vscript.parse_script(SCRIPT)
    n = sum(len(s["sentences"]) for s in slides)
    to_gen = sum(not os.path.exists(cache_path(s["spoken"], ref_sig))
                 for sl in slides for s in sl["sentences"])
    print(f"{len(slides)} slides, {n} sentences ({to_gen} to generate, {n - to_gen} from cache).")

    pause = np.zeros(int(SR * PAUSE_SECONDS), np.float32)
    parts, out_slides, cursor, done = [], [], 0.0, 0
    for slide in slides:
        slide_start = cursor
        sents = []
        if not slide["sentences"]:
            parts.append(np.zeros(int(SR * HOLD_SECONDS), np.float32))
            cursor += HOLD_SECONDS
        else:
            for sent in slide["sentences"]:
                done += 1
                print(f"[{done}/{n}] {sent['spoken']}")
                wav = synth(sent["spoken"], ref_sig)
                dur = len(wav) / SR
                sents.append({"text": sent["shown"], "start": round(cursor, 3),
                              "end": round(cursor + dur, 3)})
                parts += [wav, pause]
                cursor += dur + PAUSE_SECONDS
        out_slides.append({"directive": slide["directive"], "start": round(slide_start, 3),
                           "sentences": sents})

    outdir = project.output_dir(SCRIPT)
    rel = os.path.relpath(outdir, HERE)
    audio = np.clip(np.concatenate(parts), -1.0, 1.0)
    sf.write(os.path.join(outdir, "narration.wav"), audio, SR, subtype="PCM_16")
    with open(os.path.join(outdir, "timeline.json"), "w", encoding="utf-8") as fh:
        json.dump({"duration": round(len(audio) / SR, 3), "slides": out_slides}, fh, indent=2)
    print(f"Saved narration.wav ({len(audio) / SR:.1f}s) and timeline.json in {rel}/")


if __name__ == "__main__":
    main()
