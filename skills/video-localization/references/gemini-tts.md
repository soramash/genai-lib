# Gemini TTS rules

## Privacy boundary

The local video, extracted audio, screenshots, Japanese transcript, and secrets must not be sent to Gemini. `gemini_tts.py` sends only an English instruction prompt and the English narration body for one section. Confirm user authorization before the first non-dry-run API call.

Use `GEMINI_API_KEY` from the process environment. Never print its value, pass it as a CLI argument, save it in a config file, or include it in a manifest. API failures are logged by exception type only.

## Reproducibility

The script uses PEP 723 metadata with `google-genai==2.19.0`; invoke it with `uv run`. Defaults are:

- Model: `gemini-3.1-flash-tts-preview`
- Voice: `Kore`
- Output: 24 kHz, mono, 16-bit PCM WAV
- Maximum automatic speed-up: 1.15x

Override model or voice explicitly when required and record the values in the manifest.

## Caching and fitting

Each section has a cache key derived from model, voice, and English text. A matching raw WAV is reused; changed text, model, or voice causes regeneration. `--force` regenerates every section and replaces the final output.

When speech is shorter than its interval, the script detects internal quiet regions and distributes the exact missing sample count among them. It does not slow speech. If no qualifying silence exists, the quietest internal frame is used. When speech is too long, pitch-preserving ffmpeg `atempo` is permitted only up to `--max-speedup`; larger overruns stop with an editorial action message.

The final WAV length is constructed in samples from section boundaries, so its duration exactly matches the selected media duration to 1/24000 second.
