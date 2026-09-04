## Why

User request, while reviewing a real episode's AI-generated background
image on the Metadata review screen: they should be able to replace it
without starting the whole video job over. Captions already had this
("Revise captions" — `revise_srt` / `ReviseCaptionsWorkflow`); the
background image had no equivalent.

## What Changes

- New `POST /video_jobs/{video_job_id}/image/revise` (`api/main.py`):
  same revisability rule as `revise_srt`
  (`metadata_review_pending`/`ready_for_manual_upload`/`failed`). Accepts
  a multipart image upload, saves it to the job's media directory, updates
  `video_jobs.image_path`, and re-runs the **existing**
  `ReviseCaptionsWorkflow` with the current, unchanged SRT text and the new
  `image_path` — no new workflow needed, since that workflow already
  re-renders from whatever `image_path`/`srt_text` it's given and already
  handles the "skip metadata regen if already approved" logic this needs
  too.
- `web/src/VideoReview.jsx`: new `ReviseImageToggle` component (a collapsed
  "Replace background image" link expanding into a file input + submit),
  added alongside `ReviseCaptionsToggle` in `MetadataReview`,
  `ReadyForUpload`, and the `failed` block.

## Capabilities

No new data-model shape — `video_jobs.image_path` already existed; this
adds a way to change it post-hoc through the existing revise/re-render
mechanism. `skip_specs: true`.

## Impact

- `api/main.py`, `web/src/VideoReview.jsx`.
- Verified end-to-end on a throwaway test video_job (not the user's real
  one): pushed it to `metadata_review_pending`, called
  `/image/revise` with a new (deliberately odd-dimensioned, to also
  re-confirm `render-video-even-dimensions`'s fix on this path) image,
  confirmed the workflow re-rendered successfully and reached
  `metadata_review_pending` again with the new `image_path` recorded.
- Extracted a frame from the resulting video and visually confirmed it
  shows the new image's color, not the original's — the re-render actually
  used the new file, not a stale cached one.
- Cleaned up the throwaway video_job, workflow, media, and scratch files.
