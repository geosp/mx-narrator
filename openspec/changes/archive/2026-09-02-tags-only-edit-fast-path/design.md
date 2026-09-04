## Context

See proposal.md for motivation. `episode-lifecycle-management` already established
the cascade-delete-and-regenerate mechanism (`_delete_render_jobs_for_script`,
`_start_render`) this change refines the *decision* in front of, not the mechanism
itself.

## Goals / Non-Goals

**Goals:**
- Never re-run synthesis or discard a video review for an edit that provably can't
  change the audio.

**Non-Goals:**
- Partial/incremental re-synthesis (e.g. re-rendering only changed sentences). Any
  change to `script_text` still re-renders the whole episode, same as before.
- Renaming files when `unit_id` changes. Still routed through the full regenerate
  path, conservatively — see Decisions.

## Decisions

**Field classification is a fixed, explicit tuple in `api/main.py`, not a generic
diff of the whole request body.** A generic "did anything change" diff would
misclassify `id3`/`series_name`/`series_album`/`title` changes as
regeneration-worthy, defeating the point. The fixed field list
(`_AUDIO_AFFECTING_SCRIPT_FIELDS`, `_AUDIO_AFFECTING_RENDER_FIELDS`) is the actual
contract: it names precisely the fields `synthesize`/`render_job()` read to produce
audio bytes, confirmed by reading both. `unit_id` is included even though it's not
read by the synthesis engine itself, because it's part of the output filename
(`{unit_id}.{lang}.mp3`); handling a rename without breaking `audio_path`/
`audio_url` everywhere they're referenced (SSE payloads, the dashboard listing, the
video_job's `audio_url`) is real complexity not worth taking on for what's expected
to be a rare edit — full regenerate on `unit_id` change is simple and correct, just
not maximally optimal.

**The fast path requires `render_job.status == "complete"`, with no attempt to
patch an in-flight render.** A running `AudioGenerationWorkflow`'s
`SynthesizeInput.id3` is already frozen as of `start_workflow` — Temporal workflow
inputs are immutable once started, so there's no safe way to make an in-progress
render pick up new tags without restarting it. Falling back to the full
cascade-and-regenerate path for this case is simple and correct, if not optimal;
editing tags on a still-rendering episode is expected to be rare.

**`apply_id3` moved to a new `worker/id3.py` rather than `api/main.py` importing
`worker/activities.py` directly.** `worker/activities.py` imports `narrator.batch`,
`worker.transcription` (faster-whisper), and `worker.llm` (litellm) — pulling all of
that into the API process's import graph for one small helper function would be a
real, avoidable cost (slower API cold start, an unnecessarily wide dependency
surface for a process that otherwise never touches ML models directly). This
mirrors the existing rationale for `worker/types.py` staying import-light for the
same reason.

## Risks / Trade-offs

- **[Risk] The frontend's field-diff (for gating the confirm dialog) and the
  backend's field-diff (for the actual decision) are two independent
  implementations that could drift.** → Accepted: the frontend copy is UX-only
  (deciding whether to show a warning), the backend copy is the actual source of
  truth for what happens. If they drift, the worst case is a confirm dialog that's
  wrong about what will happen, not incorrect data loss — the backend still decides
  correctly regardless of what the dialog said.
