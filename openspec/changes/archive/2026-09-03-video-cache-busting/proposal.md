## Why

Real user report: revised captions to fix a mistake, the re-render
completed successfully, but the video review page kept showing the video
with the old mistake. Investigated video job
`21d97618-8176-4fef-9b00-e71bc9a4e437`:
- File timestamps confirmed a real re-render happened (`captions.srt`
  updated, then `output.mp4` regenerated ~22s later).
- Extracted a frame from the actual server-side `output.mp4` at the
  corrected caption's timestamp — it already showed the fix.
- A `HEAD` request on the live `/media/.../output.mp4` URL showed no
  `Cache-Control` header at all.

Root cause: `video_url`'s path (`/media/{video_job_id}/output.mp4`) is
identical across every re-render — same video_job_id, same filename,
overwritten in place. With no `Cache-Control` header, browsers apply their
own heuristic freshness and can reuse a stale cached copy indefinitely
without checking the server again. Even a same-page SSE-driven re-render
wouldn't have refetched anyway: since the `src` string is byte-identical
before and after a revise, React never mutates the `<video>` element's
`src` attribute, so the browser has no signal to even attempt a new
request.

## What Changes

- `worker/activities.py`: `mark_video_job` now sets `video_rendered_at`
  (current UTC time) alongside `video_path`/`video_url` whenever a video is
  (re-)rendered.
- `api/main.py`: new lightweight middleware sets `Cache-Control: no-cache`
  on all `/media/*` responses — browsers may still cache, but must always
  revalidate via the existing ETag/Last-Modified rather than trusting
  heuristic freshness. Defense in depth alongside the fix below, covering
  plain page reloads/fresh navigations.
- `web/src/VideoReview.jsx`: the video URL passed to `MetadataReview`/
  `ReadyForUpload` now appends `?t=<video_rendered_at>` — guarantees the
  `<video src>` attribute actually changes after a revise, so the browser
  is forced to fetch fresh content even within a live SSE-updated page,
  not just on a fresh navigation.

## Capabilities

No API/data-model contract change — `video_rendered_at` is an internal
timestamp for cache-busting, not a new capability. `skip_specs: true`.

## Impact

- `worker/activities.py`, `api/main.py`, `web/src/VideoReview.jsx`.
- Verified against the real reported video job (read-only — no changes made
  to that job's data): confirmed via file timestamps and an extracted video
  frame that the server-side render was already correct, isolating the bug
  to browser-side caching rather than a backend re-render failure.
- Verified the fix live: `HEAD` request on the same video URL now returns
  `Cache-Control: no-cache` (previously absent).
- Found and terminated an unrelated orphaned Temporal workflow from an
  earlier test session (a video_job whose Mongo document had been deleted
  during test cleanup, but whose workflow execution was left running,
  idly waiting on a signal that would never come) before redeploying.
- The specific already-affected video (rendered before this fix) needs a
  hard refresh (or a new revise, which will now set `video_rendered_at`)
  to show correctly — the underlying server content was already right.
