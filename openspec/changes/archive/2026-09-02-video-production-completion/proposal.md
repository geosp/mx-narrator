## Why

`video-transcription-review` deliberately ended `VideoProductionWorkflow` at
`srt_approved`, deferring `render_video`, wiring `generate_metadata` into the
workflow, and metadata review to a follow-up change. Since then `VideoReview.jsx`
has literally told users "Video rendering is a future step" — there has never been
a video file anywhere in this app, only audio. Separately, `generate_metadata`
(from `llm-metadata-generation`) has existed as a working, tested Activity that
nothing calls, so `video_metadata` has never had a real document and
`_fetch_series_context`'s prior-approved-titles lookup has never had real data to
find. This change completes the pipeline per the RFC's own design (§7.2, §7.3),
taking an episode all the way from `srt_approved` to the terminal
`ready_for_manual_upload` state.

## What Changes

- New `render_video` Activity (new `worker/video.py`): ffmpeg loops the background
  image and muxes it with the finished audio and the approved SRT as a **soft**
  (selectable, `mov_text`) subtitle track — not burned in. Runs on `cpu-tasks`
  (pure muxing, no GPU). Kept entirely Narrator-Studio-side, not added to
  `src/narrator/` — video production was never part of the original CLI's scope.
- `generate_metadata` is now actually called from `VideoProductionWorkflow`
  (unchanged itself) via two new small Activities: `save_metadata_draft` (first
  write to `video_metadata`) and `approve_metadata` (writes the human-edited final
  values + `human_approved_at` — the first real data `_fetch_series_context` has
  ever had).
- New workflow signal `approve_metadata(title, description, tags)`, same shape as
  the existing `approve_srt`.
- New API endpoints: `GET /video_jobs/{id}/metadata`, `POST
  /video_jobs/{id}/metadata/approve`, `POST /video_jobs/{id}/manually_uploaded`
  (pure bookkeeping — no YouTube call of any kind, ever, per RFC §6.2).
- `mark_video_job` gains `video_path`/`error` params (computing `video_url` the
  same way `mark_render_job` already does for `audio_url`) and the workflow now
  wraps the render/metadata span in a try/except that records a real `"failed"`
  status — closing a gap flagged (but deferred) in `episode-lifecycle-management`'s
  design.md, hit for real during this change's own verification.
- `web/src/VideoReview.jsx` replaces the "future step" placeholder with real
  handling for `rendering`/`generating_metadata` (busy state), a metadata review
  form (editable title/description/tags + video preview), and the terminal
  `ready_for_manual_upload` screen (final video, approved metadata, a "manually
  uploaded" checkbox).
- **Infra fix**: `cpu-worker` never had the `media-data` volume mounted (it
  previously only did pure-text/LLM work with no file I/O) — `render_video` needs
  it to read the image/audio/SRT and write the MP4. Found via a real failed run
  during verification, not anticipated in the design.

## Capabilities

### Modified Capabilities
- `workflow/video-production`: extends the workflow past `srt_approved` through
  `rendering` → `generating_metadata` → `metadata_review_pending` →
  `ready_for_manual_upload`, plus a `failed` state for this span.

## Impact

- New file `worker/video.py`.
- `worker/activities.py`: `render_video`, `save_metadata_draft`,
  `approve_metadata`; `mark_video_job` extended.
- `worker/workflows.py`: `VideoProductionWorkflow` extended; new
  `approve_metadata` signal; failure handling added for the new span.
- `worker/types.py`: `RenderVideoInput`/`Result`, `SaveMetadataDraftInput`,
  `ApproveMetadataInput`; `image_path` added to `VideoProductionWorkflowInput`.
- `worker/cpu_main.py`: registers the three new activities.
- `api/main.py`: three new `/video_jobs/*` endpoints; threads `image_path` into
  the workflow input.
- `web/src/VideoReview.jsx`, `web/src/lib.js` (new status colors).
- `deploy/docker-compose.yml`: `cpu-worker` gains `MEDIA_ROOT` and the
  `media-data` volume mount.
- No changes to `generate_metadata`, `_fetch_series_context`, or any code in
  `src/narrator/`.
