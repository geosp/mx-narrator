## Context

Phase 2 (archived) established the FastAPI + Temporal + MongoDB integration pattern
and the shared `narrator-studio/gpu-worker:local` image. This change adds the LLM
metadata-generation piece of `VideoProductionWorkflow` (RFC §7.2) standalone, since
its actual inputs (a render job's script text, plus prior-series-title context from
MongoDB) already exist from Phase 2 and don't depend on the workflow's earlier stages
(transcription, correctness check, SRT review, video render — still undesigned). See
proposal.md for motivation; RFC §7.2/§9/§10/§13 (v5) for the target design this change
implements.

## Goals / Non-Goals

**Goals:**
- A single, deterministic Temporal Activity (`generate_metadata`) that produces
  schema-valid YouTube title/description/tags — no agent framework, no tool use, no
  multi-step reasoning (RFC §7.2's explicit framing).
- LLM provider and target machine fully config-driven (`LLM_MODEL`/`LLM_API_BASE`),
  defaulting to a LAN-hosted model (Ollama or vLLM, on any of the user's several home
  network machines), with a remote API (e.g. Anthropic) as an explicit opt-in.
- A lightweight worker path (`cpu-worker`, no GPU reservation) so metadata generation
  never queues behind in-flight GPU synthesis.

**Non-Goals:**
- No transcription, correctness check, SRT review, or video render — those are
  separate, future `VideoProductionWorkflow` stages.
- No `VideoProductionWorkflow` itself — this change delivers the Activity/harness in
  isolation, verified directly (via `temporalio.testing.ActivityEnvironment` and a
  real Temporal server), not wired into a workflow yet.
- Not building an agent, tool-use loop, or multi-step LLM reasoning of any kind —
  explicitly decided against; see design.md Decisions and RFC §13.
- Not managing the LAN-hosted LLM's own hosting/bind-address configuration — each
  machine running Ollama/vLLM is responsible for its own reachability; this change
  only consumes whatever endpoint it's pointed at.

## Decisions

- **LiteLLM, not Pydantic AI, not a hand-rolled adapter.**
  `litellm.acompletion(model="ollama/llama3.1:8b", ...)` vs.
  `model="anthropic/claude-...", ...` — the only difference between providers is the
  model string; no "agent" concept anywhere. Pydantic AI's core primitive is literally
  named `Agent`, which fights the "no agent framework" decision conceptually even
  though it could run tool-free — rejected for that framing alone. A hand-rolled
  adapter would mean reimplementing three different providers' JSON-schema-
  constrained-decoding wire formats (Ollama's `format` field, vLLM's OpenAI-compatible
  `response_format`/`guided_json`, Anthropic's forced-tool-use trick) — a solved
  problem, not a premature abstraction to reach for a small, well-scoped library
  instead.
- **Known LiteLLM gotcha**: pass `response_format` as an explicit
  `{"type": "json_schema", "json_schema": {...model_json_schema()...}}` dict, not a
  raw Pydantic class — LiteLLM has documented inconsistency issues with the latter
  (`BerriAI/litellm#6848`, `#7561`). Parse the returned JSON string with
  `VideoMetadataSchema.model_validate_json(...)` rather than relying on LiteLLM to
  hand back a parsed object.
- **`worker/llm.py` is a separate module from `worker/types.py`.** `types.py`'s whole
  reason for existing (established in Phase 2) is that `api/main.py` imports it
  without pulling in narrator's heavy ML stack. `litellm` is a new import cost with no
  reason to load into `api` — keeping it in its own module preserves that contract.
  The LLM's raw JSON output is validated by a Pydantic model in `llm.py`, then
  converted with one line into the plain dataclass in `types.py` that actually crosses
  the Temporal boundary (matching how `SynthesizeInput`/`Result` already work,
  without needing `temporalio.contrib.pydantic`).
- **`generate_metadata` is `async def`, unlike `synthesize`.** This Activity is
  I/O-bound (one HTTP call to a local or remote LLM endpoint), not CPU/GPU-bound —
  Temporal's Python SDK runs async activities natively, no thread-pool/heartbeat-
  thread machinery needed (that machinery exists in `synthesize` specifically because
  `render_job()` is a long blocking call; this Activity's LLM call is comparatively
  short and awaitable).
- **A new `cpu-tasks` task queue and `cpu-worker` service, not `gpu-tasks`.**
  `gpu-worker`'s `Worker(...)` has `max_concurrent_activities=1` process-wide —
  registering `generate_metadata` there would serialize it behind in-flight
  synthesis, defeating the RFC's original intent (§5.1) of a separate lightweight CPU
  worker. `worker/cpu_main.py` registers only `generate_metadata` on `cpu-tasks`, no
  `activity_executor`/GPU config. The `cpu-worker` compose service reuses the existing
  shared image (`narrator-studio/gpu-worker:local`) with a different `command:` and no
  GPU device reservation — the same "one image, different command" pattern already
  used for `api`.
- **Bounded retries** (`RetryPolicy(maximum_attempts=3)`) on the `generate_metadata`
  Activity call, matching Phase 2's `SYNTHESIZE_RETRY_POLICY` philosophy — a schema-
  validation miss is plausibly transient/model-dependent here (smaller local models
  are more likely to violate schema constraints than larger ones or Anthropic), unlike
  `synthesize`'s deterministic bad-engine-name-style failures.
- **Config table:**

  | Env var | Default | Notes |
  |---|---|---|
  | `LLM_MODEL` | `ollama/llama3.1:8b` | LiteLLM model string with provider prefix — `ollama/<model>`, `hosted_vllm/<model>` for a vLLM OpenAI-compatible endpoint, `anthropic/claude-...` for remote. Swapping providers/machines is a config change only. |
  | `LLM_API_BASE` | none (must be set) | `http://<lan-ip>:<port>` of whichever machine is serving the model — Ollama's default port is 11434, vLLM's OpenAI-compatible server defaults to 8000. No sensible universal default since it depends on which of the user's several LAN machines is in use; irrelevant for `anthropic/*`. |
  | `ANTHROPIC_API_KEY` | unset | LiteLLM reads this natively; required only when `LLM_MODEL` selects `anthropic/*`. |

  Since the LLM-hosting machine is normally a separate physical box on the LAN, this
  is ordinary outbound network access from the `cpu-worker` container — no Docker
  networking trick (`host.docker.internal`, `extra_hosts`) needed in the common case.
  That machinery only matters if someone points `LLM_API_BASE` at Ollama/vLLM running
  on the *same* machine as Docker Compose itself (Ollama defaults to binding
  `127.0.0.1`, unreachable from Docker without a host-side `OLLAMA_HOST=0.0.0.0`
  systemd override) — a documented exception, not the design center.
- **Series-context fetch happens inside the Activity itself**, not as a separate
  Activity. Chain: `render_jobs[render_job_id].script_id` → `scripts[script_id]
  .series_name` → other `scripts` with the same `series_name` → their
  `render_jobs → video_jobs → video_metadata`, filtered to `human_approved_at` set,
  most recent first, capped (e.g. last 10) to bound prompt size for smaller local
  models' context windows. A Mongo read is cheap and fast enough that re-running it on
  a bounded LLM-call retry is a non-issue — splitting it into its own Activity would
  only add ceremony, unlike `mark_render_job`'s split in Phase 2 (which exists because
  it's a reliable, side-effecting status write that must not be entangled with a
  long-running, less-reliable operation).

## Risks / Trade-offs

- [Risk] Structured-output reliability varies by model size — smaller local models
  (e.g. `phi4-mini:3.8b`) are more likely to violate schema constraints than larger
  ones or Anthropic → Mitigation: bounded retries surface failure rather than hang,
  but this is a safety net, not a guarantee; model choice is a per-deployment tuning
  decision, tracked in tasks.md's verification step.
- [Risk] Each LAN machine's own Ollama/vLLM bind-address and model-loaded state is
  outside this repo's control (vLLM in particular requires the target model to
  already be served, unlike Ollama's lazy-load-on-request) → Mitigation: this change
  only consumes `LLM_API_BASE`; documented as an operational prerequisite, same
  category as the RFC's existing `nvidia` default-runtime prerequisite.
- [Risk] LiteLLM is a fast-moving dependency, the sole thing standing between this
  Activity and every provider's real wire format → Mitigation: pin an exact version
  (not a floating `>=`) in `pyproject.toml`, matching this repo's existing pinning
  convention for `chatterbox-tts`/`setuptools`.
- [Risk] This change ships `generate_metadata` with nothing calling it yet (no
  `VideoProductionWorkflow`) → Mitigation: deliberate — verified directly via
  `ActivityEnvironment` and a real Temporal server/task queue (tasks.md), the same way
  Phase 2 verified `synthesize` before `AudioGenerationWorkflow` wired it in.

## Migration Plan

Purely additive — new `worker/llm.py` module, new dataclasses/Activity, new
`cpu-worker` compose service, new `litellm` dependency. No existing service,
workflow, or Activity changes shape. Rollback: remove the `cpu-worker` service and
the `litellm` dependency; `gpu-worker`/`api`/`web` and `AudioGenerationWorkflow` are
unaffected.
