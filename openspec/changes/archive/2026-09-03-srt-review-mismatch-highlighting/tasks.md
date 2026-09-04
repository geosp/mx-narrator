## 1. Mismatch highlighting

- [x] 1.1 `SrtReview` accepts a `mismatches` prop; `mismatchesForEntry()` matches by time overlap with a 1.5s tolerance
- [x] 1.2 Flagged rows get a red left border + light red background, plus an inline `⚠ expected/heard` note per matching mismatch
- [x] 1.3 `mismatches` threaded through `MetadataReview`, `ReadyForUpload`, the `failed` block, and `ReviseCaptionsToggle` — every place `SrtReview` renders
- [x] 1.4 `MismatchReview` got one line pointing at the new behavior

## 2. Width regression (found and fixed during verification)

- [x] 2.1 Diagnosed: wrapping the caption textarea in a new div for the mismatch note broke its `flex: 1` width inheritance
- [x] 2.2 Fixed with an explicit `width: "100%"` on `captionText`

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Built a throwaway test video_job with real correctness-check mismatches; Playwright screenshot confirmed flagged rows render correctly with the right expected/heard text
- [x] 3.2 User independently caught the width regression on their own real, in-progress video job (screenshot)
- [x] 3.3 Re-verified the fix against that same real job via a read-only Playwright screenshot — confirmed full-width text, nothing submitted/approved on the real job
- [x] 3.4 Cleaned up the throwaway test video_job, media, and scratch files
