## Why

A real episode's correctness check ("No se turbe su corazón", Juan 14) surfaced 24
mismatches, and the user asked what was going on. Inspecting them showed most were
false positives from two gaps in `worker/diff.py::check_correctness()`'s
normalization, not narration errors: Spanish accent marks aren't folded (`qué`
vs `que`, `aún` vs `aun`, `pódcast` vs `podcast` compare as different words), and
words with two RAE-valid spellings — one word or two — tokenize differently
("adonde" in the script vs Whisper's "a donde"). Both are noise that drowns out
the mismatches that actually matter, undermining the whole point of a review step
meant to catch real narration/transcription problems.

## What Changes

- `_normalize_text()` now folds acute/grave/circumflex/diaeresis accent marks to
  their base vowel (á/à/â/ä/ã→a, etc.) before comparison — deliberately NOT
  folding `ñ` or `ç`, which are distinct letters, not accented vowels, in
  Spanish/Portuguese.
- A new merge pass (`_merge_split_words`, Spanish-only) collapses a small,
  explicit set of RAE-recognized two-spelling words ("a donde"/"adonde", "por
  que"/"porque", "con que"/"conque", "si no"/"sino", "a parte"/"aparte") to one
  canonical form on both the expected and actual token lists before diffing.
- Verified directly against the real episode that prompted this: re-ran
  `check_correctness` with its actual script text and actual transcribed
  captions — all 6 accent/word-boundary false positives from that run are gone;
  every other mismatch (two dropped "no se turbe su corazón" phrases, one large
  unaligned block, and several plausible ASR mishearings like "iscariote"→
  "escariote") is unchanged, confirming the fix removes noise without hiding
  signal.

## Capabilities

### Modified Capabilities
- `workflow/video-production`: the correctness-check requirement's normalization
  is more accurate — accent-mark and word-boundary spelling variants no longer
  produce false-positive mismatches.

## Impact

- `worker/diff.py` only. No API, workflow-shape, or frontend changes — this is a
  pure accuracy fix to an existing Activity's internal logic.
- No changes to `src/narrator/` — this normalization is specific to comparing
  Whisper transcripts against narrator's known input text, not something the
  synthesis pipeline itself needs.
