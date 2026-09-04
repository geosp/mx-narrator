## 1. Python package rename

- [x] 1.1 `src/narrator/` → `src/mx_narrator/` (plain move, no git history to preserve — repo has zero commits)
- [x] 1.2 All 26 files' `from narrator...`/`import narrator` → `mx_narrator` (`src/`, `worker/`, `tests/`, `api/main.py`)
- [x] 1.3 `pyproject.toml`: `name`, `[project.scripts]` entry
- [x] 1.4 `src/mx_narrator/cli.py`: `argparse` `prog=`, docstring examples
- [x] 1.5 `src/mx_narrator/__init__.py`'s greeting string, `assemble.py`'s tempdir prefix, `prep/base.py`'s logger-name comment

## 2. Docker/deployment naming

- [x] 2.1 `deploy/docker-compose.yml`: `name:`, 4 image-tag references
- [x] 2.2 `deploy/README.md`: registry-push example, container-name example, prose
- [x] 2.3 `deploy/gpu-worker/Dockerfile`, `deploy/gpu-worker-stub/Dockerfile`: comments

## 3. Branding

- [x] 3.1 `README.md`, `specs.md`: titles, CLI examples, paths
- [x] 3.2 `web/src/App.jsx`, `Dashboard.jsx`: `<h1>` heading; `web/index.html`: `<title>`

## 4. Comments referencing real code paths

- [x] 4.1 `worker/*.py`, `api/main.py`, `openspec/config.yaml`, `openspec/specs/*/spec.md`: updated mentions that referenced actual (now-changed) import paths or the platform name

## 5. MongoDB database name — decoupled, not migrated

- [x] 5.1 `MONGODB_DATABASE` env var (default `narrator_studio`) added to `worker/activities.py` and `api/main.py`, replacing 3 hardcoded literals
- [x] 5.2 `deploy/docker-compose.yml`: `MONGODB_DATABASE: narrator_studio` set explicitly per service, alongside existing `MONGODB_URL`

## 6. Docker volumes — pointed at existing data, not migrated

- [x] 6.1 `deploy/docker-compose.yml`: `mongo-data`/`media-data`/`temporal-postgres-data` marked `external: true` with explicit `name:` pointing at the existing `narrator-studio_*` volumes

## 7. Verification (real infrastructure, no mocking)

- [x] 7.1 `uv lock` — resolves correctly, root package entry confirmed `mx-narrator`
- [x] 7.2 Noted (not fixed, pre-existing/unrelated): full host `uv sync` blocked by missing C++ compiler for `ctc-forced-aligner`'s native extension
- [x] 7.3 Rebuilt both Docker images from scratch under their new tags
- [x] 7.4 Ran the real test suite inside the freshly-built image (tests mounted at runtime): 80 passed, 1 deselected
- [x] 7.5 Verified the renamed CLI entry point (`mx-narrator --help`) inside the image
- [x] 7.6 Confirmed no workflow was mid-activity before cutover
- [x] 7.7 Tore down the old `narrator-studio` project's containers (no `-v`), brought up the new `mx-narrator` project attached to the same volumes
- [x] 7.8 Confirmed all services healthy
- [x] 7.9 Confirmed real production data survived: 3 real `render_jobs`/`scripts` documents, 22 media files
- [x] 7.10 Smoke-tested the live stack: API `/dashboard` → 200 with real data, web `/` → 200 with the new `<title>`
- [x] 7.11 Final repo-wide grep sweep: zero unaddressed "narrator" mentions outside explicitly-excluded references
