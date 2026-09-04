## Why

`voices/` has held Chatterbox reference samples (`geo.en.wav`, `geo.es.wav`) since
before this app existed, and `src/narrator/voices.py::resolve_voice` already knows
how to pick a per-language sample or fall back to a bare "family" file. But nothing
in Narrator Studio ever set `RenderJob.voice_family` — confirmed via a full-repo
grep, `voice` appeared nowhere in `api/main.py`, `worker/types.py`, or
`worker/activities.py`. Every episode rendered through this app has used
Chatterbox's built-in default voice, never an actual cloned voice. `voices/` also
isn't copied into the worker image or mounted as a volume, so even setting
`voice_family` today would point at a path that doesn't exist in the container. The
user asked for real voice management: upload named voices through the UI, see
what's available, delete them, and pick one when creating or editing/regenerating an
episode — confirmed as upload+select via the UI, not read-only filesystem scanning.

## What Changes

- New MongoDB collection `voices`: `{_id, name, languages: [str], created_at}`.
  Uploaded samples live under the existing `MEDIA_ROOT` volume at
  `MEDIA_ROOT/voices/{voice_id}/voice.wav` (fallback) and
  `voice.{lang}.wav` (`es`/`en`/`pt`) — exactly the naming convention
  `resolve_voice()` already expects, so it's reused completely unmodified.
- New endpoints: `GET /voices`, `POST /voices` (create + first sample), `POST
  /voices/{id}/samples` (add/replace one language), `DELETE
  /voices/{id}/samples/{lang}` (422 if it's the last sample), `DELETE /voices/{id}`
  (removes the voice and all its media).
- `ScriptIn` gains an optional `voice_id`, validated against the `voices`
  collection when present, threaded through `AudioGenerationWorkflowInput` →
  `SynthesizeInput` → `synthesize`'s `RenderJob(voice_family=...)` construction —
  the same plumbing pattern already used for every other render parameter.
- `regenerate_script`'s audio-affecting field list gains `voice_id`: changing only
  the selected voice now correctly triggers the full regenerate path (from
  `tags-only-edit-fast-path`), not the tags-only fast path.
- New frontend screen `web/src/Voices.jsx` (upload, preview via inline `<audio>`,
  delete); a voice `<select>` added to the shared `web/src/ScriptForm.jsx`; a
  "Manage voices" link from the Dashboard and the script form.
- WAV-only uploads (422 otherwise) — no transcoding dependency added;
  `resolve_voice`'s per-language lookup only works within one consistent extension
  per voice family.

## Capabilities

### New Capabilities
- `api/voices`: upload, list, and delete named voice samples for Chatterbox
  cloning.

### Modified Capabilities
- `api/scripts`: script submission/edit accepts an optional voice selection, and
  changing it is treated as audio-affecting by the regenerate decision.
- `workflow/audio-generation`: the workflow resolves and applies a selected voice
  during synthesis, when one is provided.

## Impact

- `api/main.py`: `/voices*` endpoints; `ScriptIn`/`ScriptDetailOut`/
  `_start_render`/`regenerate_script` gain `voice_id`.
- `worker/types.py`: `voice_id` on `AudioGenerationWorkflowInput`/
  `SynthesizeInput`.
- `worker/workflows.py`: one more field mapped into `SynthesizeInput` in
  `AudioGenerationWorkflow.run`.
- `worker/activities.py`: `synthesize` builds `voice_family` from `voice_id` via
  the new `worker/voice_storage.py`.
- New file `worker/voice_storage.py` (import-light: only `pathlib`, shared by
  `api/main.py` and `worker/activities.py` so both agree on file layout).
- New frontend files `web/src/Voices.jsx`; changes to `web/src/ScriptForm.jsx`,
  `web/src/EditScript.jsx`, `web/src/Dashboard.jsx`, `web/src/main.jsx`.
- No changes to `src/narrator/voices.py` or any other narrator library code —
  reused exactly as designed, per this project's "orchestrate, don't modify"
  Non-Goal held throughout every prior phase.
- Not covered here: bulk-managing the two pre-existing `voices/geo.*.wav` files
  (they aren't auto-imported; re-uploading them through the new UI, if wanted, is a
  one-time manual step outside this change's scope).
