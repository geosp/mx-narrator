## Why

Phase 3 (`VideoProductionWorkflow`, RFC §7.2) is the next unbuilt phase: transcribe →
correctness_check → [mismatch review] → SRT review → render_video → generate_metadata
→ metadata review → done. That's five pipeline stages plus two human-review UI
screens, and it bundles several genuine firsts for this codebase at once (a new ML
dependency for transcription, a new file format, Temporal signal-wait/human-in-the-
loop). This change scopes down to the first three stages — transcribe,
correctness_check, and the SRT review signal-wait — the same small,
independently-verifiable vertical slice every prior phase in this project has been.
`render_video`, wiring the already-built `generate_metadata` Activity into the
workflow, and the metadata-review signal-wait are deferred to a follow-up change that
extends this same workflow once this slice is proven.

This change also fixes a real, previously-documented gap: `POST /scripts` never
collects `series_name`, which means `generate_metadata`'s prior-approved-episode-
titles context (built in the `llm-metadata-generation` change) has had no real data
to draw on since it was built. Small, well-contained, and a real blocker for that
feature — included here rather than deferred again.

## What Changes

- New Temporal workflow `VideoProductionWorkflow`: `transcribe` (faster-whisper,
  GPU) → `correctness_check` (CPU, exact-text diff against narrator's own known TTS
  input) → if mismatch: signal-wait for human acknowledgment → signal-wait for SRT
  review/approval → `finalize_srt`. Ends at a new `srt_approved` status — a
  **disclosed, deliberate deviation** from RFC §7.3's literal `rendering` transition,
  since `render_video` doesn't exist yet in this change.
- New Activities: `transcribe`, `correctness_check`, `mark_video_job`, `finalize_srt`.
- New `video_jobs` MongoDB collection (RFC §6.2), first real usage.
- New API endpoints on the existing `api` service: `POST /video_jobs` (multipart,
  starts the workflow), `POST /video_jobs/{id}/mismatch/acknowledge`,
  `POST /video_jobs/{id}/srt/approve`, `GET /video_jobs/{id}/srt`,
  `GET /video_jobs/{id}/events` (SSE). Also adds static media serving
  (`/media` mount) so the review UI can play back the source audio — didn't exist
  before since Phase 2's UI never needed playback.
- New frontend screen `web/src/VideoReview.jsx`: mismatch review list +
  acknowledge button, SRT review (audio playback + editable textarea) + approve
  button, live status via SSE.
- **`api/scripts` fix**: `POST /scripts` now accepts and stores `series_name`
  (optional, additive, non-breaking).
- New dependencies: `faster-whisper`, `srt`, `python-multipart`.

## Capabilities

### New Capabilities
- `workflow/video-production`: transcription → exact-text correctness check → SRT
  human review, ending at `srt_approved` — the first slice of `VideoProductionWorkflow`.

### Modified Capabilities
- `api/scripts`: `POST /scripts` additionally accepts and stores a `series_name`
  field, closing the gap that left `generate_metadata`'s series-context feature
  (from `llm-metadata-generation`) without real data to use.

## Impact

- New code: `worker/transcription.py`, `worker/diff.py`, additions to
  `worker/activities.py`/`worker/types.py`/`worker/workflows.py`/`worker/main.py`/
  `worker/cpu_main.py`, new endpoints + static mount in `api/main.py`,
  `web/src/VideoReview.jsx`.
- Extends `pyproject.toml` (three new dependencies) and `deploy/docker-compose.yml`
  (`WHISPER_MODEL`/`WHISPER_COMPUTE_TYPE` env vars on `gpu-worker`, no new service).
- No changes to `AudioGenerationWorkflow`, `synthesize`, or `generate_metadata`'s own
  internals — this change only fixes the caller-side data gap in `api/scripts` that
  `generate_metadata` already handles gracefully.
- Depends on Phase 2 infra and a real `render_jobs`/MP3 to transcribe against.
- Not wired into a full `VideoProductionWorkflow` end-to-end — `render_video`,
  metadata generation, and metadata review remain a separate, future change.
