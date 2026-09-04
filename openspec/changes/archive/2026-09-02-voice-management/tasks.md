## 1. Shared storage convention

- [x] 1.1 Add `worker/voice_storage.py` (`voice_dir`, `voice_family_path`,
      `sample_path` — import-light, only `pathlib`) implementing the
      `MEDIA_ROOT/voices/{voice_id}/voice[.{lang}].wav` convention that
      `narrator.voices.resolve_voice()` already expects, unmodified — verified the
      shared image still builds and both `api` and `gpu-worker` start cleanly
      importing it

## 2. Backend: voices API

- [x] 2.1 Implement `GET /voices`, `POST /voices`, `POST /voices/{id}/samples`,
      `DELETE /voices/{id}/samples/{lang}`, `DELETE /voices/{id}` in
      `api/main.py`, storing files via `worker/voice_storage.py` and metadata in a
      new `voices` Mongo collection (`{_id, name, languages, created_at}`) —
      verified against a real upload: `POST /voices` with an actual WAV
      (`voices/geo.es.wav`) landed at
      `MEDIA_ROOT/voices/{id}/voice.es.wav` byte-identical to the source, and
      `GET /voices` listed it correctly
- [x] 2.2 Verify sample-deletion rules against real data: deleting a voice's only
      sample returns 422 and leaves it untouched; adding a second language then
      deleting the first succeeds and `GET /voices` reflects exactly the remaining
      one; deleting a whole voice removes its Mongo doc and its entire media
      directory (confirmed gone on disk afterward)
- [x] 2.3 Verify non-WAV uploads are rejected with a 422 before any file is
      written or voice created

## 3. Render pipeline plumbing

- [x] 3.1 Thread `voice_id: str | None = None` through `ScriptIn`,
      `AudioGenerationWorkflowInput`, `SynthesizeInput` (`worker/types.py`), the
      one additional field mapped in `AudioGenerationWorkflow.run`
      (`worker/workflows.py`), and `worker/activities.py::synthesize` building
      `RenderJob(voice_family=voice_family_path(...) if input.voice_id else None)`
      — verified via a real end-to-end render: submitted a script with a real
      uploaded voice selected, and `gpu-worker`'s own logs confirmed
      `narrator.voices`'s `resolve_voice()` picked the exact uploaded file
      (`voices[es]: using per-language sample /data/media/voices/{id}/voice.es.wav`)
      and Chatterbox actually computed voice conditioning from it — the first real
      voice-cloned render this app has ever produced
- [x] 3.2 Add `voice_id` validation (must reference an existing voice, when
      provided) shared between `create_script` and `regenerate_script` via a new
      `_validate_script_in` helper
- [x] 3.3 Add `voice_id` to `regenerate_script`'s `_AUDIO_AFFECTING_RENDER_FIELDS`
      — verified against real data: editing only an ID3 tag with the same voice
      selected still took the tags-only fast path (`audio_regenerated: false`,
      same `render_job_id`); editing only the voice selection (uploading a second
      real voice and switching to it) correctly triggered the full path
      (`audio_regenerated: true`, new `render_job_id`), and the resulting render's
      logs confirmed the *new* voice's sample was the one actually resolved
- [x] 3.4 `GET /scripts/{id}` (`ScriptDetailOut`) returns the render job's
      `voice_id` so the edit form pre-selects the currently-used voice — verified
      the field round-trips correctly before and after a voice change

## 4. Frontend

- [x] 4.1 Build `web/src/Voices.jsx`: create-voice form (name + language + WAV
      file), per-voice sample list with inline `<audio>` preview (served from the
      existing `/media` static mount), add-another-sample control, confirm-gated
      delete for both a single sample and a whole voice — verified via a real
      headless-browser session against the app's actual live data (the user's own
      uploaded "Geo - ES"/"Geo - EN" voices): both voices listed with working
      audio preview elements
- [x] 4.2 Add a voice `<select>` to the shared `web/src/ScriptForm.jsx` (fetched
      from `GET /voices`, same lifecycle as the existing series dropdown) plus a
      "Manage voices" link, and add `"voice_id"` to `EditScript.jsx`'s
      `AUDIO_AFFECTING_EXACT_FIELDS` so the destructive-cascade confirm dialog
      gates correctly on a voice change too — verified via Playwright: the upload
      form's voice dropdown listed the real voices already in the database
      ("(Engine default)", "Geo - EN", "Geo - ES")
- [x] 4.3 Wire `?view=voices` into `web/src/main.jsx`'s router and add a "Manage
      voices" link from `Dashboard.jsx` — verified the link navigates correctly
      and the screen renders real data

## 5. Documentation

- [x] 5.1 This proposal/design/spec-delta set, written and archived alongside the
      implementation above, adding a new `api/voices` capability and extending
      `api/scripts`/`workflow/audio-generation` — not left to drift, per the
      standing instruction this session.
