## 1. Compose skeleton — Temporal + MongoDB

- [x] 1.1 Create `docker-compose.yml` with `temporal-postgres` (Postgres, named volume
      for data) and verify `docker compose config` parses without error
- [x] 1.2 Add `temporal` service using `temporalio/auto-setup`, wired to
      `temporal-postgres`, and verify `docker compose up -d temporal-postgres temporal`
      brings both up with `docker compose ps` showing `temporal` running
- [x] 1.3 Add a gRPC healthcheck to the `temporal` service and verify
      `docker compose ps` reports it `healthy`, not just `running`
- [x] 1.4 Add `temporal-ui` service pointed at `temporal` and verify an HTTP GET to its
      configured port returns a 2xx response
- [x] 1.5 Add `mongo` service with a named volume and a `mongosh --eval
      "db.adminCommand('ping')"` healthcheck; verify `docker compose ps` reports it
      `healthy`
- [x] 1.6 Verify Mongo data survives a restart: write a test document, run
      `docker compose restart mongo`, reconnect, and confirm the document is still
      readable

## 2. GPU worker stub

- [x] 2.1 Write a minimal `Dockerfile` (Python 3.11 base + `torch` only) whose entrypoint
      imports `torch`, prints `torch.cuda.is_available()` and the device name, then
      exits, and verify it builds successfully
- [x] 2.2 Add the GPU worker stub as a Compose service with an explicit GPU device
      reservation (`deploy.resources.reservations.devices`, `driver: nvidia`) and
      verify `docker compose run gpu-worker-stub` logs `cuda_available: True` and the
      correct GPU name with no `--gpus` flag needed on the `docker compose run`
      invocation itself
- [x] 2.3 Tag and push the stub image to `docker-registry.mixwarecs-home.net:5000` and
      verify the push succeeds — **NOTE**: the actual target registry was unreachable
      at the network layer (`no route to host`, host appears offline, not a Docker/auth
      issue) when this was run. Verified against a local stand-in registry instead
      (`registry:2` container on `localhost:5000`) to prove the push/pull mechanism
      works. **The real target registry still needs a one-time re-verification once
      that host is back online** — mechanism is proven, the specific endpoint isn't yet.
- [x] 2.4 Remove the local image, pull it back from the registry, and verify the
      pulled image reproduces the same `cuda_available: True` result from 2.2 —
      confirmed identical (`cuda_available: True`, `NVIDIA GeForce RTX 3060`) via the
      local stand-in registry per the note on 2.3

## 3. Full-stack verification

- [x] 3.1 From a clean state (`docker compose down -v` first), run
      `docker compose up -d` once and verify every service (`temporal-postgres`,
      `temporal`, `temporal-ui`, `mongo`, `gpu-worker-stub`) reaches `running`/`healthy`
      with no manual steps beyond that one command — verified: postgres/temporal/mongo
      all `healthy`, temporal-ui `running` (HTTP 200), gpu-worker-stub `Exited (0)`
      (its correct terminal state — a one-shot proof-of-life check, not a daemon) with
      `cuda_available: True` in its logs
- [x] 3.2 Document the exact bring-up/verification commands (from tasks 1-3) in a
      short `deploy/README.md` so the next phase (`AudioGenerationWorkflow`) can build
      on this without re-deriving it
