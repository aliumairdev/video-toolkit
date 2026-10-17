# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""Shared script parser for clone_voice.py and build_video.py.

script.txt format
  # note                       -> ignored
  @kind Field | Field | ...    -> starts a new slide (see README for slide kinds)
  plain text                   -> spoken over the current slide
  {shown|spoken}               -> captions/slides show the left side, the voice says the right side
"""
import re
import sys

PAIR = re.compile(r"\{([^{}|]+)\|([^{}]+)\}")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def spoken(s):
    return PAIR.sub(lambda m: m.group(2), s)


def shown(s):
    return PAIR.sub(lambda m: m.group(1), s)


def parse_script(path):
    raw_slides, cur = [], None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("@"):
                cur = {"directive": line[1:].strip(), "text": []}
                raw_slides.append(cur)
                continue
            if cur is None:
                cur = {"directive": "", "text": []}
                raw_slides.append(cur)
            cur["text"].append(line)

    slides = []
    for s in raw_slides:
        text = " ".join(s["text"])
        if "<<FILL" in text or "<<FILL" in s["directive"]:
            sys.exit("script.txt still has <<FILL ...>> placeholders. Fill them in first.")
        parts = [p.strip() for p in SENTENCE_END.split(text) if p.strip()]
        slides.append({
            "directive": shown(s["directive"]),
            "sentences": [{"spoken": spoken(p), "shown": shown(p)} for p in parts],
        })
    if not slides:
        sys.exit("script.txt has no content.")
    return slides
