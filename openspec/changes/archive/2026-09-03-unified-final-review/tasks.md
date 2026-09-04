## 1. Backend

- [x] 1.1 New `POST /video_jobs/{video_job_id}/revise-all` endpoint, scoped to `metadata_review_pending`
- [x] 1.2 `needs_rerender` detection: parsed caption text comparison (not raw string) + image presence
- [x] 1.3 Fast path (no change): signals the open workflow directly, same as `metadata/approve`
- [x] 1.4 Re-render path: terminates active workflow, starts one `ReviseCaptionsWorkflow` with whichever values changed
- [x] 1.5 `ReviseCaptionsWorkflowInput.metadata` (optional) — `ReviseCaptionsWorkflow`'s `metadata_already_approved` branch calls the existing `approve_metadata` Activity when set

## 2. Frontend

- [x] 2.1 Extracted presentational `CaptionEditor` from `SrtReview` (audio player + editable, mismatch-highlighted rows, no fetch/submit)
- [x] 2.2 `SrtReview` thinned to a wrapper (fetch + entries state + its own submit), unchanged behavior for standalone use
- [x] 2.3 `MetadataReview` → "Final review": owns entries + image file + metadata state, renders everything inline, one Save button posting to `revise-all`
- [x] 2.4 `ReadyForUpload`/`failed` left unchanged (scoped decision)

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Metadata-only edit: confirmed `rerendered: false`, no re-render, metadata saved
- [x] 3.2 Caught and fixed a real bug: first metadata-only test showed `rerendered: true` due to `srt.js`'s float timestamp round-trip drift; fixed by comparing parsed caption text instead of raw SRT strings; re-verified fast path with the fix
- [x] 3.3 Caption-only edit: confirmed `rerendered: true`, edited text in output, metadata saved together
- [x] 3.4 Image-only edit (deliberately odd-dimensioned): confirmed `rerendered: true`, new image visible in an extracted video frame, dimensions correctly normalized
- [x] 3.5 Both caption and image changed together: confirmed one combined re-render (no racing terminate/restart), both changes present
- [x] 3.6 Confirmed standalone `SrtReview` (primary `srt_review_pending` flow) still works after the `CaptionEditor` extraction (Playwright screenshot)
- [x] 3.7 Visually confirmed the new unified "Final review" screen layout (Playwright screenshot)
- [x] 3.8 Cleaned up all throwaway video_jobs, media, and scratch files
