## Why

User request: rename the project to "mx-narrator". Investigation confirmed
"mx" is short for "Mixware" — the user's own registry/homelab namespace
(`deploy/README.md` already referenced
`docker-registry.mixwarecs-home.net:5000/narrator-studio/...`).

## What Changes

Full rename across four tiers, all confirmed with the user before touching
anything given the real blast radius:

- **Python package**: `src/narrator/` → `src/mx_narrator/`; all 26 files
  that did `from narrator...`/`import narrator` (`src/`, `worker/`,
  `tests/`, `api/main.py`) updated. `pyproject.toml`: `name = "mx-narrator"`,
  `[project.scripts]` entry `mx-narrator = "mx_narrator.cli:main"`.
  `src/mx_narrator/cli.py`'s `argparse` `prog=` and docstring examples
  updated to `mx-narrator`.
- **Docker/deployment naming**: `deploy/docker-compose.yml`'s `name:
  mx-narrator`, image tags `mx-narrator/gpu-worker`/`mx-narrator/web`,
  `deploy/README.md`'s registry-push example and container-name example.
- **Project branding**: `README.md`/`specs.md` titles and CLI examples,
  `web/src/App.jsx`/`Dashboard.jsx`'s `<h1>` heading and `web/index.html`'s
  `<title>` → "Mx Narrator Studio".
- **Prose/comments referencing the package or platform by name**: ~15
  comments across `worker/*.py`/`api/main.py`/`deploy/*`/
  `openspec/config.yaml`/`openspec/specs/*/spec.md` updated for accuracy
  (they referenced real code paths like `narrator.prep.registry` or
  `src/narrator/voices.py`, which would otherwise now be wrong).

**Explicitly excluded (flagged to the user, not assumed):**
- `docs/rfc-narrator-studio.md` — filename and prose left untouched. Two
  archived OpenSpec docs cite this exact path as historical record; treated
  like git history — an accurate record of decisions made under the old
  name, not something to retroactively rewrite.
- `openspec/changes/archive/**` — historical record, untouched by design.
- The project directory on disk (`/home/geo/develop/projects/narrator`) —
  stays at its current path per the user's explicit choice.

**MongoDB database name — made configurable, not migrated:** the database
is still literally `narrator_studio` (holds real production data). Added
`MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "narrator_studio")`
(same pattern as the existing `MONGODB_URL`) in `worker/activities.py` and
`api/main.py`, replacing the 3 hardcoded literals; `deploy/docker-compose.yml`
sets it explicitly alongside `MONGODB_URL` per service. Default value keeps
today's behavior byte-identical — no migration, per the user's explicit
choice ("make it a configuration option, leave the current name as its
value").

**Docker volumes — pointed at existing data, not migrated either:** the
compose project name change would otherwise make Compose default to
fresh, empty `mx-narrator_*` volumes. `deploy/docker-compose.yml`'s
`mongo-data`/`media-data`/`temporal-postgres-data` are now `external: true`
with an explicit `name:` pointing at the existing `narrator-studio_*`
volumes — same "don't risk/migrate live data for a cosmetic rename"
principle as the database name, applied consistently without re-asking
since the user had already established it. (`narrator-studio_hf-cache` is
NOT included — it's an orphaned volume from before that path became a host
bind mount, unused by the compose file either way.)

## Capabilities

No behavior change — identifiers/names only. `skip_specs: true`.

## Impact

- ~35 files touched across `src/`, `worker/`, `api/`, `tests/`, `web/`,
  `deploy/`, `openspec/`, plus root-level `README.md`/`specs.md`/
  `pyproject.toml`.
- Verified `uv.lock` resolves correctly under the new package name
  (`uv lock` — instant, root package entry confirmed `name = "mx-narrator"`).
  Full `uv sync` on the bare host is blocked by a pre-existing, unrelated
  gap (`ctc-forced-aligner`'s native extension needs a C++ compiler the
  host doesn't have installed — the Docker image already has
  `build-essential` from an earlier change this session); not something
  this rename introduced or was expected to fix.
- Rebuilt `mx-narrator/gpu-worker:local` and `mx-narrator/web:local` from
  scratch (full ML-stack reinstall, `pyproject.toml` changed). Ran the real
  test suite inside the freshly-built image (tests mounted at runtime,
  since production images don't ship `tests/` by design): 80 passed, 1
  deselected (`slow`). Verified the renamed CLI entry point directly:
  `mx-narrator --help` inside the image.
- Performed the real cutover: confirmed no workflow was mid-activity, tore
  down the old `narrator-studio` project's containers (`docker compose -p
  narrator-studio down`, no `-v` — volumes untouched), brought up the new
  `mx-narrator` project attached to the same (now-external) volumes.
  Confirmed all services healthy, confirmed real production data survived
  intact (all 3 real `render_jobs`/`scripts` documents present, 22 media
  files present), smoke-tested the live API (`/dashboard` → 200, real data)
  and web UI (`/` → 200, `<title>Mx Narrator Studio</title>`).
- Final repo-wide grep confirmed zero unaddressed "narrator" mentions
  outside the explicitly-excluded RFC/archive/volume-name references.
