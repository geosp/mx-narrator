## 1. MongoDB replica set (prerequisite for change streams)

- [x] 1.1 Update `deploy/docker-compose.yml`'s `mongo` service to run with `--replSet
      rs0` and verify the container starts (won't be a usable replica set yet until
      1.2)
- [x] 1.2 Run a one-time `rs.initiate()` against it and verify `rs.status()` reports a
      healthy single-node replica set — implemented as an idempotent `mongo-init`
      one-shot Compose service (not a manual step) so `docker compose up` stays a
      single repeatable command; re-running it after initiation confirmed it correctly
      no-ops instead of erroring
- [x] 1.3 Verify a change stream actually delivers an event: open a change stream on a
      scratch collection, insert a document from another connection, and confirm the
      change stream receives it — confirmed: `CHANGE_STREAM_EVENT: "insert"` delivered

## 2. GPU worker image with narrator's real dependencies

- [x] 2.1 Write a `Dockerfile` that copies `src/narrator/`, `pyproject.toml`, and
      `uv.lock` into the image and runs `uv sync --frozen`, and verify
      `uv run python -c "import narrator.batch"` succeeds inside the built image —
      confirmed: `narrator.batch import OK` (`deploy/gpu-worker/Dockerfile`; required
      adding `git` to the image since `chatterbox-tts` is a pinned git dependency)
- [x] 2.2 Verify Chatterbox V3 loads inside the container against the real GPU
      (reuse the same check as narrator's own `ChatterboxEngine.load()` /
      `test_gpu_chatterbox.py` pattern) and produces a non-empty audio tensor for a
      short test string — this is the phase's core risk check (design.md) — confirmed:
      `cuda_available: True, device_name: NVIDIA GeForce RTX 3060`, 230480-byte output,
      `CHATTERBOX_GPU_VERIFY: OK`; required `docker run --gpus all` explicitly (a plain
      `docker run` on `python:3.11-slim` doesn't get GPU access from the host's default
      nvidia runtime without it — Phase 1's stub only worked because `docker compose
      run` reads the compose file's `deploy.resources.reservations.devices`)
- [x] 2.3 Add the `temporalio` SDK dependency and write a minimal worker entrypoint
      that connects to `temporal:7233` and polls a `gpu-tasks` task queue, and verify
      it appears as a registered worker in Temporal's Web UI — confirmed via
      `temporal task-queue describe --task-queue gpu-tasks` (same server-side state
      the Web UI reads): one workflow poller identity registered with a live last-
      access time. Built as `worker/` (main.py, activities.py, workflows.py) —
      implemented together with the `synthesize`/`mark_render_job` Activities and
      `AudioGenerationWorkflow` from group 3 below since they're one cohesive unit;
      each task below still has its own independent verification. `deploy/docker-
      compose.yml`'s `gpu-worker-stub` (Phase 1's one-shot proof-of-life) is replaced
      by the real `gpu-worker` service per proposal.md ("evolves... into a real
      Temporal worker process")

## 3. AudioGenerationWorkflow

- [x] 3.1 Implement the `synthesize` Activity: reconstructs a `RenderJob` from its
      input, calls `narrator.batch.render_job()`, wrapped with a background heartbeat
      thread (15s interval) per design.md, and verify it runs successfully against a
      short real script end-to-end (produces a playable MP3) — confirmed: full run
      through `AudioGenerationWorkflow` produced `verify-unit.es.mp3` (67860 bytes),
      `render_jobs.status` -> `"complete"`. Also applies the submitted ID3 fields
      (`worker/activities.py::_apply_id3`, post-processing `render_job()`'s own
      tagging via mutagen directly rather than modifying narrator's `tag_mp3()`) —
      verified all of artist/title/album/track/year/genre/comments landed correctly.
      **Addendum found during group 4 testing:** a longer, multi-chunk script's
      heartbeat thread hit `RuntimeError: Not in activity context` — `threading.Thread`
      doesn't inherit Temporal's (contextvars-based) activity context, so the heartbeat
      thread's `activity.heartbeat()` calls were silently failing whenever a render
      actually crossed the 15s interval, defeating this task's whole point. Fixed by
      capturing `contextvars.copy_context()` in the main activity thread and running
      the heartbeat loop inside it; re-verified with a 7-sentence, ~64s multi-chunk
      render — zero errors, confirmed via `docker logs | grep`
- [x] 3.2 Implement `synthesize` writing output to the shared `/data/media` volume and
      verify the produced file is readable from a different container mounting the
      same volume — confirmed: a throwaway `python:3.11-slim` container mounting only
      `media-data` read and tag-inspected the MP3 the `gpu-worker` container produced
- [x] 3.3 Implement error handling: a synthesis failure updates `render_jobs.status`
      to `"failed"` with an error message rather than leaving the workflow/document
      stuck, and verify by forcing a real failure (e.g. an invalid engine name) and
      checking both Temporal's Web UI and the `render_jobs` document — confirmed:
      `render_jobs.error` = `"RuntimeError: Unknown engine: 'not-a-real-engine'.
      Supported: chatterbox, kokoro"`, `status: "failed"`; `temporal workflow show`
      history shows `ActivityTaskFailed` -> caught -> `WorkflowExecutionCompleted`.
      Required adding `RetryPolicy(maximum_attempts=1)` to the `synthesize` Activity —
      Temporal's default unlimited-retry policy would otherwise retry a deterministic
      failure (bad engine name) indefinitely up to the 2-hour `start_to_close_timeout`
      instead of surfacing it, which is exactly the "stuck" state this task exists to
      prevent
- [x] 3.4 Implement `AudioGenerationWorkflow` calling the `synthesize` Activity with a
      generous `start_to_close_timeout` (per design.md) and verify a full run's
      history is visible in Temporal's Web UI end to end — confirmed via `temporal
      workflow show`/`task-queue describe` (same server-side state the Web UI reads)
      for both the success and failure runs above

## 4. FastAPI backend

- [x] 4.1 Implement `POST /scripts` (validates language against narrator's supported
      set, persists `scripts` + `render_jobs` documents, starts
      `AudioGenerationWorkflow`) and verify both the happy path and the missing-text /
      unsupported-language rejection paths with real requests — confirmed: happy path
      -> 200 with `script_id`/`render_job_id` and a workflow that actually ran
      (`render_jobs.status` progressed rendering -> complete); empty `script_text` ->
      422 (pydantic `min_length=1`); `lang: "fr"` -> 422 `"Unsupported language..."`;
      confirmed zero `scripts`/`render_jobs` documents created for either rejection.
      Built as `api/main.py`, reusing `narrator.prep.registry.available_languages()`
      rather than duplicating the supported-language list. Shares the `gpu-worker`
      Docker image (new `api` compose service, different `command:`) rather than a
      second build of narrator's ML stack, since `api/main.py` only imports the
      lightweight `worker/types.py` (extracted from `worker/activities.py` for this
      reason), never `worker.activities`/`worker.workflows`
- [x] 4.2 Verify ID3 tag fields submitted on the request land unchanged on the created
      `render_jobs.id3` field, including overriding the default artist — confirmed:
      posted artist/title/album/track/year/genre/comments all matched exactly in the
      persisted `render_jobs.id3` sub-document
- [x] 4.3 Implement an SSE endpoint that streams `render_jobs` status changes via the
      MongoDB change stream from group 1, and verify with a real client: start a
      render, hold the SSE connection open, and confirm status updates arrive without
      polling — confirmed: `curl -sN .../render_jobs/{id}/events` held open across an
      entire real render emitted exactly two `data:` events with no request in
      between — the initial snapshot (`status: "rendering"`) and the pushed update
      (`status: "complete"`, `audio_path` set)

## 5. Minimal frontend

- [x] 5.1 Build a script upload form (text, language, render parameters, ID3 tag
      fields matching the tag-editor screenshot) that posts to `/scripts`, and verify
      a submission end-to-end produces a `render_jobs` document — confirmed via a real
      headless-browser run (Playwright/Chromium, not just a curl/fetch check): filled
      and submitted the form on the running Vite dev server, `render_jobs` document
      created with the submitted ID3 fields. Built with plain React 19 + Vite + JSX
      (no TypeScript), inline style objects (CSS-in-JS), matching the sibling `ebpi`
      project's conventions
- [x] 5.2 Build a status view subscribing to the SSE endpoint and verify it updates
      live (queued → rendering → complete) without a page refresh during a real render
      — confirmed in the same browser run: `SEEN_STATUSES=["connecting","rendering",
      "complete"]`, final DOM shows the completed `audio_path`, zero browser console
      errors, no `page.reload()`/navigation anywhere in the test — the `EventSource`
      updates were the only thing that changed the DOM after initial submit

## 6. End-to-end verification

- [x] 6.1 From a clean `docker compose up -d --build` (all services: Phase 1's infra
      plus this phase's `api`/`gpu-worker`/`web`), submit a real script through the UI
      and verify a correctly-tagged, playable MP3 is produced with no manual CLI step
      anywhere in the path — confirmed: `docker compose down` (full container
      removal) then a single fresh `docker compose up -d --build` brought up all 7
      services; a real headless-browser session filled and submitted the form on the
      containerized `web` service (localhost:3000, not the dev server), watched the
      status view go `rendering` -> `complete` via SSE, and the resulting MP3 (read
      back from a separate throwaway container on the `media-data` volume) has a real
      duration (4.39s), a real bitrate (128kbps), and the exact submitted
      title/artist/album ID3 tags. Added `web/Dockerfile` (multi-stage: `npm run
      build` -> nginx serving the static bundle) and a `web` compose service —
      `VITE_API_BASE` build arg defaults to `http://localhost:8000` since it's the
      browser on the host, not another container, that calls the API
- [x] 6.2 Update `deploy/README.md` with the new services and bring-up/verification
      commands from this phase, so Phase 3 can build on it without re-deriving it —
      done: services table, updated bring-up/verify/teardown commands (7 services,
      the `mongo-init` replica-set gap from Phase 1 closed), a scripted (no-UI) path
      via curl, and a "Next phase" pointer to `VideoProductionWorkflow`
