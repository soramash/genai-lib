# Cue-locked transcript schema

`segments.py init` creates a UTF-8 JSON array. Each item has exactly this logical shape:

```json
{
  "index": 1,
  "start": "00:00:00,000",
  "end": "00:00:04,120",
  "raw_ja": "Whisper output copied from the source SRT",
  "corrected_ja": "校正済みの日本語",
  "en": "Concise English subtitle translation."
}
```

## Invariants

- Keep array order and cue count unchanged.
- Keep `index` contiguous from 1 and unchanged.
- Keep `start` and `end` byte-for-byte unchanged.
- Keep `raw_ja` unchanged; it is an audit record of local ASR output.
- Fill every `corrected_ja` and `en` value.
- Do not merge, split, insert, or delete cues.
- Preserve names, acronyms, product terms, numbers, dates, URLs, and negation.
- Record unresolved words visibly, for example `[聞き取り不明]` / `[unclear]`; never invent facts.

`segments.py validate` compares all locked fields with the raw SRT and fails on drift. `segments.py render` refuses invalid input.
