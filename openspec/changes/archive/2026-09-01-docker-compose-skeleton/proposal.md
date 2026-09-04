## Why

Narrator Studio (docs/rfc-narrator-studio.md) needs Temporal, MongoDB, and a
GPU-capable worker running as self-hosted Docker services before any application
workflow (audio generation, video production) can be built and tested against them.
Standing this up first, with no application code, proves the deployment topology
(RFC §5.2) — including GPU passthrough and the private registry — independently of any
business logic, so later phases build on a working foundation instead of debugging
infrastructure and application code at the same time.

## What Changes

- New Docker Compose stack defining: `temporal` (server), `temporal-postgres` (its
  datastore), `temporal-ui`, `mongo`, and a GPU worker stub container.
- GPU worker stub: a minimal container (Python 3.11 base, matching narrator's
  `requires-python`) that starts, confirms CUDA/GPU device access is visible inside the
  container (e.g. `torch.cuda.is_available()`), logs the result, and exits — no
  Temporal worker/activity logic yet, just proof the container can see the GPU through
  the host's `nvidia` default runtime (confirmed already configured, RFC §12).
- Worker image(s) built and pushed to the existing private registry
  (`docker-registry.mixwarecs-home.net:5000`), then pulled back down to confirm the
  round trip works.
- No changes to `src/narrator/` — this phase touches only new deployment/infrastructure
  files.

## Capabilities

### New Capabilities
- `infra/docker-compose-stack`: the self-hosted Temporal + MongoDB + GPU-worker-stub
  deployment topology from RFC §5.2 — what "up and reachable" means for each service,
  and that the GPU worker container has functioning GPU access.

### Modified Capabilities
(none — this is the first change against this repo's OpenSpec baseline)

## Impact

- New files: Docker Compose definition, a GPU worker stub `Dockerfile`.
- No changes to the existing `narrator` CLI's behavior, `pyproject.toml`, or
  dependencies (RFC §11: narrator is orchestrated, not modified).
- Affects the local Docker host only (self-hosted, per RFC §4/§9) — no cloud
  dependency, no external network exposure.
- Depends on: the host's `nvidia` default runtime and the private registry — both
  already confirmed available (RFC §12), not something this change needs to set up.
