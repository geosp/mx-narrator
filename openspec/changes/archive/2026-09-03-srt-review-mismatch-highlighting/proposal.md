## Why

User feedback on the `mismatch_needs_review` screen: the list of correctness-
check mismatches (timestamp, expected, actual) is read-only, and once you
click "Acknowledge and continue" into the caption editor
(`srt_review_pending`), there's nothing distinguishing the flagged captions
from the rest — you have to remember timestamps from the previous screen to
find and check them.

## What Changes

- `web/src/VideoReview.jsx`: `SrtReview` now accepts a `mismatches` prop.
  Each caption row whose time range overlaps a mismatch's `approx_time`
  (within a 1.5s tolerance, to absorb minor timestamp drift after
  `align_captions` re-times entries) gets a red left border + light red
  background, plus an inline note under the textarea: `⚠ expected "X" —
  heard "Y"` for each matching mismatch.
- `mismatches` threaded from the `job.correctness_check.mismatches` already
  in the video_job document, through `MetadataReview`/`ReadyForUpload`/the
  `failed` block/`ReviseCaptionsToggle`, to every place `SrtReview` renders
  — not just the primary review flow, so a later "Revise captions" pass also
  benefits.
- `MismatchReview` (the mismatch list screen itself) gained one line of
  explanatory text pointing at the new behavior, so it's discoverable.
- No inline editing added to the mismatch-list screen itself — kept a single
  editing surface (SrtReview) rather than splitting caption editing across
  two screens.
- Fixed a real regression introduced while building this: wrapping the
  caption `<textarea>` in a new div (to hold the mismatch note underneath
  it) broke its width — it was previously a direct flex child of the row
  and stretched via `flex: 1`; nested inside a plain div it had no explicit
  width and shrank to its intrinsic size, truncating caption text. Fixed
  with an explicit `width: "100%"` on `captionText`. Caught by the user
  against their own real, in-progress video job — screenshotted first with
  the bug, then re-verified fixed against the same real job (read-only,
  nothing submitted/approved).

## Capabilities

No new API/data-model contract — `correctness_check.mismatches` already
existed and was already sent to the client; this only changes how it's
displayed. `skip_specs: true`.

## Impact

- `web/src/VideoReview.jsx` only.
- Verified with real Playwright screenshots: first against a synthetic test
  video_job with real correctness-check mismatches (confirmed the flagged
  captions render with the red border and the correct expected/heard text),
  then against the user's own real, currently in-review video job to
  confirm the width-truncation bug and its fix, without submitting or
  approving anything on that real job.
