## Context

See proposal.md for motivation. `episode-lifecycle-management`'s design.md already
flagged "`video_jobs.status` never reaches `failed`" as a known, deliberately
deferred gap; this change hits that exact gap for real during its own
verification (see Risks) and closes it as part of the same pass, since it's
directly in the code being extended.

## Goals / Non-Goals

**Goals:**
- A real, playable MP4 with correct audio and selectable captions.
- `generate_metadata` finally wired in, with `_fetch_series_context` receiving
  real data for the first time.
- Failures in the new unattended span (ffmpeg, LLM call) are recorded, not
  silently stuck.

**Non-Goals:**
- Burned-in subtitles, subtitle styling, or multiple subtitle languages.
- Any YouTube API integration — `ready_for_manual_upload` is terminal by design
  (RFC §7.2), confirmed again this change.
- Editing metadata after `human_approved_at` is set (RFC's own data model has no
  "unapprove" — a fresh video production run would be the way to redo it, out of
  scope here).

## Decisions

**Soft subtitles (`mov_text`), not burned-in.** Matches the RFC's own wording
exactly ("mux audio + soft subtitle track") and avoids needing libass/fontconfig
inside the container — a real dependency-surface cost for a feature (styled
burned-in captions) nobody asked for.

**`render_video`/`save_metadata_draft`/`approve_metadata` all run on `cpu-tasks`,
explicit `task_queue` overrides on each `execute_activity` call.** None of these
are GPU-bound (ffmpeg muxing here does no encoding-heavy work — it's a straight
mux/remux — and the two Mongo-write activities are trivial), so routing them to
`gpu-tasks` (the workflow's default queue) would needlessly make them wait behind
in-flight synthesis on a single-GPU host, the same reasoning `correctness_check`
and `generate_metadata` already established.

**`generate_metadata` itself is untouched.** Wiring it in is entirely additive —
two new Activities (`save_metadata_draft`, `approve_metadata`) sit around it to
persist a draft and then the approved version, rather than modifying the
Activity `llm-metadata-generation` already built and verified to compute-and-return
only. Smallest possible integration surface.

**Failure handling added for the new span, not the whole workflow.** The
transcription/correctness-check/SRT-review portion already has its own error
posture (a mismatch is a *review* state, not a failure); only the newly-added
`render_video` → `generate_metadata` → `save_metadata_draft` sequence is
unattended system work with a real, previously-unhandled failure mode, so the
`try/except` wraps exactly that span — mirroring `AudioGenerationWorkflow`'s
existing pattern for `synthesize`, not inventing a new one.

## Risks / Trade-offs

- **[Risk, realized during verification] `cpu-worker` had no access to
  `MEDIA_ROOT` at all.** It was only ever used for `generate_metadata` (an LLM
  HTTP call) and `correctness_check` (pure text diffing) — neither touches files.
  The first real `render_video` run failed with "No such file or directory" for
  the background image, which existed fine on the `media-data` volume but wasn't
  mounted into this service. Fixed by adding `MEDIA_ROOT` and the volume mount to
  `cpu-worker` in `deploy/docker-compose.yml`. Verified by rebuilding and rerunning
  the exact same episode end-to-end successfully afterward, plus `ffprobe`
  confirming a correct video/audio/`mov_text`-subtitle MP4.
- **[Risk] Low framerate (`-r 1`) output could look wrong in some players that
  expect a higher minimum framerate.** → Accepted for now: YouTube and standard
  desktop/mobile players handle 1fps still-image video correctly (a common
  technique for long-form audio content); revisit only if a real player issue
  surfaces.
