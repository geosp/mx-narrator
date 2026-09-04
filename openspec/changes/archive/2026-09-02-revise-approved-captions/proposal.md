## Why

Once captions are approved, `VideoProductionWorkflow` moves on and eventually
closes (`ready_for_manual_upload` or `failed`) — a closed Temporal workflow
execution can't be signaled. There was no way to fix a caption typo discovered
after approval without starting the whole episode over. User asked for a way to
review and edit approved captions again, with the video actually re-rendered to
match — not a cosmetic-only text edit.

## What Changes

- New `ReviseCaptionsWorkflow` (`worker/workflows.py`): started fresh (the
  original workflow execution has typically already closed) when captions are
  edited after first approval. Redoes only what depends on caption text —
  `finalize_srt` + `render_video` — skipping transcription and the correctness
  check entirely (the human's edit *is* the correction now) and skipping
  metadata regeneration when metadata was already approved (caption wording
  doesn't change an LLM-generated title/description drawn from the script).
  When metadata wasn't approved yet, it still goes through
  `generate_metadata`/`save_metadata_draft`/review, same as the first time.
- New `POST /video_jobs/{id}/srt/revise` endpoint — allowed only once a video
  job has reached `metadata_review_pending`, `ready_for_manual_upload`, or
  `failed` (doubling as a retry path for a failed render). Best-effort
  terminates whatever workflow is currently associated with the video job,
  starts the new one.
- **Real gap this surfaced and fixed**: `POST /video_jobs/{id}/metadata/approve`
  hardcoded the workflow ID it signals (`video-prod-{id}`) — wrong once a
  revise workflow (`video-revise-{id}`) is the one actually waiting for that
  signal. Fixed by storing `video_jobs.active_workflow_id`, updated whenever a
  new workflow starts for that video job, and read (not hardcoded) by the
  approve-metadata endpoint.
- `web/src/VideoReview.jsx`: `SrtReview` (built last turn) is now parametrized
  by endpoint/label so the exact same synced per-caption UI is reused for
  revision, not rebuilt. A collapsed-by-default "Revise captions" toggle is
  added to the metadata-review, ready-for-upload, and failed screens.

## Capabilities

### Modified Capabilities
- `workflow/video-production`: adds the ability to revise approved captions
  and re-render after the fact.

## Impact

- `worker/workflows.py`: new `ReviseCaptionsWorkflow`, duplicating a small
  signal + tail block from `VideoProductionWorkflow` rather than extracting a
  shared base class — see design.md.
- `worker/types.py`: `ReviseCaptionsWorkflowInput`.
- `worker/activities.py`: new `reset_manually_uploaded`.
- `worker/main.py`: registers `ReviseCaptionsWorkflow` — **a real bug was caught
  during verification**: it was imported but never added to the `Worker(...)`
  registration list, so the first real revise attempt failed immediately
  (`WorkflowTaskFailed`, retrying indefinitely with zero effect) until this was
  found and fixed.
- `worker/cpu_main.py`: registers `reset_manually_uploaded`.
- `api/main.py`: new `/srt/revise` endpoint; `active_workflow_id` tracking.
- `web/src/VideoReview.jsx`: `SrtReview` parametrized; revise toggle added.
- No changes to `generate_metadata`, `correctness_check`, `transcribe`, or any
  code in `src/narrator/`.
