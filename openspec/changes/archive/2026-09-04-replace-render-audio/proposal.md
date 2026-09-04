## Why

User request on the Render status screen (`RenderJob.jsx`): sometimes after
audio is generated, they want to take the MP3, edit it externally (add
music, etc.), and have the edited file become the canonical audio for that
render job — used for video production and anywhere else `audio_path` is
read. There was no way to do this; the only upload on that page is the
video's background image, which starts a different workflow entirely.

## What Changes

- New `POST /render_jobs/{render_job_id}/audio/replace` (`api/main.py`,
  multipart `audio` file). Valid only when `status` is `complete` or
  `failed` (the latter as a free bonus recovery path — same code path lets
  a failed render be manually un-stuck with a supplied file). Saves the
  upload to `job_dir/audio{ext}` (a new filename, not overwriting the
  original `{unit_id}.{lang}.mp3` — matches the existing
  `revise_image`/`revise_all` `background{ext}` pattern; confirmed by
  grepping every `audio_path` read site that nothing downstream hardcodes
  the original synthesis naming). Updates `audio_path`/`audio_url`,
  `status: "complete"`, clears `error`, sets a new `audio_replaced_at`
  timestamp. No Temporal involvement — by `complete`/`failed`,
  `AudioGenerationWorkflow` has already finished, so this is a pure file +
  Mongo write, unlike the video-side revise endpoints.
- `web/src/RenderJob.jsx`: new `ReplaceAudio` component (file input + "Upload
  and use this audio" button), shown alongside `StartVideoProduction`,
  visually separated and labeled so it isn't confused with the video
  background-image picker.
- Proactive cache-busting: since a second replace on the same render_job
  reuses the identical `audio{ext}` path, applied the same fix as this
  session's `video-cache-busting` change — `?t=<audio_replaced_at>` on the
  `<audio src>` (the `Cache-Control: no-cache` half of that fix already
  covers all of `/media/*`, no change needed there).
- Deliberately not running `apply_id3` on the upload (might not even be an
  MP3) and no content validation beyond what `revise_image` already does
  for images (none) — consistent with established precedent.

## Capabilities

No new data-model shape — reuses existing `render_jobs` fields plus one new
timestamp. `skip_specs: true`.

## Impact

- `api/main.py`, `web/src/RenderJob.jsx`.
- Verified end-to-end on a real throwaway render_job (fast `kokoro` engine):
  uploaded a real, distinct replacement audio file (a 440Hz test tone,
  audibly/structurally different from the TTS narration), confirmed
  `audio_path`/`audio_url`/`audio_replaced_at` updated and the file on disk
  byte-for-byte matches the upload (md5 checksum).
- Confirmed the replacement actually flows through to video production:
  started a real `VideoProductionWorkflow` against the render_job, and its
  `transcribe` activity produced an empty transcript (the sine tone has no
  speech, VAD correctly found nothing) — proof it processed the
  replacement audio, not the original English narration.
- Confirmed the double-replace cache-busting scenario for real: replaced
  the audio a second time (880Hz tone), then via a fresh-context Playwright
  check confirmed the page's actual `<audio src>` carries the *latest*
  `audio_replaced_at` timestamp and resolves to the second replacement's
  exact content (md5-verified), not a stale cached copy of the first.
- Verified the `failed` recovery path (forced a render_job to `failed`,
  uploaded a replacement, confirmed `status` returned to `complete` and
  `error` cleared) and confirmed the endpoint correctly rejects a replace
  attempt on a non-terminal status (`rendering` → 422 with a clear message).
- Cleaned up all throwaway render_jobs/scripts/video_jobs/media/workflow
  executions afterward.
