## Why

The Metadata review screen had three disjoint edit surfaces, each with its
own separate action: title/description/tags + "Approve metadata" (no
re-render), a collapsed "Revise captions" link with its own submit button,
and a collapsed "Replace background image" link with its own submit button.
User feedback: make everything visible together, with one button that saves
whatever was actually changed.

## What Changes

**Backend** (`api/main.py`, `worker/types.py`, `worker/workflows.py`) — new
endpoint, existing ones untouched:
- New `POST /video_jobs/{video_job_id}/revise-all` (multipart: `srt_text`,
  `title`, `description`, `tags`, optional `image`). Scoped to
  `metadata_review_pending` only — that's the only status with a live
  workflow still open and waiting for a signal; `ready_for_manual_upload`/
  `failed` have none, so `metadata/approve`/`srt/revise`/`image/revise`
  keep serving those (unchanged, still used by `ReadyForUpload`/`failed`'s
  separate toggles per the scoped decision below).
- Detects whether a re-render is actually needed: compares *parsed caption
  text* (not raw SRT string — `parseSrt`/`serializeSrt`'s float-based
  timestamp round-trip can drift by a millisecond of rounding noise with
  zero real edits, confirmed empirically; text is the only thing users can
  actually edit in this UI) against the current stored SRT, and whether a
  new image was uploaded.
  - No change → same fast path as today's `metadata/approve`: signals the
    open workflow directly, no wasted re-render.
  - Caption or image changed → terminates the active workflow, starts one
    `ReviseCaptionsWorkflow` with whichever values changed (never two
    overlapping revise calls racing each other).
- `ReviseCaptionsWorkflowInput` gained an optional `metadata:
  VideoMetadataFields | None` field. When set (only by `revise-all`),
  `ReviseCaptionsWorkflow`'s existing `metadata_already_approved` branch
  calls the existing `approve_metadata` Activity with it before marking
  `ready_for_manual_upload` — reuses the Activity `metadata/approve`'s
  signal handler already calls, rather than duplicating that Mongo write in
  the API layer.

**Frontend** (`web/src/VideoReview.jsx`):
- Extracted `CaptionEditor` — the audio player + editable, mismatch-
  highlighted caption row list — out of `SrtReview` into a presentational
  component (no fetch, no submit button). `SrtReview` (still used standalone
  by the primary `srt_review_pending` screen) becomes a thin wrapper: owns
  fetch + entries state + its own submit button, renders `CaptionEditor`.
- `MetadataReview` (heading renamed "Final review") now owns `entries`
  state too (fetched alongside metadata on mount), a plain always-visible
  image file input, and renders `CaptionEditor` inline — one "Save" button
  serializes everything and posts to `revise-all`.
- Scoped to this screen only: `ReadyForUpload`/`failed` keep their current
  read-only metadata + separate `ReviseCaptionsToggle`/`ReviseImageToggle`
  links, per the user's explicit scope choice.

## Capabilities

No new data-model shape — reuses existing fields/Activities throughout.
`skip_specs: true`.

## Impact

- `api/main.py`, `worker/types.py`, `worker/workflows.py`,
  `web/src/VideoReview.jsx`.
- Verified all four real combinations on throwaway test video_jobs: (1)
  metadata-only edit → confirmed `rerendered: false`, fast signal path, no
  wasted re-render, metadata saved; (2) caption-only edit → confirmed
  `rerendered: true`, edited text present in the output SRT, metadata saved
  from the same submit; (3) image-only edit (deliberately odd-dimensioned,
  to re-confirm `render-video-even-dimensions`'s fix on this path too) →
  confirmed the new image in an extracted video frame; (4) both caption and
  image changed together → confirmed one combined re-render (not two
  racing terminate/restart calls), both changes present in the output.
- Caught and fixed a real bug during verification: the first metadata-only
  test unexpectedly triggered a re-render (`rerendered: true`) — root
  caused to `srt.js`'s float-based timestamp round-trip drifting by
  rounding noise even with zero edits, defeating a raw string-equality
  comparison. Fixed by comparing parsed caption text instead; re-verified
  the fast path with the fix.
- Confirmed the standalone `SrtReview` (primary `srt_review_pending` flow)
  still works correctly after the `CaptionEditor` extraction, and visually
  confirmed the new unified "Final review" screen layout via Playwright
  screenshots.
- Cleaned up all throwaway video_jobs, media, and scratch files after each
  test.
