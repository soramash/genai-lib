# Subtitle policy

- Cue IDs, start times, and end times are immutable after transcription.
- Prefer one line; use at most two readable lines for English.
- Target no more than 42 English characters per line and roughly 84 per cue. `segments.py validate` warns above 84 characters.
- Break English at phrase boundaries. Avoid leaving articles, prepositions, auxiliaries, or names isolated at a line edge.
- Keep punctuation natural and avoid all-caps except established acronyms.
- Do not encode styling, positioning, speaker labels, or explanatory notes unless they exist in the source meaning.
- Keep subtitles valid UTF-8 SRT. Do not hand-edit generated numbering or time ranges.
- A short visual gap between cues is acceptable. Never extend a cue over the next cue to improve reading time.

After muxing, compare the subtitle stream extracted from MP4 with the source English SRT by parsed cue ID, timestamps, and text. MP4 packet counts can differ from SRT cue counts because the mov_text track may contain empty samples; parsed cue equality is the authoritative check.
