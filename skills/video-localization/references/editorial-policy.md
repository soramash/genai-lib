# Editorial and translation policy

## Japanese correction

Correct recognition errors, punctuation, spacing, obvious filler, and broken sentence boundaries while preserving the speaker's meaning and level of certainty. Restore terms from slide context when evidence is clear. Do not add claims, remove caveats, modernize dates, or silently guess unclear proper nouns.

Create two views:

- Cue-locked `corrected_ja` for subtitles and traceability.
- Readable Markdown that joins adjacent cues into paragraphs under timestamped topical headings.

## English translation

Translate meaning, not Japanese word order. Use concise, professional presentation English that fits the original cue duration. Maintain consistent terminology throughout. Preserve:

- Proper nouns and official product or organization spelling.
- Acronyms; expand only when the presentation explains them or the expansion is certain.
- Numbers, units, dates, versions, percentages, and comparison direction.
- Modality and negation such as must, may, cannot, planned, and completed.

Do not embellish, summarize away details, or use a more certain claim than the Japanese. If one English sentence spans several cues, distribute natural fragments across the existing cues without moving timestamps.

## TTS narration Markdown

The English TTS Markdown is a readable narration view, not a new translation. Its section bodies must cover all translated content in order without duplication or omission. Use `## [HH:MM:SS] Title` headings at stable presentation boundaries. The first starts at `00:00:00`; each next heading defines the previous section's end. Titles are metadata and are not spoken.
