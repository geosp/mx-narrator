## Context

See proposal.md for motivation. Key constraint: Temporal signals only reach an
*open* workflow execution. `ready_for_manual_upload` and `failed` are terminal —
`VideoProductionWorkflow.run()` has already returned by then, so there is no
running execution left to signal. Revising captions after approval has to start
a new workflow execution, not resurrect a closed one — the same shape of
decision `regenerate_script` already made for script edits.

## Goals / Non-Goals

**Goals:**
- Let a caption correction discovered after approval actually reach the video
  file, not just the stored SRT text.
- Avoid redoing work that doesn't depend on caption wording (transcription, the
  correctness check, metadata regeneration when metadata's already approved).

**Non-Goals:**
- Editing captions *during* a still-open workflow execution by other means
  (e.g. a generic "amend" signal) — the closed-execution case is the actual
  gap; a still-open execution already has `approve_srt`/`approve_metadata` to
  work with at the right moment.
- Versioning/history of prior caption revisions — each revise overwrites the
  SRT file and re-renders in place, matching how the first approval already
  works (`finalize_srt` has always overwritten in place, no versioning).

## Decisions

**A new workflow type (`ReviseCaptionsWorkflow`), not a generic "resume
VideoProductionWorkflow from a later step."** Temporal workflows don't support
resuming a closed execution partway through; the only way to redo a tail
portion is a new execution. Re-running the *entire* original workflow
(including transcription) was considered and rejected — re-transcribing would
regenerate a fresh Whisper transcript from the audio, discarding the human's
edit entirely, which is backwards.

**Duplicating the `approve_metadata` signal + tail orchestration, not
extracting a shared base class.** Temporal signals are scoped to one running
execution's type, so `ReviseCaptionsWorkflow` needs its own copy to support
metadata review when metadata wasn't approved yet. A cross-class mixin for
Temporal signal handlers is plausible in the Python SDK but unconfirmed in this
codebase, and `VideoProductionWorkflow` is a real, currently-in-use workflow —
not worth risking a refactor of to save roughly fifteen lines. Both copies call
the exact same unchanged `render_video`/`generate_metadata`/
`save_metadata_draft`/`approve_metadata` activities, so they can't drift on
*what* happens, only orchestration order.

**`metadata_already_approved` is decided by the API layer (a `video_metadata`
query) before starting the workflow, not by a workflow-side query activity.**
Simpler — one Mongo read in a place that's already reading `video_jobs`/
`render_jobs` for the same request, versus adding a new activity purely to
branch on one boolean.

**`video_jobs.active_workflow_id` tracking.** Discovered as a real, necessary
gap while designing this: `POST /video_jobs/{id}/metadata/approve` hardcoded
`video-prod-{id}` as the workflow to signal. Once a revise workflow can also be
the one waiting on that signal, the endpoint needs to know which execution is
actually current. Set at `create_video_job` (`video-prod-{id}`) and at each
revise (`video-revise-{id}`, a fixed/reused ID — revises are sequential human
actions, and Temporal's default ID-reuse policy allows starting a new run once
the previous one with that ID has closed).

## Risks / Trade-offs

- **[Risk, realized during verification] Registering a new workflow *class* is
  a two-step change (import it, *and* add it to the `Worker(...)` registration
  list) — the first real revise attempt only did the import.** Result:
  `WorkflowTaskFailed` (`NotFoundError: Workflow class ReviseCaptionsWorkflow is
  not registered on this worker`), retried by Temporal indefinitely with zero
  effect — `video_jobs.status` never changed, silently masking the failure as
  "nothing happened yet" rather than an obvious error. Caught by checking the
  real workflow execution history (`temporal workflow show`), not by trusting
  the apparent status. Fixed by adding the class to `worker/main.py`'s
  `workflows=[...]` list; re-verified with a real end-to-end revise
  afterward.
- **[Risk] `active_workflow_id`'s fixed, reused ID per video job means two
  concurrent revises (e.g. two browser tabs) would race.** → Accepted: this is
  a personal, single-operator tool (RFC's stated scope); the second request's
  `start_workflow` would either fail against a still-open first execution or
  the `_terminate_workflow` best-effort call would cancel the first — either
  way, not silent data corruption, and not a realistic usage pattern here.
