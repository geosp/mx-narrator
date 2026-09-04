## Why

This is a retroactive proposal: dashboard browsing, script edit/regenerate, delete,
and series listing were already built and verified this session in direct response
to real usage gaps the user hit while running the app day-to-day (no way to see
what's in the database, no way to fix a typo without starting over, no way to remove
a test episode, no way to reuse a series name without retyping it). They were
implemented one gap at a time as reported, not as a single planned phase, so
`openspec/specs` never caught up — `api/scripts`'s baseline still only describes the
original upload-and-render flow, and nothing describes the dashboard, series
listing, or per-script edit/delete lifecycle at all. This change closes that gap so
the spec baseline matches what's actually running.

## What Changes

- **Dashboard listing**: `GET /dashboard` returns every script joined with its
  latest `render_jobs`/`video_jobs` status, so the UI can show what the database
  holds without the client already knowing a specific job id. `GET /series` returns
  the distinct series names currently in use.
- **Script detail + edit**: `GET /scripts/{id}` returns a script's current text,
  tags, and render parameters (pulled from its latest render job) for pre-filling an
  edit form, plus whether it has an associated video job. `PUT
  /scripts/{id}/regenerate` updates the script and starts a fresh render — since the
  new audio invalidates any transcription/video review done against the old audio,
  the existing render job and video job (and their media files, and any in-flight
  Temporal workflow) are discarded first, matching the same destructive-but-declared
  approach as delete below.
- **Script deletion**: `DELETE /scripts/{id}` removes a script and cascades through
  its render job(s) and video job(s) — terminating any in-flight workflow, deleting
  media files, then the MongoDB documents.
- **Series are derived, not stored**: no new collection or cleanup logic — a series
  "exists" exactly as long as some script's `series_name` references it, so it stops
  being listed automatically once its last script is deleted or edited away.
- **Render progress and playback**: `render_jobs.progress` (`{current, total}`
  chunk counts) is written incrementally during synthesis, and `render_jobs.
  audio_url` is written once a render completes, so both the workflow's own SSE
  stream and `GET /dashboard` can show live progress and offer inline playback
  without either endpoint recomputing anything.

## Capabilities

### New Capabilities
- `api/dashboard`: cross-collection episode listing (`GET /dashboard`) and series
  listing (`GET /series`) for browsing what the database currently holds.

### Modified Capabilities
- `api/scripts`: adds script detail retrieval, edit-and-regenerate (with cascade
  discard of stale render/video work), and cascade deletion.
- `workflow/audio-generation`: `render_jobs` documents now carry incremental chunk
  progress during synthesis and a playback URL once complete.

## Impact

- `api/main.py`: `GET /dashboard`, `GET /series`, `GET /scripts/{id}`, `PUT
  /scripts/{id}/regenerate`, `DELETE /scripts/{id}`; shared helpers
  `_start_render`, `_delete_render_jobs_for_script`, `_terminate_workflow`,
  `_media_url`.
- `worker/activities.py`: `synthesize` reports chunk progress via a callback;
  `mark_render_job` computes `audio_url` on completion.
- `src/narrator/batch.py`: `render_job()` accepts an optional `progress_callback`
  (additive, no behavior change for existing callers).
- New frontend screens `web/src/Dashboard.jsx` (default landing page),
  `web/src/RenderJob.jsx` (extracted from the old inline status view),
  `web/src/EditScript.jsx`, and a shared `web/src/ScriptForm.jsx`/`web/src/lib.js`.
  Frontend structure isn't spec'd (this project's existing convention — see
  `workflow/video-production`'s handling of `VideoReview.jsx`), but is listed here
  for completeness.
- No changes to `VideoProductionWorkflow`'s own internals, or to
  `generate_metadata`/`correctness_check`.
