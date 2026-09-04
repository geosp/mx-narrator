## 1. Retry policy constants

- [x] 1.1 Add `MONGO_WRITE_RETRY_POLICY = RetryPolicy(maximum_attempts=5)` to `worker/workflows.py`
- [x] 1.2 Add `GENERATE_METADATA_RETRY_POLICY = RetryPolicy(maximum_attempts=2)` to `worker/workflows.py`

## 2. Apply bounded retry policies

- [x] 2.1 `AudioGenerationWorkflow`: `mark_render_job` calls (3) get `MONGO_WRITE_RETRY_POLICY`
- [x] 2.2 `VideoProductionWorkflow`: every `mark_video_job` call (9), `finalize_srt`, `save_metadata_draft`, `approve_metadata` get `MONGO_WRITE_RETRY_POLICY`; `generate_metadata` gets `GENERATE_METADATA_RETRY_POLICY`
- [x] 2.3 `ReviseCaptionsWorkflow`: every `mark_video_job` call, `finalize_srt`, `save_metadata_draft`, `approve_metadata`, `reset_manually_uploaded` get `MONGO_WRITE_RETRY_POLICY`; `generate_metadata` gets `GENERATE_METADATA_RETRY_POLICY`
- [x] 2.4 Verify mechanically (parse every `execute_activity(...)` call site in `worker/workflows.py`) that all 32 calls now carry an explicit `retry_policy` — confirmed 0 missing

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Confirmed no video/render job was mid-activity (`temporal workflow describe`) before rebuild/redeploy
- [x] 3.2 Rebuilt `gpu-worker` (cache hit on the expensive `uv sync` layer — only `worker/` changed), redeployed `api`/`cpu-worker`/`gpu-worker`, confirmed clean startup of all three
- [x] 3.3 Ran a full real episode through `AudioGenerationWorkflow` + `VideoProductionWorkflow` end-to-end to `ready_for_manual_upload` — confirmed zero behavior change on the happy path
- [x] 3.4 Built an isolated, throwaway `RetryProbeWorkflow` + `always_fails` activity on a dedicated `retry-probe-queue` (touching no real data) and proved via a real Temporal server round-trip that `RetryPolicy(maximum_attempts=3)` stops retrying at exactly 3 attempts (`TOTAL_ACTIVITY_ATTEMPTS: 3`, clean `ActivityError` catch) — not just under `ActivityEnvironment`, which skips wire serialization and has already been shown this session to miss real bugs
- [x] 3.5 Cleaned up the throwaway test file and the leftover test episode from the happy-path run

## 4. Docs

- [x] 4.1 `skip_specs: true` — internal reliability hardening only, no observable API/UI/data-model contract change
