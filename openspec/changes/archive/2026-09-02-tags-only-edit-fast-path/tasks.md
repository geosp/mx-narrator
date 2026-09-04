## 1. Shared ID3 helper

- [x] 1.1 Extract `apply_id3` from `worker/activities.py` into a new, import-light
      `worker/id3.py` (only `mutagen`/`pathlib`/`worker.types`, no ML/LLM deps), and
      update `synthesize`'s one call site — verified the shared image still builds
      and the API container starts cleanly with `from worker.id3 import apply_id3`
      in `api/main.py` (no heavy-dependency import errors at startup)

## 2. Backend decision and fast path

- [x] 2.1 In `api/main.py`'s `regenerate_script`, fetch the latest render_job and
      compute `needs_full_regenerate` from the fixed audio-affecting field list
      (`unit_id`, `lang`, `script_text`, `engine_name`, `speed`, `exaggeration`,
      `cfg_weight`, `seed`) plus `render_job.status != "complete"` — verified via
      real requests against a live script: identical resubmission and a tag-only
      resubmission both correctly took the fast path
- [x] 2.2 Implement the fast path: `$set` the render_job's `id3`/`series_album`/
      `title` fields, call `apply_id3()` on the existing `audio_path` in place, and
      return `audio_regenerated: false` with the *same* `render_job_id` — verified
      against real Mongo/disk state: editing only the artist tag left
      `render_jobs._id`, `audio_path`, and the associated `video_jobs` doc and its
      media directory completely untouched, while the MP3's actual `TPE1` frame
      (read back via `mutagen.ID3`) changed from the old value to the new one
- [x] 2.3 Confirm the existing full-regenerate path (response model renamed
      `ScriptOut` → `RegenerateOut`, adding `audio_regenerated`) is unchanged when
      `script_text` changes — verified: `audio_regenerated: true`, a *new*
      `render_job_id`, and the prior render_job/video_job/media directories
      confirmed gone from disk afterward

## 3. Frontend confirm-dialog gating

- [x] 3.1 Add `audioAffectingFieldsChanged()` to `web/src/EditScript.jsx` (same
      field list as the backend, comparing the fetched `initialValues` against the
      submitted form) and gate the destructive-cascade `confirm()` on it — verified
      via a real headless-browser session: editing only the ID3 artist field on an
      episode with an existing video review submitted with no dialog appearing, and
      the video review was confirmed still present via a live `GET /dashboard` call
      afterward
- [x] 3.2 Verify the dialog still fires correctly when it should — a separate,
      isolated Playwright session (to avoid a listener-leak artifact seen in an
      earlier combined test run) confirmed: editing the script text on an episode
      with a video review fired the confirm dialog with the expected message;
      dismissing it left the render_job id, the video_job, and all media completely
      unchanged
- [x] 3.3 Reword the persistent warning banner and page subtitle to distinguish
      "editing tags is safe" from "editing text/voice settings deletes the review" —
      verified visually that the copy reflects the new behavior

## 4. Documentation

- [x] 4.1 This proposal/design/spec-delta set, written and archived alongside the
      implementation above (not left to drift, per explicit instruction this
      session) — folds into `api/scripts`'s baseline, replacing the
      unconditionally-destructive version of the regenerate requirement.
