# QA checklist

## Automated gates

- Preflight report has `ok: true` and identifies video plus audio streams.
- Raw SRT parses, cue IDs are contiguous, durations are positive, and cues do not overlap.
- Segments validation has no errors; cue count, IDs, timestamps, and `raw_ja` match the raw SRT.
- TTS dry run recognizes all sections and starts at `00:00:00`.
- TTS manifest reports 24 kHz mono 16-bit PCM and a final duration equal to the source.
- Final MP4 has one video stream, English default audio, Japanese secondary audio, and default English subtitles.
- Final duration is within tolerance of the source.
- Source and final video elementary-stream hashes match.
- Extracted subtitle cues exactly match the English SRT.
- Both audio tracks decode without ffmpeg errors.

## Human review

- Spot-check the beginning, section transitions, proper nouns, dates, numbers, and the ending.
- Confirm subtitles appear with the corresponding slide or spoken topic and are readable at normal speed.
- Listen for duplicated, omitted, clipped, unnaturally accelerated, or excessively silent speech.
- Confirm English is the default track and Japanese can be selected.
- Confirm the original source file's hash and modification time were not changed.

## Optional semantic audio check

For high-assurance delivery, transcribe the final English track locally and compare it with the English narration text. Report the ASR model, normalization method, word error rate, and similarity; treat this as supporting evidence rather than exact proof because ASR itself can err.
