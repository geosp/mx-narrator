## Why

A real user episode's `render_video` activity got orphaned when `cpu-worker` was
recreated (redeploying an unrelated fix) while it was mid-run. `render_video` had
no heartbeat, unlike `synthesize`/`transcribe`, so Temporal had no way to notice
the worker was gone — the activity sat showing `"Started"` with zero actual CPU
usage for 8+ minutes, on track to occupy the full 30-minute
`start_to_close_timeout` before finally failing. Diagnosed live via `docker top`
(no ffmpeg process at all) and `temporal workflow describe` (activity still
"Started", worker identity from the now-gone container) — the user just saw
"RENDERING" for a long time with no way to know it was actually stuck versus
slow.

## What Changes

- `render_video` (`worker/activities.py`) now heartbeats every 15s via a
  background thread, exactly matching `synthesize`/`transcribe`'s existing
  pattern — a dead worker is detected within `RENDER_VIDEO_HEARTBEAT_TIMEOUT`
  (45s) instead of the full 30-minute `start_to_close_timeout`.
- `VideoProductionWorkflow`'s `render_video` activity call
  (`worker/workflows.py`) gets a matching `heartbeat_timeout`.
- The one orphaned real execution was terminated and its stale `video_jobs`
  document removed directly (its `render_jobs`/`scripts` documents — the actual
  20-minute narration — were untouched); the episode is startable again from
  "Start video production" using the same already-complete audio.

## Capabilities

### Modified Capabilities
- `workflow/video-production`: video rendering failures (including a lost
  worker) are now detected promptly, not only after the full timeout.

## Impact

- `worker/activities.py`: `render_video` gains the same heartbeat-thread
  boilerplate `synthesize`/`transcribe` already use.
- `worker/workflows.py`: one new timeout constant, one new parameter on an
  existing `execute_activity` call.
- No schema, API, or frontend changes.
