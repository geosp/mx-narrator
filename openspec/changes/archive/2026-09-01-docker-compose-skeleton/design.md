## Context

First infrastructure-only change for Narrator Studio (docs/rfc-narrator-studio.md
§5.2). No application code exists yet — this stands up the deployment topology so
later phases (`AudioGenerationWorkflow`, `VideoProductionWorkflow`) have something
real to run against instead of building app logic and infra simultaneously. Host
constraints already confirmed (RFC §12): Docker's default runtime is `nvidia`
(`/etc/docker/daemon.json`), and a private registry is available at
`docker-registry.mixwarecs-home.net:5000` (with `insecure-registries` set for it, i.e.
plain HTTP, not TLS — an existing host configuration, not something this change
introduces or needs to alter).

## Goals / Non-Goals

**Goals:**
- Prove every service in the topology boots and is reachable via one
  `docker compose up`.
- Prove a container can see the host GPU with no extra per-container flags, given the
  host's `nvidia` default runtime.
- Prove the private registry push/pull round trip works for a worker image.

**Non-Goals:**
- No Temporal workflow/activity code, no FastAPI backend, no frontend — those are
  later phases.
- Not proving narrator's actual dependencies (Chatterbox, Whisper, ffmpeg/NVENC) run
  correctly inside a container — only that the container can see the GPU at all. This
  session's TTS work was tested running directly on the host throughout; whether the
  CUDA/cuDNN library stack behaves identically inside a container is a real open risk,
  deliberately deferred to the `AudioGenerationWorkflow` phase where it can be tested
  against actual narrator code.
- No production-grade Temporal cluster tuning (multi-node, custom retention, archival)
  — this is a small internal team's tool, not a large-scale deployment.

## Decisions

- **Docker Compose, not Kubernetes/Swarm.** Matches the RFC's explicit direction
  ("docker images for workers") and this system's actual scale (one host, one small
  team). Kubernetes' operational overhead isn't justified here.
- **`temporalio/auto-setup` as the Temporal server image**, backed by PostgreSQL. This
  is Temporal's own standard self-hosting path for exactly this scale — it bundles the
  server and automatically applies schema setup against Postgres on first start, so
  there's no separate manual schema-migration step. Considered hand-assembling
  Temporal's full multi-service production topology; rejected as unjustified
  complexity for a single small-team deployment. Revisit only if this ever needs to
  scale past what one `auto-setup` instance can handle.
- **Explicit GPU reservation in the Compose file** (`deploy.resources.reservations.
  devices` with `driver: nvidia`) on the GPU worker service, even though the host's
  `nvidia` default runtime would technically make this implicit. Being explicit means
  the stack stays correct if the host's default runtime setting is ever changed for
  unrelated reasons — the Compose file shouldn't silently depend on host-level config
  it doesn't declare.
- **GPU worker stub is a minimal proof-of-life image** (Python 3.11 base + PyTorch
  only, no narrator dependencies yet): imports `torch`, checks `torch.cuda.
  is_available()`, logs the device name, exits. Keeps this phase's Docker image small
  and decoupled from narrator's actual (heavier) dependency set, per the proposal's
  explicit "no changes to `src/narrator/`."
- **Named Docker volumes for Mongo and Temporal's Postgres data**, not bind mounts —
  standard Docker-managed persistence, portable across hosts if this ever moves.
- **Per-service `healthcheck:` blocks in Compose** (Temporal: gRPC health check via
  its own CLI; Mongo: `mongosh --eval "db.adminCommand('ping')"`; Temporal UI: HTTP
  GET) so "the stack is up and healthy" is something `docker compose ps` can report
  programmatically, matching the spec's testable scenarios — not just "logs look fine."

## Risks / Trade-offs

- [Risk] `auto-setup`'s automatic schema migration on every start is a dev/small-scale
  convenience, not how a larger production Temporal deployment would be configured →
  Mitigation: acceptable at this scale; revisit if usage ever grows past what one
  small team's workload needs.
- [Risk] GPU-visible-in-container doesn't guarantee narrator's actual ML stack
  (Chatterbox V3, Whisper, ffmpeg NVENC) runs correctly under the container's CUDA/
  cuDNN library versions, which may differ from the host's → Mitigation: explicitly
  scoped out of this phase (see Non-Goals); the next phase validates this for real
  against actual narrator code, not assumed solved by this stub passing.
- [Risk] The private registry uses `insecure-registries` (plain HTTP) → Mitigation:
  this is existing host configuration for a registry on the private local network, not
  something introduced by this change; out of scope to change here.

## Migration Plan

N/A — first infrastructure deployment, no existing state to migrate. Rollback, if
something's wrong: `docker compose down -v` cleanly tears down all containers and
volumes, since nothing else depends on this stack yet.
