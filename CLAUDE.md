# Project: script → cloned-voice narration → tutorial video

Owner: Ali Umair (senior software engineer, aliumair.dev). Goal: turn a written script into a
YouTube tutorial video narrated in his own cloned voice, with animated slides synced to the voice.
This toolkit was designed and tested in a Claude cloud session (on Linux), then moved to this Mac.

## Pipeline
1. `clone_voice.py`: reads `script.txt` (via `vscript.py`) and narrates each sentence with
   Chatterbox TTS (Resemble AI, MIT), using `my_voice.wav` as the voice reference. It writes
   `narration.wav` and `timeline.json` (slide and sentence start/end times). Sentences are cached in
   `.tts_cache/`, keyed by text, voice file and settings.
2. `build_video.py`: reads `timeline.json` and `narration.wav` and renders 1920x1080 frames with
   Pillow, piping them to ffmpeg. It generates a quiet music pad that ffmpeg ducks under the voice
   (sidechaincompress), then loudnorm to -14 LUFS. Outputs `video.mp4`, `captions.srt` and
   `thumbnail.jpg`. Use `--preview` to write `previews/overview.jpg`, `--draft` for 720p, and
   `--no-music` for narration only.
3. `script.txt` format is documented in README.md: `@kind Field | Field` slide lines, `# notes`,
   and `{shown|spoken}` for pronunciation (e.g. `{EC2|E C 2}`).

## This machine
- MacBook Pro M1 Pro (arm64), macOS. System Python is 3.15, which is TOO NEW: PyTorch has no 3.15 wheels.
  Use the Python 3.11 venv in this folder (`source venv/bin/activate` or `.venv`; check `python --version`).
- chatterbox-tts pins torch==2.6.0 (arm64 wheels exist). clone_voice.py patches `torch.load` to
  `map_location=cpu` and sets `PYTORCH_ENABLE_MPS_FALLBACK=1`, so the model loads on `mps`.
  If `mps` fails, it falls back to CPU.
- "unauthenticated requests to the HF Hub" is only a warning. Optionally `export HF_TOKEN=...`
  (the user's own token; never print it or write it to files).
- Needs ffmpeg (`brew install ffmpeg`) and `pip install pillow numpy pygments` in the venv.

## Tested vs untested
- Tested on Linux: vscript.py parsing, build_video.py (all 8 slide kinds, preview, full render,
  ffmpeg audio graph, music balance about 14 dB under speech).
- NOT tested anywhere: clone_voice.py end to end with Chatterbox. The cloud sandbox couldn't
  download the model, so the timeline was simulated with another TTS. Expect first-run issues here
  (model download, mps ops, torchaudio save/load backend). Fix them in place and keep behaviour the same.

## Working agreements
- Fix bugs in place, re-run, and confirm. Prefer small targeted edits over rewrites.
- Keep image previews small (960px wide) when inspecting frames, to save tokens.
- The script must only contain true claims about Ali. Don't invent certifications, numbers or clients.
  `script.txt` has two facts to confirm with Ali before publishing: the current AWS exam code
  (currently written as SAA-C03) and the real course length (currently "20 / twenty").
- Don't commit or upload `my_voice.wav`, `.tts_cache/` or tokens anywhere.

## Next steps (where we left off)
1. Run `python clone_voice.py` with the new script.txt to produce `narration.wav` and `timeline.json`.
2. Run `python build_video.py --preview` and review `previews/overview.jpg` with Ali.
3. Run `python build_video.py` for the final video. YouTube metadata and captions come from captions.srt.
