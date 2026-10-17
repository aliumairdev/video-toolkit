# Contributing

Thanks for improving video-toolkit! A few things to know before you send changes.

## License of contributions

This project is licensed under the **GNU Affero General Public License v3.0** (see [LICENSE](LICENSE)).

By submitting a contribution (a pull request, patch, or any change), **you agree that your
contribution is licensed under AGPL-3.0**, the same license as the project (inbound = outbound).
You confirm you have the right to contribute it. This is how improvements flow back to the
project and stay open for everyone.

If you redistribute a modified version of video-toolkit — including running it as a network
service — AGPL-3.0 requires you to make your modified source available under the same license.

## How to contribute

1. Open an issue first for anything non-trivial, so we can agree on the approach.
2. Fork, branch, and make focused changes that match the existing style.
3. Keep the pipeline working: run `python make_video.py --preview` (or `--draft`) and confirm it
   still builds.
4. If you add or change how a term is pronounced, update `lexicon.json` — that's the shared
   pronunciation dictionary the whole pipeline learns from.
5. Open a pull request describing what changed and why.

## Good first contributions

- New slide kinds in `build_video.py`.
- More entries in `lexicon.json` (acronyms / terms the TTS says wrong).
- Support for other voice-cloning engines behind the `make_video.py --engine` switch.
- Docs and setup fixes.
