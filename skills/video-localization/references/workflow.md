# End-to-end workflow

Run commands from the workspace root. Set paths explicitly; never assume the current video name.

## 1. Prepare isolated output

Use a new directory such as `localized/<source-stem>/`. Never modify, rename, or replace the source video. Preserve command reports and manifests in the output directory.

```sh
SKILL=.kiro/skills/video-localization
python3 "$SKILL/scripts/preflight.py" INPUT.mp4 \
  --whisper-model /absolute/path/to/multilingual-model.bin \
  --require-tts --output-json localized/NAME/preflight.json
```

Stop on preflight errors. An English-only Whisper model is invalid for Japanese.

## 2. Transcribe locally

```sh
python3 "$SKILL/scripts/transcribe.py" INPUT.mp4 \
  --output-dir localized/NAME \
  --model /absolute/path/to/multilingual-model.bin
```

`whisper-cli` and ffmpeg run locally. Do not upload the source media or extracted audio.

## 3. Proofread and translate

Initialize the cue-locked JSON document:

```sh
python3 "$SKILL/scripts/segments.py" init \
  localized/NAME/NAME.raw.srt localized/NAME/NAME.segments.json
```

Edit only `corrected_ja` and `en`. Keep every `index`, `start`, `end`, and `raw_ja` unchanged. Follow `editorial-policy.md`, `subtitle-policy.md`, and `transcript-schema.md`. Then validate and render:

```sh
python3 "$SKILL/scripts/segments.py" validate \
  localized/NAME/NAME.raw.srt localized/NAME/NAME.segments.json
python3 "$SKILL/scripts/segments.py" render \
  localized/NAME/NAME.raw.srt localized/NAME/NAME.segments.json \
  --output-dir localized/NAME --stem NAME
```

Also produce readable `NAME.corrected_ja.md` and `NAME.en.md`. The English Markdown used for TTS must group narration into coherent sections using headings exactly like `## [00:03:18] Access reviews`. The first section must start at `00:00:00`. A title is metadata and is not spoken; each section body contains the complete narration for that interval.

## 4. Generate English speech

First plan without an API call:

```sh
uv run "$SKILL/scripts/gemini_tts.py" localized/NAME/NAME.en.md \
  --media INPUT.mp4 --output localized/NAME/NAME.english_voice.wav \
  --work-dir localized/NAME/tts-work --dry-run
```

Review section boundaries and lengths. After confirming that Gemini may receive the English text, run the same command without `--dry-run`. The API key must exist only in `GEMINI_API_KEY`; never place it in a command argument, source file, config, manifest, or log.

TTS runs section by section. Matching cache records are resumed. Short sections retain natural speech speed and distribute missing time across internal pauses. Overlong speech is accelerated only up to `--max-speedup` (default 1.15); beyond that the script stops so the English can be shortened or regenerated.

## 5. Mux tracks

```sh
python3 "$SKILL/scripts/mux_media.py" \
  --source INPUT.mp4 \
  --english-audio localized/NAME/NAME.english_voice.wav \
  --english-srt localized/NAME/NAME.en.srt \
  --output localized/NAME/NAME.english_dub.mp4
```

The video is stream-copied. English audio is the default, original Japanese is retained as the second audio track, and English subtitles are embedded and default.

## 6. Validate before reporting success

```sh
python3 "$SKILL/scripts/validate_output.py" \
  --source INPUT.mp4 \
  --output localized/NAME/NAME.english_dub.mp4 \
  --english-srt localized/NAME/NAME.en.srt \
  --output-json localized/NAME/validation.json
```

Do not report completion unless `ok` is true. Run the human checks in `qa-checklist.md` as well. Use `--force` only after confirming which generated artifact will be replaced; it must never target the source video.
