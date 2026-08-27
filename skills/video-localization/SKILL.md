---
name: video-localization
description: Localize Japanese-language videos into English end to end. Use for 動画文字起こし、日本語校正、英訳、同期字幕、英語吹替、Gemini TTS、動画ローカライズ、または字幕・音声トラック検証。
compatibility: Requires Python 3.11+, uv, ffmpeg/ffprobe, whisper-cli with a multilingual GGML model, network access for Gemini TTS, and GEMINI_API_KEY supplied outside the repository.
metadata:
  author: workspace-team
  version: "1.0.0"
---

# Video localization

Localize a Japanese presentation video into English subtitles and an English-dubbed MP4. Treat `$ARGUMENTS` as the source video path followed by any user-specified output directory, Whisper model, Gemini model, or voice.

## Non-negotiable safeguards

- Never overwrite, rename, truncate, or modify the source video. Put every generated artifact in a separate output directory.
- Keep video and audio local. The only content permitted to leave the machine is the finalized English narration text sent by `scripts/gemini_tts.py`.
- Before the first non-dry-run Gemini call, tell the user that English text will be sent and obtain confirmation unless the current request already explicitly authorizes Gemini TTS.
- Read `GEMINI_API_KEY` only from the environment. Never show its value or place it in files, command arguments, manifests, or logs.
- Keep raw cue IDs, cue order, timestamps, and raw Japanese immutable through correction and translation.
- Pin Python API dependencies. Use the PEP 723 declaration in `gemini_tts.py` via `uv run`; do not install into the global Python environment.
- Stop on validation failures. Do not claim completion based only on a command's exit code.

## Required workflow

1. **Resolve inputs.** If no unambiguous source path was supplied, ask for it. Choose a new output directory such as `localized/<source-stem>/`. Locate a multilingual GGML Whisper model; reject `.en`-only models.
2. **Preflight.** Run `scripts/preflight.py` with the source and model. Verify ffmpeg, ffprobe, whisper-cli, uv, media streams, model, and API-key presence without exposing the key. Preserve the JSON report.
3. **Transcribe locally.** Run `scripts/transcribe.py`. This extracts mono PCM locally and invokes whisper-cli for Japanese SRT, text, and JSON. Preserve its manifest.
4. **Create cue-locked data.** Run `scripts/segments.py init`. Proofread Japanese and translate English by editing only `corrected_ja` and `en` in the JSON. Follow `references/transcript-schema.md`, `references/editorial-policy.md`, and `references/subtitle-policy.md`.
5. **Validate and render.** Run `scripts/segments.py validate`, then `render` to create corrected Japanese and English SRT. Also create readable corrected-Japanese and English Markdown. Recheck names, acronyms, numbers, dates, negation, and uncertain words against context.
6. **Prepare narration sections.** In English Markdown, use `## [HH:MM:SS] Title` at coherent slide or topic boundaries, beginning at `00:00:00`. Keep every translated idea in order; headings are not spoken.
7. **Plan TTS.** Run `uv run scripts/gemini_tts.py ... --dry-run`. Confirm all sections, ordering, and final media duration without calling Gemini.
8. **Generate TTS.** Run without `--dry-run` after authorization. Reuse section caches on restart. The script keeps natural speech speed by expanding internal pauses when short and permits only bounded pitch-preserving speed-up when long. Follow `references/gemini-tts.md`.
9. **Mux.** Run `scripts/mux_media.py`. Stream-copy the original video, make English Gemini TTS the default audio, retain original Japanese as secondary audio, and embed default English mov_text subtitles.
10. **Validate.** Run `scripts/validate_output.py` and complete `references/qa-checklist.md`. Require stream/tag correctness, duration tolerance, source/output video-bitstream hash equality, exact parsed subtitle equality, and successful decoding of both audio tracks.

See `references/workflow.md` for complete command forms and recovery behavior. `assets/config.example.json` contains non-secret default examples only; never add an API key to it.

## Completion report

Report the source path and unchanged status, output paths, cue and section counts, media duration, stream layout, subtitle equality, video hash equality, audio decode result, TTS model/voice, and any human checks that remain. State explicitly that no video or audio was uploaded and that Gemini received English text only. If a criterion was not verified, identify it instead of calling the task complete.
