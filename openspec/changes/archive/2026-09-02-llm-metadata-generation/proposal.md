## Why

The RFC's LLM-generated-YouTube-metadata step (§7.2) needs a concrete, buildable
design before `VideoProductionWorkflow` can be built around it. Phase 3 planning
surfaced that the user already has several machines on their home network capable of
running Ollama or vLLM, so the design has to be provider-agnostic (local network by
default, remote API as an explicit opt-in) rather than the RFC's original hardcoded
Anthropic-only call — see the RFC's v5 revision (§3, §5.1, §7.2, §9, §10, §13). This
piece can be built and verified standalone: `generate_metadata`'s actual inputs
(a `render_job_id`, its script text, and prior-series-title context from MongoDB) all
already exist from Phase 2, with no real dependency on the rest of
`VideoProductionWorkflow`'s stages (transcription, correctness check, SRT review,
video render), which remain undesigned and out of scope here.

## What Changes

- New `worker/llm.py`: the LLM harness — a `VideoMetadataSchema` Pydantic model
  (title/description/tags, YouTube's length caps as field constraints) and a
  `generate_structured()` function wrapping `litellm.acompletion`, config-driven via
  `LLM_MODEL`/`LLM_API_BASE`/`ANTHROPIC_API_KEY` (RFC §9). Defaults to a LAN-hosted
  Ollama model; swapping to a vLLM-served LAN machine or a remote API (e.g. Anthropic)
  is a config change only, no code change.
- New Temporal dataclasses in `worker/types.py` (`VideoMetadataFields`,
  `GenerateMetadataInput`, `GenerateMetadataResult`).
- New `generate_metadata` Activity in `worker/activities.py` — a single deterministic,
  `async def` Activity (I/O-bound HTTP call, unlike `synthesize`'s CPU/GPU-bound
  sync+heartbeat-thread pattern): fetches prior human-approved episode titles for the
  same series as prompt context, makes one structured LLM call, returns the result. No
  agent framework, no tool use, no multi-step reasoning — matches RFC §7.2's updated
  description.
- New `worker/cpu_main.py` entrypoint + `cpu-worker` Docker Compose service — a
  second, lightweight Temporal worker (no GPU device reservation) polling a new
  `cpu-tasks` task queue, so `generate_metadata` doesn't serialize behind in-flight
  GPU synthesis on `gpu-worker`'s `max_concurrent_activities=1` queue. Reuses the
  existing shared image (`narrator-studio/gpu-worker:local`), different `command:`,
  same pattern already used for the `api` service.
- New `litellm` dependency (pinned exact version) in `pyproject.toml`/`uv.lock`.

## Capabilities

### New Capabilities
- `workflow/metadata-generation`: the `generate_metadata` Temporal Activity and its
  LLM harness — given a render job's script and series context, produces
  schema-valid YouTube title/description/tags via a configurable local-or-remote LLM
  provider.

### Modified Capabilities
(none — this is additive: a new Activity, a new worker service, a new dependency.
`workflow/audio-generation` and `api/scripts` from Phase 2 are unaffected; no existing
requirement's behavior changes.)

## Impact

- New code: `worker/llm.py`, additions to `worker/types.py` and
  `worker/activities.py`, `worker/cpu_main.py`.
- Extends (does not modify) `deploy/docker-compose.yml`: new `cpu-worker` service.
- Extends (does not modify) `pyproject.toml`/`uv.lock`: new `litellm` dependency.
- No changes to `src/narrator/` internals, `AudioGenerationWorkflow`, or the `synthesize`
  Activity.
- Depends on Phase 2's infra being up (`temporal`, `mongo` reachable) and at least one
  real `render_jobs` document existing to test against.
- Not yet wired into any workflow — `VideoProductionWorkflow` itself (which will call
  `generate_metadata` as one of its stages, per RFC §7.2) is a separate, future change
  once the workflow's earlier stages (transcription, correctness check, SRT review,
  video render) are designed.
