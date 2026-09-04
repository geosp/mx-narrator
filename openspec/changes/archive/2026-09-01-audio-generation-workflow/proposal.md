## Why

Phase 1 (`docker-compose-skeleton`, archived) proved the infrastructure boots and a
container can see the GPU — but never ran narrator's actual dependencies (Chatterbox,
real synthesis) inside a container, and explicitly flagged that as an open risk. This
phase is the smallest real vertical slice: a script goes in through the web UI, a
fully ID3-tagged MP3 comes out, orchestrated by Temporal instead of a one-off CLI
invocation. It proves narrator's real ML stack works in a container, and establishes
the FastAPI + Temporal + MongoDB integration pattern every later phase (video
production) reuses.

## What Changes

- New Temporal workflow `AudioGenerationWorkflow` with a `synthesize` Activity that
  wraps `src/narrator/batch.py::render_job()` — narrator's own code is called, not
  modified.
- New minimal FastAPI backend: `POST /scripts` accepts script text, language, render
  parameters (engine, voice, cfg_weight, exaggeration, speed, seed), and the ID3 tag
  fields from the tag-editor UI (artist, title, album, track, year, genre, comments),
  persists to MongoDB, and starts the workflow.
- New MongoDB collections: `scripts` and `render_jobs`, per RFC §6.2.
- GPU worker image evolves from Phase 1's one-shot proof-of-life stub into a real
  Temporal worker process (long-running, polling a task queue) with narrator's actual
  dependencies installed (Chatterbox, Kokoro, torch, ffmpeg) — this is where the real
  container-vs-host CUDA/cuDNN risk flagged in Phase 1 gets tested for real.
- Minimal React + Vite frontend: a script upload form (including the ID3 tag fields)
  and a status view showing whether a render is queued/rendering/complete/failed.
- Extends `deploy/docker-compose.yml` (Phase 1) with the new `api`, `gpu-worker`, and
  `web` services — does not change the Temporal/MongoDB services Phase 1 already
  proved.

## Capabilities

### New Capabilities
- `api/scripts`: the script + render-parameter + ID3-tag intake API — validation,
  persistence to `scripts`/`render_jobs`, and triggering `AudioGenerationWorkflow`.
- `workflow/audio-generation`: the Temporal workflow itself — given a persisted script
  and render parameters, produces a correctly-tagged MP3 via narrator's existing
  synthesis pipeline, and records status transitions in `render_jobs`.

### Modified Capabilities
(none — `infra/docker-compose-stack` from Phase 1 is extended with new services, not
behaviorally changed; its existing requirements — stack reachability, GPU access — are
unaffected)

## Impact

- New code: a FastAPI service, a Temporal worker service (imports narrator as a
  dependency), a minimal React+Vite frontend.
- No changes to `src/narrator/` internals — `render_job()` is called from a Temporal
  Activity, not modified.
- Extends (does not replace) `deploy/docker-compose.yml` from Phase 1.
- Depends on Phase 1's infra being up (`temporal`, `mongo` reachable).
- First real test of narrator's ML dependencies running inside a container, not just
  on the bare host as throughout the original narrator CLI's development.
