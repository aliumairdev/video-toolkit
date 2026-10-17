# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""
Audit a script for the things that make TTS mispronounce or rush, BEFORE you spend a render on it.

It uses lexicon.json (a persistent pronunciation dictionary the pipeline "learns"):
  - Known terms (AWS, EC2, IT, your name, ...) are wrapped as {shown|spoken} so the voice says
    them right while slides still show the normal spelling.
  - Unknown acronyms / codes (e.g. VPC, SAA-C99) are reported so you can add them to lexicon.json
    once -- then every future build fixes them automatically.
  - Over-long sentences are flagged, because F5 tends to rush (and garble) them.

Usage:
  python audit_script.py                 # report issues, change nothing
  python audit_script.py --fix           # apply known fixes to the script in place
  python audit_script.py --script x.txt  # audit a different script

Only spoken lines are touched; @slide and #comment lines are left alone.
"""
import argparse
import json
import os
import re

import vscript

HERE = os.path.dirname(os.path.abspath(__file__))
LEXICON = os.path.join(HERE, "lexicon.json")

BRACE = re.compile(r"\{[^{}]*\}")
WRAP = re.compile(r"\{([^{}|]+)\|([^{}]+)\}")
# candidate "needs a pronunciation" tokens: 2+ caps (AWS), letters+digits (EC2, S3), or a code (SAA-C03)
ACRONYM = re.compile(r"[A-Z]{2,}")
ALNUM = re.compile(r"[A-Za-z]*[0-9]+[A-Za-z0-9]*")
CODE = re.compile(r"[A-Z0-9]+-[A-Z0-9]+")


def is_spoken(line):
    s = line.strip()
    return bool(s) and not s.startswith("#") and not s.startswith("@")


def resync_wraps(text, pron):
    """Update existing {shown|spoken} wraps whose spoken value no longer matches the lexicon,
    so changing lexicon.json re-flows into every script."""
    changed = {}

    def repl(m):
        shown, spoken = m.group(1), m.group(2)
        if shown in pron and spoken != pron[shown]:
            changed[shown] = changed.get(shown, 0) + 1
            return "{" + shown + "|" + pron[shown] + "}"
        return m.group(0)

    return WRAP.sub(repl, text), changed


def apply_pron(text, pron):
    """Wrap known terms as {shown|spoken}, skipping anything already inside braces."""
    parts = BRACE.split(text)
    guards = BRACE.findall(text)
    changed = {}
    out = []
    for i, seg in enumerate(parts):
        for key in sorted(pron, key=len, reverse=True):
            pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])")
            seg, n = pat.subn("{" + key + "|" + pron[key] + "}", seg)
            if n:
                changed[key] = changed.get(key, 0) + n
        out.append(seg)
        if i < len(guards):
            out.append(guards[i])
    return "".join(out), changed


def find_unknown(text, pron):
    stripped = BRACE.sub(" ", text)                 # ignore already-wrapped terms
    found = set()
    for m in re.finditer(r"[A-Za-z0-9][A-Za-z0-9.\-]*", stripped):
        tok = m.group().strip(".-")
        if not tok or tok in pron:
            continue
        if ACRONYM.fullmatch(tok) or ALNUM.fullmatch(tok) or CODE.fullmatch(tok):
            found.add(tok)
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", default="script.txt")
    ap.add_argument("--fix", action="store_true", help="apply known pronunciations to the script in place")
    args = ap.parse_args()

    path = args.script if os.path.isabs(args.script) else os.path.join(HERE, args.script)
    with open(LEXICON, encoding="utf-8") as fh:
        lex = json.load(fh)
    pron = lex["pronunciations"]
    maxw = lex.get("max_sentence_words", 32)

    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    total_changed, unknown, long_sents = {}, set(), []
    new_lines = []
    for ln, line in enumerate(lines, 1):
        if not is_spoken(line):
            new_lines.append(line)
            continue
        resynced, rchanged = resync_wraps(line, pron)   # update stale wraps to current lexicon
        fixed, changed = apply_pron(resynced, pron)      # wrap any new unwrapped terms
        new_lines.append(fixed)
        for d in (rchanged, changed):
            for k, c in d.items():
                total_changed[k] = total_changed.get(k, 0) + c
        unknown |= find_unknown(fixed, pron)
        for sent in re.split(r"(?<=[.!?])\s+", vscript.spoken(line).strip()):
            w = len(sent.split())
            if w > maxw:
                long_sents.append((ln, w, sent.strip()))

    # ---- report ----
    print(f"Audit of {os.path.relpath(path, HERE)}:")
    if total_changed:
        summary = ", ".join(f"{k}x{v}" for k, v in sorted(total_changed.items()))
        verb = "Applied" if args.fix else "Would apply"
        print(f"  {verb} {sum(total_changed.values())} known fix(es): {summary}")
    else:
        print("  No known terms needed wrapping (already fixed, or none present).")
    if unknown:
        print(f"  ! {len(unknown)} unknown acronym/code(s) the voice may mispronounce: "
              f"{', '.join(sorted(unknown))}")
        print("    -> add each to lexicon.json with how it should sound, then re-run. "
              "(If it's already said as a word, leave it out.)")
    if long_sents:
        print(f"  ! {len(long_sents)} long sentence(s) (> {maxw} words) may rush/garble:")
        for ln, w, s in long_sents:
            print(f"      line {ln} ({w} words): {s[:80]}{'...' if len(s) > 80 else ''}")
        print("    -> consider splitting into shorter sentences.")

    if args.fix:
        if total_changed:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(new_lines)
            print("  Script updated in place.")
        else:
            print("  Nothing to change.")
    elif total_changed or unknown:
        print("  Run with --fix to apply the known fixes.")


if __name__ == "__main__":
    main()
