## Why

The RFC's rollout plan (§14) names a "hardening pass — secrets management,
error/retry policy tuning, worker resource limits" as its fourth and final
phase; it was never done as a dedicated pass. Auditing `worker/workflows.py`:
only `synthesize`, `transcribe`, `correctness_check`, and `render_video` had
an explicit, bounded `RetryPolicy`. Every other `execute_activity` call —
`mark_render_job`, `mark_video_job` (used ~9 times across two workflows),
`finalize_srt`, `generate_metadata`, `save_metadata_draft`,
`approve_metadata`, `reset_manually_uploaded` — had none, meaning Temporal's
*unbounded* default retry applied. This is the exact bug class that caused
three separate real incidents this session (most recently `render_video`'s
missing heartbeat, and before that a nested-dataclass wire-serialization bug
in `mark_video_job`) — a deterministic bug in any of these activities would
retry silently forever with growing backoff instead of surfacing as a
failure.

## What Changes

- Two new shared `RetryPolicy` constants in `worker/workflows.py`:
  `MONGO_WRITE_RETRY_POLICY` (`maximum_attempts=5`, for the small idempotent
  Mongo/file writes) and `GENERATE_METADATA_RETRY_POLICY`
  (`maximum_attempts=2`, for the one activity that calls an external LLM
  endpoint).
- Applied to all 32 `execute_activity` calls across `AudioGenerationWorkflow`,
  `VideoProductionWorkflow`, and `ReviseCaptionsWorkflow` — every call now has
  an explicit, bounded retry policy; none rely on Temporal's unbounded
  default anymore. Verified mechanically (a small script parsing every
  `execute_activity(...)` call site) that none were missed.
- No timeout values changed — retry-policy only, per the approved scope.
  Resource limits and secrets management stay out of scope for this pass.

## Capabilities

No capability changes. This is an internal reliability hardening measure, not
a change to any observable API/UI/data-model contract — the happy path is
byte-for-byte unchanged (verified with a real episode through the full
pipeline), and the *existing* documented guarantee ("failures are recorded,
not silently lost," already specified for the primary risky activities in
`workflow/audio-generation` and `workflow/video-production`) is made more
robust across more activities, not replaced with a new one. `skip_specs:
true` accordingly, rather than inventing a new requirement for what's
fundamentally a defense-in-depth implementation detail.

## Impact

- `worker/workflows.py` only.
- Verified via an isolated, throwaway Temporal workflow (not touching any
  real data) that `RetryPolicy(maximum_attempts=N)` genuinely caps retries at
  N through a real server round-trip, not just `ActivityEnvironment` (which
  skips wire serialization and has already been shown this session to miss
  real bugs) — confirmed exactly 3 attempts, then a clean `ActivityError`
  catch, for a deterministically-failing activity.
- Verified a real episode through both `AudioGenerationWorkflow` and
  `VideoProductionWorkflow` end to end with no behavior change.
