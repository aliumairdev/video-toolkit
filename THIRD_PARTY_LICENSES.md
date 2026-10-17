# Third-party components

video-toolkit itself is licensed under **AGPL-3.0** (see [LICENSE](LICENSE)), © 2026 Ali Umair.
That license covers the code in this repository. The components below are **not** owned by this
project and keep their own licenses — you must comply with each when you use video-toolkit.

## ⚠️ Important: model-weight terms (read before any commercial use)

The TTS **model weights are downloaded at runtime from Hugging Face and are NOT in this repo.**
AGPL-3.0 applies to this project's code, not to these models.

| Model | Repo | Note |
|---|---|---|
| F5-TTS (`F5TTS_v1_Base`) | `SWivid/F5-TTS` | Code is MIT, but the released weights were trained on the **Emilia** dataset, which is **CC BY-NC 4.0 (non-commercial)**. Verify the current terms on the model card before using the output commercially. |
| Chatterbox | `ResembleAI/chatterbox` | MIT. Adds an inaudible watermark to generated audio. |
| Vocos vocoder | `charactr/vocos-mel-24khz` | MIT. |
| Whisper (ref transcription) | `openai/whisper-large-v3-turbo` | MIT. Used once to transcribe your reference clip. |

**Bottom line:** the toolkit is AGPL and free to use; whether a *finished video* can be sold
depends on the model weights you generated it with. Check the model cards.

## Python dependencies (installed via pip, not redistributed here)

| Package | License |
|---|---|
| chatterbox-tts | MIT (Resemble AI) |
| f5-tts | MIT (F5-TTS authors) |
| torch, torchaudio | BSD-3-Clause (Meta) |
| transformers, tokenizers | Apache-2.0 (Hugging Face) |
| pillow | MIT-CMU / HPND |
| numpy, scipy, soundfile | BSD-3-Clause |
| pygments | BSD-2-Clause |

See each package's own distribution for full license text.

## Bundled assets (in this repo)

| Asset | License |
|---|---|
| Inter (fonts/) | SIL Open Font License 1.1 — © Rasmus Andersson |
| JetBrains Mono (fonts/) | SIL Open Font License 1.1 — © JetBrains |

The OFL permits bundling and redistribution; the license text ships with the fonts in `fonts/`.
