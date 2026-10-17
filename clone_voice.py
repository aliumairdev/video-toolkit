# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
Narrate a script in your own voice with Chatterbox (MIT license, by Resemble AI).

Reads script.txt (parsed by vscript.py, so slides and {shown|spoken} pronunciation work),
synthesizes each sentence with your cloned voice, and writes:
  narration.wav    the full narration (send this to build_video.py)
  timeline.json    slide + sentence start/end times, so the video stays in sync

Folder setup:
  my_voice_clean.wav   normalized, de-silenced reference (see README; falls back to my_voice.wav)
  script.txt           the text to narrate
  clone_voice.py       this file

Run:
  python clone_voice.py

Note: Chatterbox adds an inaudible watermark to generated audio (responsible-AI feature).
"""
import hashlib
import json
import os
import sys

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")   # Apple Silicon: run unsupported ops on CPU
import torch

if not torch.cuda.is_available():
    # Model files were saved on NVIDIA GPUs; load them to CPU first, then move to the Mac GPU.
    _orig_load = torch.load
    def _load_cpu(*args, **kwargs):
        kwargs.setdefault("map_location", torch.device("cpu"))
        return _orig_load(*args, **kwargs)
    torch.load = _load_cpu

import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

import project
import vscript

HERE = os.path.dirname(os.path.abspath(__file__))
REF = "my_voice_clean.wav"  # normalized, de-silenced reference (see README). Falls back to my_voice.wav.
SCRIPT = "script.txt"
OUT = "narration.wav"
TIMELINE = "timeline.json"
CACHE_DIR = ".tts_cache"
PAUSE_SECONDS = 0.30      # silence between sentences (added after trimming each clip's own silence)
HOLD_SECONDS = 2.5        # how long a slide with no spoken text stays on screen
EXAGGERATION = 0.4        # 0.3 = calmer/closer to reference, 0.7 = more expressive
CFG_WEIGHT = 0.3          # lower (~0.3) = slower, more deliberate pacing; 0.5 sounds rushed
TEMPERATURE = 0.8         # lower (~0.6) sticks closer to your voice/accent; higher varies more
TRIM_SILENCE_DB = -40.0   # strip leading/trailing silence from each clip so gaps are consistent
# Tip: run `python voice_test.py` to A/B these three before a full render.

if not os.path.exists(os.path.join(HERE, REF)) and os.path.exists(os.path.join(HERE, "my_voice.wav")):
    print(f"{REF} not found; using my_voice.wav (run the ffmpeg cleanup in README for best results).")
    REF = "my_voice.wav"

# ---- read and parse the script (slides + sentences, honouring {shown|spoken}) ----
slides = vscript.parse_script(os.path.join(HERE, SCRIPT))
n_sentences = sum(len(s["sentences"]) for s in slides)

# ---- per-sentence cache so re-runs only generate changed lines ----
SR = 24000   # Chatterbox always outputs 24 kHz; cached clips are saved at this rate
ref_path = os.path.join(HERE, REF)
ref_sig = f"{os.path.getmtime(ref_path):.0f}:{os.path.getsize(ref_path)}"
cache_dir = os.path.join(HERE, CACHE_DIR)
os.makedirs(cache_dir, exist_ok=True)

def cache_path(text):
    key = f"{text}|{REF}|{ref_sig}|{EXAGGERATION}|{CFG_WEIGHT}|{TEMPERATURE}"
    return os.path.join(cache_dir, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".wav")


# ---- load the model only when something actually needs generating ----
# (first load downloads it from Hugging Face, a few GB; cached-only runs skip this entirely)
_model = {}
def get_model():
    if "m" not in _model:
        device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
        try:
            _model["m"] = ChatterboxTTS.from_pretrained(device=device)
        except Exception as e:               # some Macs fail on "mps"; fall back to CPU
            print(f"Could not load on {device} ({e}); falling back to CPU.")
            _model["m"] = ChatterboxTTS.from_pretrained(device="cpu")
        print(f"Loaded Chatterbox on {device}.")
    return _model["m"]


def trim_silence(wav, thresh_db=TRIM_SILENCE_DB, keep_ms=60):
    """Strip near-silence from the start/end of a clip so sentence gaps stay uniform.
    Chatterbox often pads each clip with its own silence, which stacks with PAUSE_SECONDS."""
    amp = wav.abs().max(dim=0).values                       # (N,) peak per sample
    thresh = amp.max() * (10 ** (thresh_db / 20.0))
    loud = (amp > thresh).nonzero()
    if loud.numel() == 0:
        return wav                                          # all quiet: leave as-is
    margin = int(SR * keep_ms / 1000)
    start = max(0, int(loud[0]) - margin)
    end = min(wav.shape[1], int(loud[-1]) + margin)
    return wav[:, start:end]


def synth(text):
    """Generate (or load from cache) a trimmed clip for one sentence."""
    cp = cache_path(text)
    if os.path.exists(cp):
        wav, _ = ta.load(cp)
        return wav
    wav = get_model().generate(text, audio_prompt_path=ref_path,
                               exaggeration=EXAGGERATION, cfg_weight=CFG_WEIGHT,
                               temperature=TEMPERATURE)
    wav = trim_silence(wav.cpu())
    ta.save(cp, wav, SR)
    return wav


to_generate = sum(not os.path.exists(cache_path(s["spoken"])) for sl in slides for s in sl["sentences"])
print(f"{len(slides)} slides, {n_sentences} sentences "
      f"({to_generate} to generate, {n_sentences - to_generate} from cache).")


# ---- generate slide by slide, tracking time to build the timeline ----
pause = torch.zeros(1, int(SR * PAUSE_SECONDS))
parts = []
cursor = 0.0                                                # seconds written so far
out_slides = []
done = 0
for slide in slides:
    slide_start = cursor
    sent_entries = []
    if not slide["sentences"]:
        parts.append(torch.zeros(1, int(SR * HOLD_SECONDS)))  # silent hold so the slide has duration
        cursor += HOLD_SECONDS
    else:
        for sent in slide["sentences"]:
            done += 1
            print(f"[{done}/{n_sentences}] {sent['spoken']}")
            wav = synth(sent["spoken"])
            dur = wav.shape[1] / SR
            sent_entries.append({"text": sent["shown"],
                                 "start": round(cursor, 3),
                                 "end": round(cursor + dur, 3)})
            parts += [wav, pause]
            cursor += dur + PAUSE_SECONDS
    out_slides.append({"directive": slide["directive"],
                       "start": round(slide_start, 3),
                       "sentences": sent_entries})

audio = torch.cat(parts, dim=1).clamp(-1.0, 1.0)
# Save as 16-bit PCM so the WAV plays in every player (32-bit float WAV is silent in QuickTime).
outdir = project.output_dir(os.path.join(HERE, SCRIPT))
rel = os.path.relpath(outdir, HERE)
ta.save(os.path.join(outdir, OUT), audio, SR, encoding="PCM_S", bits_per_sample=16)
with open(os.path.join(outdir, TIMELINE), "w", encoding="utf-8") as fh:
    json.dump({"duration": round(audio.shape[1] / SR, 3), "slides": out_slides}, fh, indent=2)
print(f"Saved {OUT} ({audio.shape[1] / SR:.1f}s) and {TIMELINE} in {rel}/")
