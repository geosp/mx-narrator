## 1. Heartbeat fix

- [x] 1.1 Add the same heartbeat-thread pattern `synthesize`/`transcribe` already
      use to `render_video` (`worker/activities.py`), and a matching
      `heartbeat_timeout` on its `execute_activity` call in
      `worker/workflows.py` — verified with a real short episode end to end
      (script → render → transcribe → SRT approve → render_video →
      generating_metadata → metadata_review_pending) completing normally with the
      heartbeat thread running throughout, no regression to the happy path

## 2. Live incident recovery

- [x] 2.1 Diagnosed the real orphaned execution that prompted this change:
      `docker top` showed no ffmpeg process and 0% CPU in `cpu-worker` despite
      Temporal reporting the activity `"Started"` 8 minutes earlier — confirmed
      via `temporal workflow describe` (`LastWorkerIdentity` pointed at a
      container recreated minutes prior). Terminated the orphaned workflow
      execution and removed only the stale `video_jobs` document and its media
      directory — verified the episode's `scripts`/`render_jobs` documents (the
      actual 20-minute narration) were completely untouched and the episode
      remained startable from "Start video production" immediately afterward

## 3. Documentation

- [x] 3.1 This proposal and spec delta, archived alongside the fix.
