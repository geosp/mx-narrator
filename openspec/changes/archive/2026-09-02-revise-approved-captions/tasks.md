## 1. Workflow and activities

- [x] 1.1 Add `ReviseCaptionsWorkflowInput` (`worker/types.py`) and
      `reset_manually_uploaded` (`worker/activities.py`, registered on
      `cpu-tasks` in `worker/cpu_main.py`)
- [x] 1.2 Implement `ReviseCaptionsWorkflow` (`worker/workflows.py`):
      `mark_video_job("rendering")` → `finalize_srt` → `render_video` → branch
      on `metadata_already_approved` (skip straight to
      `ready_for_manual_upload`, resetting manually-uploaded, vs. regenerate
      metadata and wait for approval again) → same `failed`-on-`ActivityError`
      handling as `VideoProductionWorkflow`
- [x] 1.3 **Real bug found and fixed**: registered the new workflow class in
      `worker/main.py`'s import but not in its `Worker(...)` registration list
      — the first real revise attempt failed immediately
      (`WorkflowTaskFailed: NotFoundError: Workflow class ReviseCaptionsWorkflow
      is not registered on this worker`), retried indefinitely by Temporal with
      zero visible effect (`video_jobs.status` never changed, masking the
      failure as "nothing happened"). Caught by checking the real workflow
      execution history directly rather than trusting the apparent status.
      Fixed by adding it to the registration list; re-verified with a real
      end-to-end revise afterward, confirmed via `WorkflowExecutionCompleted`
      in the workflow history

## 2. API

- [x] 2.1 Add `video_jobs.active_workflow_id`, set in `create_video_job`
      (`video-prod-{id}`) — verified present on a real newly-created video job
- [x] 2.2 Implement `POST /video_jobs/{id}/srt/revise` — validates via
      `srt.parse()`, restricts to `metadata_review_pending`/
      `ready_for_manual_upload`/`failed`, best-effort terminates the previous
      workflow, updates `active_workflow_id`, starts `ReviseCaptionsWorkflow`
- [x] 2.3 Fix `POST /video_jobs/{id}/metadata/approve` to read
      `active_workflow_id` instead of hardcoding `video-prod-{id}` — verified
      directly: revised captions on a video job before metadata was ever
      approved, confirmed `active_workflow_id` had updated to
      `video-revise-{id}`, then approved metadata and confirmed the signal
      reached that execution (not a stale reference to the closed original) —
      the workflow completed with the human-edited title/description/tags
      correctly recorded

## 3. End-to-end verification against real data

- [x] 3.1 Full episode to `ready_for_manual_upload`, marked manually uploaded,
      then revised — confirmed via a real frame extraction
      (`ffmpeg -frames:v 1`) that the corrected caption text is genuinely
      burned into the re-rendered MP4, status returned to
      `ready_for_manual_upload`, `manually_uploaded` reset to `false`, and the
      approved title was unchanged
- [x] 3.2 Revised captions before metadata was ever approved — confirmed it
      went through `generate_metadata` again and landed back at
      `metadata_review_pending` (see 2.3 for the approval-signal follow-through)
- [x] 3.3 Simulated a `failed` video job and revised — confirmed it recovered
      cleanly to `ready_for_manual_upload`, acting as a working retry path
- [x] 3.4 Full real Playwright session through the actual web UI: original
      approve flow end to end (SRT approve → wait for render/metadata →
      approve metadata → `ready_for_manual_upload`), then the new "Revise
      captions" toggle, editing text through the same synced per-caption UI
      and resubmitting — confirmed the episode returned to
      `ready_for_manual_upload` and the revised text was confirmed via
      `GET /video_jobs/{id}/srt` afterward

## 4. Documentation

- [x] 4.1 Proposal, design, and spec delta written and archived alongside the
      implementation and the real bug fix above — not left to drift, per the
      standing instruction this session.
