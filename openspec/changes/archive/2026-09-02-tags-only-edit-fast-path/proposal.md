## Why

`episode-lifecycle-management`'s "Editing a script discards stale render and video
work" requirement was written without an exception: any edit at all — including
fixing a typo in an ID3 tag — triggers the full cascade (terminate workflow, delete
render_job/video_job/media, re-run TTS synthesis). ID3 tags, `series_name`,
`series_album`, and `title` don't affect the synthesized audio bytes at all
(`series_album`/`title` don't even survive into the file today — they only seed a
transient default tag that `apply_id3()` immediately overwrites). Treating a tag fix
the same as a script rewrite wastes GPU-bound synthesis time and destroys a
perfectly good, already-approved video review over a metadata typo.

## What Changes

- `PUT /scripts/{id}/regenerate` now inspects which fields actually changed. If none
  of `unit_id`, `lang`, `script_text`, `engine_name`, `speed`, `exaggeration`,
  `cfg_weight`, `seed` differ from the current script/render_job (and the render_job
  is `"complete"`), it rewrites the existing MP3's ID3 tags in place and leaves the
  render_job and video_job — and any in-flight workflow — completely untouched. Any
  other change still takes the existing full cascade-and-regenerate path.
- The response now includes `audio_regenerated: bool` so callers can tell which path
  ran.
- The frontend's destructive-cascade confirmation dialog in `EditScript.jsx` now
  only appears when a field that actually triggers regeneration has changed,
  matching the backend's decision — it no longer warns about deleting a video review
  that a tags-only save won't actually touch.
- `worker/activities.py`'s ID3-tag-writing logic moved to a new, lightweight
  `worker/id3.py` (no heavy ML/LLM dependencies) so `api/main.py` can call it
  directly for the in-place rewrite without importing `worker/activities.py`'s full
  dependency graph.

## Capabilities

### Modified Capabilities
- `api/scripts`: replaces "Editing a script discards stale render and video work"
  with a version scoped to audio-affecting fields, and adds the tags-only fast-path
  requirement.

## Impact

- `api/main.py`: `regenerate_script` gains the field-diff decision and the fast
  path; response model changes from `ScriptOut` to `RegenerateOut` (adds
  `audio_regenerated`).
- `worker/activities.py`: `_apply_id3` removed (moved to `worker/id3.py` as
  `apply_id3`); `synthesize` now imports it from there.
- New file `worker/id3.py`.
- `web/src/EditScript.jsx`: client-side field diff gates the `confirm()` dialog;
  warning copy reworded to distinguish tag edits (safe) from content/voice edits
  (destructive).
- No change to `VideoProductionWorkflow`, `AudioGenerationWorkflow`, or any other
  capability.
