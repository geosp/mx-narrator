# Mx Narrator Studio — infrastructure

Docker Compose stack for Temporal + MongoDB + a FastAPI backend + a Temporal GPU
worker (synthesis + transcription) + a lightweight LLM-metadata worker + a minimal
web UI, per `docs/rfc-narrator-studio.md` §5.2 and the OpenSpec changes at
`openspec/changes/docker-compose-skeleton/` (archived, Phase 1),
`openspec/changes/audio-generation-workflow/` (archived, Phase 2),
`openspec/changes/llm-metadata-generation/`, and
`openspec/changes/video-transcription-review/`.

## Services

| Service             | What it is                                                             |
|----------------------|------------------------------------------------------------------------|
| `temporal-postgres`  | Postgres backing store for Temporal                                    |
| `temporal`           | Temporal server (`temporal:7233`)                                      |
| `temporal-ui`        | Temporal Web UI — http://localhost:8080                                |
| `mongo`              | MongoDB, single-node replica set `rs0` (required for change streams)   |
| `mongo-init`         | One-shot: `rs.initiate()`, idempotent, exits after running             |
| `api`                | FastAPI backend — http://localhost:8000 (`POST /scripts`, `/video_jobs`, SSE, `/media`) |
| `gpu-worker`         | Temporal worker: polls `gpu-tasks` — mx_narrator synthesis + faster-whisper transcription |
| `cpu-worker`         | Temporal worker: polls `cpu-tasks` — `generate_metadata` (LLM) + `correctness_check` |
| `web`                | Minimal React UI — http://localhost:3000                               |

`api`, `gpu-worker`, and `cpu-worker` share one image
(`mx-narrator/gpu-worker:local`, built from `deploy/gpu-worker/Dockerfile`) — same
monorepo, same `pyproject.toml`/`uv.lock`, different `command:`. Only `gpu-worker` gets
the GPU device reservation; `api`/`cpu-worker` never import mx_narrator's ML stack (see
`worker/types.py`).

### `cpu-worker` config (LLM provider/target)

`generate_metadata` (title/description/tags generation) targets a configurable LLM —
local network by default, remote API as an explicit opt-in — via env vars, all
overridable with a shell env var or `.env` file, no compose file edit needed:

| Env var | Default (this deployment) | Notes |
|---|---|---|
| `LLM_MODEL` | `ollama/llama3.1:8b` | LiteLLM model string — `ollama/<model>` for Ollama, `hosted_vllm/<model>` for a vLLM OpenAI-compatible endpoint, `anthropic/claude-...` for remote |
| `LLM_API_BASE` | `http://host.docker.internal:11434` | Target machine's `host:port` — Ollama defaults to port 11434, vLLM's OpenAI server to 8000. The committed default assumes Ollama on *this* Docker host (already confirmed listening on `0.0.0.0:11434`); point it at a different LAN machine's IP for a different Ollama/vLLM host |
| `ANTHROPIC_API_KEY` | unset | Only read when `LLM_MODEL` selects `anthropic/*` |

Example: switch to a different local model without touching any file —
`LLM_MODEL=ollama/phi4-mini:3.8b docker compose up -d --force-recreate cpu-worker`.

### `gpu-worker` config (transcription)

| Env var | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `large-v3` | faster-whisper model size — `large-v3` chosen deliberately over a smaller/faster model since the correctness check's trustworthiness depends entirely on transcription accuracy |
| `WHISPER_COMPUTE_TYPE` | `int8_float16` | CTranslate2 quantization; drop to `medium`/`distil-large-v3` `WHISPER_MODEL` if VRAM pressure ever shows up in practice |

**If you run Ollama on this same host** (as this deployment's committed
`LLM_API_BASE` default assumes): a real, recurring issue on this host's AMD/ROCm GPU
backend is a wedged model runner (`journalctl -u ollama`: `HW Exception ... GPU
Hang`), surfacing as `model runner has unexpectedly stopped` from every request
regardless of model. Fix without restarting the service: `ollama stop <model>` to
clear the wedged runner, then retry — no sudo needed. If one model keeps hitting
this, try a different `LLM_MODEL` (this was seen intermittently on `llama3.1:8b` but
not `phi4-mini:3.8b` on the same host).

## Prerequisites

- Docker with Compose V2 (`docker compose version`; built/verified against 5.3.1).
  `deploy.resources.reservations.devices` for GPU access requires Compose V2 — it does
  **not** need Swarm mode.
- The host's `nvidia` default runtime, already confirmed configured
  (`/etc/docker/daemon.json`).
- **Check for port conflicts before first bring-up.** This host also runs a separate,
  unrelated `spark` project (`/home/geo/develop/govspend/spark`) whose own Temporal +
  Mongo + Redis + NATS stack uses the *same* ports (7233, 8080, 27017). If those are
  running, `docker compose up` will fail with "port is already allocated." Either stop
  it first (`cd /home/geo/develop/govspend/spark && docker compose stop`, fully
  reversible with `docker compose start`), or don't run both stacks at once.
- The host's HuggingFace cache (`~/.cache/huggingface`) is bind-mounted into
  `gpu-worker` so Chatterbox's ~5GB of weights aren't re-downloaded into a fresh
  volume. If the model has never been downloaded on this host at all, the first render
  downloads it (slow, one-time).

## Bring up

```bash
cd deploy
docker compose up -d --build
```

One command, no manual per-service steps — `mongo-init` runs `rs.initiate()`
automatically and idempotently.

## Verify

```bash
docker compose ps                                                # all services -> healthy/running
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080    # temporal-ui -> 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000    # web -> 200
docker exec mx-narrator-mongo-1 mongosh --quiet --eval "rs.status().ok"   # -> 1
```

**End-to-end, audio**: open http://localhost:3000, fill in a unit ID, script text
(optionally a series name — used for metadata generation's prior-episode-titles
context), and the MP3 tag fields, click "Generate audio". The status view updates
live (no page refresh) from `rendering` to `complete` and shows the produced file's
path under `/data/media` (the `media-data` volume, shared between `api` and
`gpu-worker`).

**End-to-end, video production (transcription → correctness check → SRT review)**:
once a render is `complete`, a "Start video production" control appears — pick a
background image and submit. This navigates to `/?video_job_id=...`, which shows
live status through `transcribing` → `checking_correctness` → (if a mismatch is
found) `mismatch_needs_review`, with an "Acknowledge and continue" button → always
`srt_review_pending`, with the source audio playable and the transcribed captions
editable before clicking "Approve" → terminal state `srt_approved`. This is
currently where the pipeline stops — see "Next phase" below.

**Without the UI** (e.g. scripting):

```bash
curl -s -X POST http://localhost:8000/scripts \
  -H "Content-Type: application/json" \
  -d '{
    "unit_id": "example-unit", "lang": "es", "series_name": "Example Series",
    "script_text": "Texto de prueba.",
    "id3": {"artist": "Artist", "title": "Title", "album": "Album"}
  }'
# -> {"script_id": "...", "render_job_id": "..."}

curl -sN http://localhost:8000/render_jobs/<render_job_id>/events   # SSE status stream

# once the render is complete:
curl -s -X POST http://localhost:8000/video_jobs \
  -F "render_job_id=<render_job_id>" -F "image=@background.jpg"
# -> {"video_job_id": "..."}

curl -sN http://localhost:8000/video_jobs/<video_job_id>/events              # SSE status stream
curl -s http://localhost:8000/video_jobs/<video_job_id>/srt                  # current draft/approved SRT text
curl -s -X POST http://localhost:8000/video_jobs/<video_job_id>/mismatch/acknowledge
curl -s -X POST http://localhost:8000/video_jobs/<video_job_id>/srt/approve \
  -H "Content-Type: application/json" -d '{"srt_text": "..."}'
```

A running `AudioGenerationWorkflow` or `VideoProductionWorkflow` is also visible
end-to-end in Temporal's own Web UI (http://localhost:8080) — independent of what
MongoDB reports.

## Known gap: the private registry

`docker-registry.mixwarecs-home.net:5000` (the intended target for worker images, per
the RFC) was unreachable at the network layer (`no route to host`) when this stack was
first verified in Phase 1 — a different physical host on the local network, apparently
offline, not a Docker/auth problem on this side. The push/pull round trip was proven
instead against a temporary local `registry:2` container on `localhost:5000`, then torn
down — the *mechanism* is proven, the *actual target registry* still needs a one-time
re-verification once that host is reachable again:

```bash
docker tag mx-narrator/gpu-worker:local docker-registry.mixwarecs-home.net:5000/mx-narrator/gpu-worker:local
docker push docker-registry.mixwarecs-home.net:5000/mx-narrator/gpu-worker:local
```

## Tear down

```bash
docker compose down       # stop and remove containers, keep volumes (mongo/temporal/media data)
docker compose down -v    # also removes those volumes — destructive, loses render history/audio
```

## Next phase

`video-transcription-review` (this deploy) covers the first three stages of RFC
§7.2's `VideoProductionWorkflow`: transcribe → correctness check → SRT review,
ending at `video_jobs.status = "srt_approved"` — a disclosed, deliberate stopping
point short of the RFC's literal `rendering` transition, since `render_video` doesn't
exist yet. Still remaining, as a separate future change extending the same
`VideoProductionWorkflow` function:

- `render_video` — ffmpeg: loop the uploaded background image, mux the finished audio
  and the approved SRT as a soft subtitle track (not burned in) into an MP4. No
  video/image/ffmpeg-muxing code exists anywhere in this codebase yet.
- Wiring the already-built, already-standalone `generate_metadata` Activity
  (`llm-metadata-generation`) into `VideoProductionWorkflow` as its next stage.
- A metadata-review signal-wait + UI screen, mirroring the SRT-review pattern.
- `video_jobs.status = "ready_for_manual_upload"` as the real terminal state (RFC
  §7.3), superseding this phase's `srt_approved` placeholder.

`api/scripts`'s `series_name` gap (flagged in `llm-metadata-generation`) is fixed —
`POST /scripts` collects it now, so `generate_metadata`'s prior-episode-titles
context has real data to draw on.
