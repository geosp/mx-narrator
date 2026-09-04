## 1. Backend

- [x] 1.1 New `POST /render_jobs/{render_job_id}/audio/replace` endpoint, valid for `complete`/`failed` statuses
- [x] 1.2 Saves upload to `job_dir/audio{ext}`, updates `audio_path`/`audio_url`/`status`/`audio_replaced_at`, clears `error`

## 2. Frontend

- [x] 2.1 New `ReplaceAudio` component, shown alongside `StartVideoProduction`
- [x] 2.2 Cache-busting `?t=<audio_replaced_at>` applied to the `<audio src>`

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Real throwaway render_job synthesized via kokoro (fast)
- [x] 3.2 Uploaded a real, distinct replacement (440Hz tone); confirmed doc fields updated and file matches upload byte-for-byte (md5)
- [x] 3.3 Started a real `VideoProductionWorkflow` against the render_job; confirmed its transcript came back empty (proof it processed the sine tone, not the original narration)
- [x] 3.4 Replaced the audio a second time (880Hz tone); confirmed via fresh-context Playwright that the page's `<audio src>` carries the latest timestamp and resolves to the second replacement's exact content (md5-verified) — the cache-busting scenario
- [x] 3.5 Verified the `failed` → replace → `complete` recovery path
- [x] 3.6 Verified rejection on a non-terminal status (`rendering` → 422)
- [x] 3.7 Cleaned up all throwaway render_jobs/scripts/video_jobs/media/workflow executions
