# Tutorial video toolkit

Write a script → narrate it in your cloned voice → get a finished YouTube video
(animated slides timed to your voice, background music, captions and a thumbnail).

```
script.txt ──► clone_voice.py ──► narration.wav + timeline.json ──► build_video.py ──► video.mp4
                  (your voice)                                          captions.srt, thumbnail.jpg
```

## One-time setup (Apple Silicon Mac)

```bash
brew install ffmpeg
cd ~/voiceclone                      # this folder
python3.11 -m venv venv              # system Python 3.15 has no PyTorch wheels — use 3.11
source venv/bin/activate
pip install -r requirements.txt
```

Models (~2 GB) download automatically from Hugging Face on the first `clone_voice.py` run.

**Optional — alternative voice cloner (F5-TTS).** If Chatterbox doesn't match your voice,
F5-TTS often does better. It needs its **own** venv (different torch version):

```bash
python3.11 -m venv venv_f5
source venv_f5/bin/activate
pip install -r requirements-f5.txt
python f5_test.py                    # compare F5 clips against your real voice
```

Put a 10–20 s clean recording of your voice in this folder as **my_voice.wav**.

**Clean the reference before cloning (important).** The clone only sounds like you if the
reference is loud enough and free of long gaps. A quiet recording (e.g. −40 LUFS) or one with
dead air produces a weak, un-you-sounding voice with gaps. Normalize and de-silence it once:

```bash
ffmpeg -y -i my_voice.wav \
  -af "highpass=f=80,afftdn=nr=12:nf=-25,\
silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:\
stop_periods=-1:stop_silence=0.3:stop_threshold=-40dB:detection=peak,\
loudnorm=I=-19:TP=-2:LRA=11" \
  -ar 24000 -ac 1 -c:a pcm_s16le my_voice_clean.wav
```

`clone_voice.py` uses `my_voice_clean.wav` automatically (and falls back to `my_voice.wav`).
Target the output at roughly −20 LUFS integrated with peaks near −2 dB.

## Make a video

One command runs the whole pipeline (clean reference → narrate → render):

```bash
source .venv/bin/activate
python make_video.py             # narration.wav + timeline.json, then video.mp4, captions.srt, thumbnail.jpg
```

Useful flags (all forwarded to the right step):

```bash
python make_video.py --preview        # narrate, then only write previews/ and stop (check this first)
python make_video.py --draft          # faster 720p render for checking timing
python make_video.py --no-music       # narration only
python make_video.py --skip-narration # reuse the existing narration.wav / timeline.json, just re-render
```

Or run the steps by hand if you prefer:

```bash
python clone_voice.py            # 1. narration.wav + timeline.json
python build_video.py --preview  # 2. check previews/overview.jpg
python build_video.py            # 3. video.mp4, captions.srt, thumbnail.jpg
```

- Edited the script? Run `clone_voice.py` again. Unchanged sentences are reused from `.tts_cache/`, so only new lines are generated.
- New voice recording? Delete `.tts_cache/` first.
- `python build_video.py --draft` renders faster at 720p for checking timing.
- `python build_video.py --no-music` gives narration only.

## Writing script.txt

Each slide starts with an `@` line. The text under it is spoken while that slide is on screen.

| Slide | Format | Notes |
|---|---|---|
| Title | `@title Heading \| Subtitle \| small label` | |
| Bullets | `@bullets Heading \| point \| point \| point` | points appear one by one as you speak |
| Statement | `@big Big statement \| small caption` | |
| Tiles | `@grid Heading \| tile \| tile \| ...` | up to ~12 short labels |
| Comparison | `@compare Heading \| Left: a; b; c \| Right: a; b; c` | |
| Code | `@code Heading \| examples/app.rb` | syntax colours; lines type in |
| Image | `@image screenshots/dashboard.png \| caption` | |
| Screen recording | `@video clips/console.mp4 \| caption` | plays the clip while you narrate over it |
| Outro | `@end Heading \| line \| line` | shows your URL |

- `# lines` are notes: they're not spoken and not shown.
- `{shown|spoken}` puts one thing on screen and has the voice say another: `{EC2|E C 2}`, `{aliumair.dev|ali umair dot dev}`.
- A slide with no text under it stays on screen for 2.5 seconds.
- Bullets appear with the sentences. Writing one sentence per point gives the best sync.
- `@video clips/console.mp4` plays a screen recording while your narration (the text under the slide) talks over it. The clip's own audio is ignored. The slide lasts as long as your narration: if the clip is shorter it freezes on the last frame; if longer, only the first part plays. Frames are extracted once and cached in `.video_cache/`.

## Settings

- **Brand and colours:** top of `build_video.py` (`BRAND`, `URL`, `COURSE`, colours, `MUSIC_VOLUME`).
- **Voice:** top of `clone_voice.py`. `EXAGGERATION` 0.3 is calmer/closer to the reference and 0.7 more expressive. A lower `CFG_WEIGHT` (about 0.3) gives slower, less rushed pacing. `PAUSE_SECONDS` is the gap between sentences; each clip's own leading/trailing silence is trimmed first so the gaps stay uniform.

Fonts: Inter and JetBrains Mono (SIL Open Font License, see `fonts/`).
Voice model: Chatterbox by Resemble AI (MIT). It adds an inaudible watermark to the generated audio.
