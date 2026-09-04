## 1. Diagnosis (real infrastructure, no mocking)

- [x] 1.1 Checked file timestamps on the reported real video job — confirmed a genuine re-render happened after the SRT was saved
- [x] 1.2 Extracted a frame from the actual server-side output.mp4 at the corrected caption's timestamp — confirmed the fix was already present server-side
- [x] 1.3 `HEAD` request on the live media URL — confirmed no `Cache-Control` header, explaining why a browser could serve a stale cached copy indefinitely

## 2. Fix

- [x] 2.1 `mark_video_job` sets `video_rendered_at` whenever `video_path` is set
- [x] 2.2 `Cache-Control: no-cache` middleware on `/media/*` responses
- [x] 2.3 Frontend appends `?t=<video_rendered_at>` to the video URL

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Rebuilt and redeployed api/web/gpu-worker/cpu-worker after confirming no workflow was mid-activity
- [x] 3.2 Found and terminated an unrelated orphaned workflow from earlier test cleanup (video_job document deleted, workflow left running)
- [x] 3.3 Re-checked the media `HEAD` response — confirmed `Cache-Control: no-cache` now present
- [x] 3.4 Did not modify the reported real video job's data — diagnosis was entirely read-only
- [x] 3.5 Cleaned up scratch files
