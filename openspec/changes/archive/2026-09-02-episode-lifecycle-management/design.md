## Context

See proposal.md for motivation. Relevant existing state: `scripts` → `render_jobs`
(1:1 today, enforced only by convention — nothing prevented a second render_job for
the same script until this change) → `video_jobs` (1:N-capable, since
`POST /video_jobs` could already be called twice against the same render job).
`render_jobs`/`video_jobs` documents are already deletable-in-principle rows with no
foreign-key enforcement (MongoDB), so cascade behavior is entirely
application-level, not database-enforced.

## Goals / Non-Goals

**Goals:**
- Let the database's actual contents be browsable and actionable from the UI
  (list, play back, edit, delete) without the client already knowing an id.
- Make "edit a script" safe by construction: never leave a `render_jobs`/
  `video_jobs` document that describes work done against text that no longer
  matches the script.

**Non-Goals:**
- Keeping render/video history. Regenerating or deleting a script discards the
  prior render/video work outright rather than archiving it — this is a
  personal-scale tool (RFC's own stated scale) where re-running a render is cheap,
  and keeping orphaned historical rows around with no UI to browse them would be
  clutter, not a feature.
- A first-class `series` collection. See Decisions.
- Any change to `VideoProductionWorkflow`'s own state machine or
  `generate_metadata`/`correctness_check`.

## Decisions

**Cascade delete/regenerate is synchronous and best-effort on workflow
termination, not itself a Temporal workflow.** Deleting or regenerating a script
touches at most a handful of Mongo documents and a couple of directories — there's
no need for the durability/retry guarantees a workflow provides, and adding one
would mean two different "delete" code paths (interactive DELETE-triggered vs.
workflow-driven) for no benefit. Workflow termination
(`Client.get_workflow_handle(...).terminate()`) is wrapped in a broad `except
Exception` and treated as informational, not fatal — the workflow may have already
completed (nothing to terminate) or never started, and either way must not block
deleting the Mongo docs/files, since a user who asked to delete something wants it
gone regardless of an unrelated workflow's state.

**Regenerate reuses the delete cascade rather than duplicating it.**
`_delete_render_jobs_for_script(script_id)` removes render_jobs/video_jobs (with
their media and workflows) but leaves the `scripts` document itself alone; `DELETE
/scripts/{id}` calls it and then deletes the script too, `PUT
/scripts/{id}/regenerate` calls it and then starts a fresh render. One cascade
implementation, two callers.

**Series are derived from `scripts.series_name`, not a stored entity.** The
alternative — a `series` collection with its own documents, created when a user
picks "+ New series" and deleted when its last script is removed — was considered
and rejected: it would need to stay in sync with `scripts.series_name` on every
create/edit/delete, doubling the surface area for the exact bug this change is
trying to close (state that can drift from what's actually true). Deriving `GET
/series` as `scripts.distinct("series_name")` makes "delete the last episode of a
series deletes the series" true by construction, with no cleanup code to write or
forget.

**`render_jobs.progress`/`audio_url` are plain incremental Mongo writes from
inside the `synthesize` Activity, not separate Activity calls.** Matches the
existing pattern in the same function (writing `script.txt`, applying ID3 tags) —
these aren't workflow-visible state transitions Temporal needs to know about, just
incremental detail on the already-current `"rendering"`/`"complete"` status. The
`render_job()` progress callback added to `src/narrator/batch.py` is a function
parameter, not a `RenderJob` dataclass field, because `RenderJob` instances are
pickled through `multiprocessing.Queue` in narrator's own CLI batch path
(`run_batch()`/`_worker()`) — a closure capturing a Mongo client wouldn't survive
that.

## Risks / Trade-offs

- **[Risk] A script edited mid-render terminates a workflow that was about to
  succeed, discarding real progress.** → Accepted: the user asked for exactly this
  behavior ("if there is a video associated to it, transcription and video
  generation need to be redone" generalizes to "editing invalidates in-flight work
  against the old text"), and mid-render edits are a deliberate user action, not
  something that happens accidentally.
- **[Risk] `terminate()`'s broad exception handling could mask a real Temporal
  connectivity problem as "nothing to terminate."** → Accepted for now: the
  operation still completes (Mongo docs/files are deleted either way) and the
  failure mode is "an orphaned workflow execution visible in Temporal's own Web UI,"
  not data corruption — recoverable by an operator, not silent data loss.
- **[Risk] No confirmation step server-side** — `DELETE`/`regenerate` execute
  immediately on request, relying entirely on the frontend's `confirm()` dialogs.
  → Accepted: this is a single-operator, personal-scale tool (RFC's stated scope,
  no auth), matching every other destructive-action pattern already in this
  codebase.
