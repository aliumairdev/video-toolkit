# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Ali Umair — https://aliumair.dev
# Part of video-toolkit. See LICENSE for the full GNU AGPL v3 terms.
"""Shared: derive a project name and output folder from the script.

The project name is the first `#` comment line in the script (e.g.
`# AWS Solutions Architect - Associate - course intro`). Falls back to the
script's filename. Everything a run produces goes in output/<project name>/.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _safe(name):
    # folder-safe but keep spaces/dashes/unicode so it reads naturally
    name = name.replace("/", "-").replace("\\", "-").strip().strip(".")
    return name[:120]


def project_name(script_path):
    try:
        with open(script_path, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                if s.startswith("#"):
                    name = s.lstrip("#").strip()
                    if name:
                        return _safe(name)
                if s.startswith("@"):
                    break   # slides began before any title comment
    except OSError:
        pass
    base = os.path.splitext(os.path.basename(script_path))[0]
    return _safe(base) or "output"


def output_dir(script_path, create=True):
    d = os.path.join(HERE, "output", project_name(script_path))
    if create:
        os.makedirs(d, exist_ok=True)
    return d
