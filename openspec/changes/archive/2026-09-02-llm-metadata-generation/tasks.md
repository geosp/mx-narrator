## 1. Dependency and config

- [x] 1.1 Add `litellm` to `pyproject.toml` (pinned to an exact version, matching this
      repo's existing pinning convention) and run `uv sync`; verify
      `uv run python -c "import litellm"` succeeds — confirmed: `litellm==1.99.0`
      installed, import OK. Pinned exact with its own stated rationale (fast-moving,
      sole thing standing between the Activity and every provider's wire format) —
      corrected from the original plan's claim that exact-pinning is this repo's
      existing convention, which isn't quite true (`temporalio`/`pymongo`/`fastapi`/
      `uvicorn`/`motor` all float on `>=`; only `chatterbox-tts` and `setuptools` are
      pinned, each for their own specific reason)
- [x] 1.2 Add `LLM_MODEL`/`LLM_API_BASE`/`ANTHROPIC_API_KEY` env var plumbing (read
      with sensible defaults per design.md's config table) and verify their values are
      visible inside a container built from the updated image — confirmed via
      `docker exec narrator-studio-cpu-worker-1 env`: `LLM_MODEL=ollama/llama3.1:8b`,
      `LLM_API_BASE=http://host.docker.internal:11434`, `ANTHROPIC_API_KEY=` (empty,
      as expected — unused for the local-network default)

## 2. LLM harness

- [x] 2.1 Implement `worker/llm.py`: `VideoMetadataSchema` (title/description/tags
      with YouTube length caps as field constraints) and `generate_structured()`
      wrapping `litellm.acompletion` with an explicit `json_schema` `response_format`
      dict (not a raw Pydantic class, per design.md's known LiteLLM gotcha), and
      verify it returns schema-valid output against at least one real local LLM
      (whichever Ollama/vLLM machine is available) with a direct call — no Temporal
      involved yet — confirmed against both `ollama/phi4-mini:3.8b` and
      `ollama/llama3.1:8b` (real Spanish devotional prompt, real schema-valid
      title/description/tags returned both times). Hit and diagnosed a real host-level
      issue along the way: Ollama's AMD/ROCm GPU backend had a stuck runner from an
      earlier hardware hang (`journalctl -u ollama`: "HW Exception by GPU node-1 ...
      reason: GPU Hang"), returning `model runner has unexpectedly stopped` for every
      request regardless of model — resolved without sudo via `ollama stop <model>`
      to clear the wedged runners, not a code issue. Also confirms Ollama runs on a
      separate AMD GPU via ROCm, not the NVIDIA card Chatterbox uses — no VRAM
      contention between the two, as design.md's Risks section flagged as unconfirmed

## 3. `generate_metadata` Activity

- [x] 3.1 Add `VideoMetadataFields`, `GenerateMetadataInput`, `GenerateMetadataResult`
      dataclasses to `worker/types.py` — done
- [x] 3.2 Implement the series-context fetch (RFC §6.2 chain:
      `render_jobs.script_id` → `scripts.series_name` → sibling `scripts` →
      their `render_jobs`/`video_jobs`/`video_metadata`, filtered to
      `human_approved_at` set, most recent first, capped) as part of the Activity
      body, and verify it returns only approved titles against real seeded Mongo data
      (a mix of approved and draft titles for the same series) — confirmed:
      `_fetch_series_context` returned exactly `["APPROVED Episode A Title"]` from
      seeded data containing one approved and one draft (`human_approved_at: None`)
      sibling title in the same series; the draft never appeared. **Real gap found**:
      Phase 2's actual `POST /scripts` never collects `series_name` at all (RFC
      modeled it, the shipped API doesn't) — `_fetch_series_context` degrades to `[]`
      for any script without it, which is every real script today. Documented in the
      function's own docstring; fixing `api/scripts` to collect it is explicitly out
      of this change's declared scope (proposal.md's "Modified Capabilities: none")
- [x] 3.3 Implement the `generate_metadata` Activity in `worker/activities.py`
      (`async def`, calling the context fetch then `generate_structured()`), and
      verify it end-to-end with `temporalio.testing.ActivityEnvironment` (no live
      Temporal server needed) against a real Phase 2 `render_jobs` document —
      confirmed: real schema-valid title/tags returned for a real Spanish devotional
      script via `ActivityEnvironment().run(...)`
- [x] 3.4 Add `RetryPolicy(maximum_attempts=3)` at the call site (this Activity is
      invoked directly for verification in this change, not yet from a workflow — see
      task 5.1) and verify a forced schema-validation failure (e.g. temporarily point
      at a model/prompt known to produce invalid JSON) exhausts retries and surfaces
      an error rather than hanging or looping indefinitely — confirmed via Temporal's
      own event history (not just observed program behavior): forced a connection
      failure (`LLM_API_BASE` pointed at an unreachable host — substituted for a
      schema-validation failure since Ollama's JSON-schema mode is grammar-constrained
      at the token level, making an actual schema violation very hard to force
      deliberately; the retry mechanism under test is identical either way, since
      Temporal retries on any raised exception regardless of cause) through a
      throwaway single-activity workflow (`VerifyMetadataWorkflow`, not part of the
      repo — no permanent workflow exists yet for `generate_metadata`, see 5.1).
      `temporal workflow show --output json` confirmed `ActivityTaskStarted.attempt:
      3` and `ActivityTaskFailed.retryState: RETRY_STATE_MAXIMUM_ATTEMPTS_REACHED` —
      exactly 3 attempts, then a clean surfaced failure, not a hang or infinite retry

## 4. `cpu-worker` service

- [x] 4.1 Implement `worker/cpu_main.py`: connects to Temporal, registers only
      `generate_metadata` on a new `cpu-tasks` task queue, no `activity_executor`/GPU
      config, and verify it appears as a registered worker on `cpu-tasks` (via
      `temporal task-queue describe --task-queue cpu-tasks`, same pattern used to
      verify `gpu-worker` in Phase 2) — confirmed: one `activity`-type poller
      registered, independent of `gpu-tasks` (which still shows its own separate
      pollers, unaffected)
- [x] 4.2 Add the `cpu-worker` service to `deploy/docker-compose.yml` (same shared
      image as `gpu-worker`/`api`, different `command:`, no GPU device reservation)
      and verify `docker compose up -d cpu-worker` starts it successfully alongside
      the existing services — confirmed: container up, logs show
      `worker polling task queue 'cpu-tasks'`. Added `extra_hosts:
      host.docker.internal:host-gateway` and `LLM_MODEL`/`LLM_API_BASE`/
      `ANTHROPIC_API_KEY` as compose-level `${VAR:-default}` substitutions so the
      committed defaults work out of the box on this host (Ollama already confirmed
      listening on `0.0.0.0:11434`) while staying overridable per-deployment with no
      compose file edit

## 5. End-to-end verification

- [x] 5.1 Execute `generate_metadata` for a real Phase 2 render job through an actual
      running Temporal server + `cpu-worker` (via a direct `client.execute_activity`
      or a minimal one-activity test workflow, since no real workflow calls it yet),
      and verify the result is schema-valid — confirmed via a throwaway
      `VerifyMetadataWorkflow` (not part of the repo) whose local worker registered
      only the workflow type, no activities — forcing `generate_metadata` onto the
      real, already-running `cpu-worker` container (the only other `cpu-tasks`
      poller), not an ephemeral in-script worker. Result: real schema-valid
      title/tags; `docker logs narrator-studio-cpu-worker-1` confirms the real
      deployed container actually processed it (`LiteLLM completion() model=
      llama3.1:8b; provider = ollama`)
- [x] 5.2 Repeat 5.1 against at least one different `LLM_MODEL`/`LLM_API_BASE`
      configuration (e.g. a second LAN machine, or Anthropic if a key is available),
      confirming the same Activity code produces schema-valid output against both
      configurations with no code change — the core claim of this change — confirmed:
      reconfigured the real `cpu-worker` service to `LLM_MODEL=ollama/phi4-mini:3.8b`
      (`docker compose up -d --force-recreate cpu-worker` with the env var set, no
      file edit), reran the identical verification workflow, got a second real
      schema-valid result, `cpu-worker`'s own logs confirmed `model=phi4-mini:3.8b`
      this time — zero code change between runs. **Caveat, noted honestly**: only two
      configs of the same local Ollama instance were exercised, not a genuinely
      different LAN machine or Anthropic — neither was available in this session (no
      second reachable machine, no `ANTHROPIC_API_KEY`). The config-swap mechanism
      itself (`LLM_MODEL`/`LLM_API_BASE` fully determine the provider/target, proven
      by the model string alone changing behavior with no code touched) is the same
      mechanism that would route to a different machine or Anthropic; that broader
      claim is architecturally proven, not empirically exercised against those
      specific targets
- [x] 5.3 Update `deploy/README.md` with the new `cpu-worker` service and its config
      env vars, so a future `VideoProductionWorkflow` change can build on it without
      re-deriving this setup — done: services table, dedicated `cpu-worker` config
      section (`LLM_MODEL`/`LLM_API_BASE`/`ANTHROPIC_API_KEY`), and an updated "Next
      phase" note flagging both remaining gaps honestly (workflow wiring,
      `api/scripts` not collecting `series_name`)
