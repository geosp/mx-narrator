## Context

Phase 1 (archived) proved Temporal, MongoDB, and GPU-container access all work. This
phase adds the first real application code on top of that: a FastAPI backend, a
Temporal worker that actually runs narrator's synthesis, and a minimal frontend. See
proposal.md for motivation; RFC §7.1 for the target sequence diagram.

## Goals / Non-Goals

**Goals:**
- Prove narrator's actual dependencies (Chatterbox V3, real GPU synthesis) work
  correctly inside a container — Phase 1 explicitly deferred this.
- Establish the FastAPI + Temporal + MongoDB integration pattern every later phase
  reuses, including the live-progress (SSE) mechanism from RFC §10.1.
- End-to-end: script in via the web UI, correctly-tagged MP3 out, no manual CLI step.

**Non-Goals:**
- No transcription, no video, no metadata generation — that's `VideoProductionWorkflow`
  (RFC §7.2), a later phase.
- No auth yet (RFC's "simple session/JWT" is deferred until there's more than one
  screen worth protecting).
- Not rebuilding narrator's synthesis logic — the Activity calls
  `src/narrator/batch.py::render_job()` directly; if that function's behavior is wrong,
  that's narrator's own extensive existing test suite's problem, not this phase's.

## Decisions

- **GPU worker image reuses narrator's own `pyproject.toml`/`uv.lock` via `uv sync
  --frozen`**, copying `src/narrator/` into the image rather than reimplementing or
  duplicating its dependency list. Gets the exact same pinned Chatterbox V3 commit
  already proven to work on the host — if it doesn't work identically in the
  container, that's the real signal this phase exists to catch (Phase 1's Non-Goals).
- **The `synthesize` Activity is a synchronous function**, not async — `render_job()`
  is itself blocking, GPU-bound, CPU/IO-heavy work; wrapping it in `async def` would
  gain nothing. Temporal's Python SDK runs sync activities in a thread pool
  automatically. The worker is configured with `max_concurrent_activities=1` per GPU
  worker process, matching narrator's own established constraint (spec.md section 2 of
  the original narrator build: "none of the TTS models here shard across cards, one
  file uses a single GPU").
- **A background heartbeat thread, not per-chunk instrumentation inside narrator.**
  Long syntheses (RFC's ballpark: 20-30 minutes of audio) risk Temporal's default
  activity timeout killing an activity that's still legitimately working. Rather than
  adding heartbeat calls inside `render_job()` (touching narrator's code, against this
  project's "orchestrate, don't modify" principle), the Activity wrapper starts a
  background thread that calls `activity.heartbeat()` every 15s for the duration of
  the blocking `render_job()` call.
- **Shared Docker volume for media files** (`media-data`, mounted at `/data/media` in
  both `api` and `gpu-worker`), matching the RFC's architecture diagram (§5.1's
  "Shared volume" node) — `render_job()`'s `out_path` is a path on this volume, so the
  API can serve/list files the worker produced without its own copy step.
- **MongoDB change streams require a replica set — even a single-node one — which
  Phase 1's plain `mongo:7` service does not have.** This phase updates that service
  (`--replSet rs0` + a one-time `rs.initiate()`) rather than deferring it, since the
  live-progress requirement in `api/scripts`'s spec depends on it working now, not
  later. This is the one change to a Phase-1-owned file this phase makes; no other
  Phase 1 service configuration changes.
- **SSE, not WebSocket, for the live-progress channel** — one-directional
  (server→client) is all that's needed; the UI signals Temporal through normal POST
  requests. Confirmed already in RFC §10.1; restated here since this is the phase that
  actually implements it for the first time.

## Risks / Trade-offs

- [Risk] Container CUDA/cuDNN behavior differing from the host (Phase 1's deferred
  risk, now actually being tested) → Mitigation: this phase's own primary goal is
  finding out; if it fails, the fix is a container-specific base image or CUDA version
  pin, not a design change here.
- [Risk] Converting Phase 1's standalone `mongo` service to a replica-set node is a
  behavior change to already-archived infrastructure, not purely additive → Mitigation:
  single-node replica sets are still standalone-equivalent for every Phase 1 requirement
  (reachable, persists data) — nothing in the Phase 1 spec is violated, this only adds
  capability.
- [Risk] Long-running synthesis Activities (many minutes) tie up a worker slot for a
  while → Mitigation: acceptable at this scale (weekly single-team production, not
  high-throughput); revisit worker pool sizing only if real usage shows it's a
  bottleneck.

## Migration Plan

Extends Phase 1's `deploy/docker-compose.yml` — no destructive changes to existing
services except the `mongo` replica-set flag above. Rollback: `docker compose down`
the new `api`/`gpu-worker`/`web` services; Phase 1's Temporal/Mongo stack is unaffected.
