# Mx Narrator Studio — Script-to-Video Production Pipeline

**Status:** Living document — describes the system as actually built and currently
running, not a proposal awaiting implementation. Originally written as a
pre-implementation RFC (v1–v5, decision log preserved in §13); converted to this
format once the system had grown well past what that log could track accurately.
Update this document whenever a change alters the architecture, data model, workflow
shape, or a still-open decision — not for every code change, but whenever a future
reader would otherwise be misled by it.
**Author:** Claude, for Giovanni Fajardo (gffajardo@gmail.com)
**Scope:** Web UI + Temporal workflows + MongoDB + Docker workers, orchestrating the
`mx_narrator` CLI/library (`src/mx_narrator/`) that ships in the same repository

---

## 1. Summary

`mx_narrator` is a local CLI: script in, narrated MP3 out, with real voice cloning
(Chatterbox), correct multilingual scripture/number handling, and ID3 tagging. This
system wraps it in a small internal platform: a script upload turns into a fully-tagged
MP3, then — after transcription, an automated correctness check, and human caption
review — a captioned video, then LLM-generated title/description/tags, staged in the UI
for the user to upload to YouTube themselves. A human approves every consequential step
along the way. The system never touches YouTube directly; it stops at "everything is
ready for you to publish." Runs as self-hosted Docker services orchestrated by Temporal.

## 2. Motivation

Producing one episode by hand means manually running CLI commands, hand-tracking which
unit/language/render-parameters were used, and manually handling transcription and video
assembly. That doesn't scale to a weekly multi-part series across three languages. This
system turns that into: upload once, get notified when each human-decision point is
ready, approve, move on — ending with a finished video and copy-paste-ready metadata,
the same hand-off point the manual process had, just automated up to that point.

## 3. Goals

- Web-based script upload with full ID3 tag control and per-voice, per-language voice
  management (upload/replace/delete reference samples independently per language).
- Durable, observable, resumable pipeline execution (Temporal) surviving worker restarts
  and GPU contention.
- A correctness check that catches TTS content problems (skipped/repeated speech) by
  comparing Whisper's transcript against the exact text `mx_narrator` fed to synthesis,
  with mismatches surfaced inline against the caption editor rather than as a separate
  list the reviewer has to cross-reference by timestamp.
- Forced word-level alignment of the human-approved caption text against the actual
  audio, so caption timing tracks the real speech rather than only Whisper's own
  (occasionally drifty) segment boundaries.
- Burned-in captions on the final video — legible everywhere the video is played,
  independent of player caption support (see §10 for why this replaced the original
  soft-subtitle-track design).
- A single "Final review" screen showing the rendered video, the editable caption text,
  and the editable metadata fields together, rather than splitting them across
  screens or hiding them behind collapsed sections.
- The ability to revise captions, the background image, or metadata *after* a job has
  already reached final review (or failed) — without re-running transcription or the
  correctness check, since a human edit at that point already *is* the correction.
- LLM-generated YouTube title/description/tags, staged for manual copy-paste — **the
  system never uploads or publishes anything itself.**
- Self-hosted on the user's own Docker-capable, GPU-equipped hardware — no new recurring
  cloud costs. Metadata generation defaults to LLM inference on the user's own home
  network (Ollama/vLLM on any of several LAN machines the user already has), so no data
  needs to leave the network at all by default; a remote API (e.g. Anthropic) remains an
  explicit, config-driven opt-in for when local copy quality proves insufficient.

## 4. Non-Goals

- **Authentication / multi-tenancy** — there is no login, no `users` collection, no
  session/JWT layer. Earlier drafts of this document specified one; it was never built,
  because the actual deployment is one person's tool on their own home network, not a
  shared service. The API is reachable to anything that can reach the host — treat the
  network boundary (§9) as the only access control that exists. Revisit only if this
  ever needs to be reachable by more than one trusted person.
- **Any YouTube API integration** — no OAuth, no upload, no publish, no scheduling. This
  was explicitly considered and reversed early on: the system's job ends at producing
  the finished video and metadata; the actual upload is a manual, off-system action.
- Rewriting `mx_narrator`'s synthesis internals — `src/mx_narrator/` is treated as a
  stable, already-hardened dependency this system calls into.
- Analytics/growth tooling, comment management, or anything past "assets are ready."

## 5. System Architecture

### 5.1 Component diagram

```mermaid
graph TD
    subgraph Client
        UI[Web UI]
    end

    subgraph "API Layer"
        API[FastAPI Backend]
    end

    subgraph Orchestration
        TEMPORAL[Temporal Server<br/>self-hosted]
        TUI[Temporal Web UI<br/>built-in observability]
    end

    subgraph Workers["Docker Workers"]
        GPUW["GPU Worker<br/>task queue: gpu-tasks<br/>synthesize, transcribe, align_captions<br/>--gpus all"]
        CPUW["CPU Worker<br/>task queue: cpu-tasks<br/>correctness_check, render_video (ffmpeg),<br/>generate_metadata, metadata writes"]
    end

    subgraph Storage
        MONGO[(MongoDB)]
        FILES[("Shared volume<br/>audio / images / video / SRT")]
    end

    subgraph External
        LLM["LLM endpoint<br/>(config-driven: LAN-hosted<br/>Ollama/vLLM by default,<br/>or a remote API)"]
    end

    UI -->|HTTPS| API
    API -->|start / signal workflow| TEMPORAL
    API -->|read / write| MONGO
    API -->|serve finished assets, no-cache| FILES
    TEMPORAL -->|task queue: gpu-tasks| GPUW
    TEMPORAL -->|task queue: cpu-tasks| CPUW
    GPUW -->|read / write| FILES
    GPUW -->|status writes| MONGO
    CPUW -->|LLM call, provider/host from LLM_MODEL/LLM_API_BASE| LLM
    CPUW -->|read / write| FILES
    CPUW -->|status writes| MONGO
    TUI -.->|observability| TEMPORAL
```

No component ever talks to YouTube. The workflow's terminal state is "assets ready" —
the UI's job past that point is just letting the user download/copy what's there, or
revise it. The "External" subgraph is a soft label, not a hard architectural boundary —
by default the LLM endpoint is another machine on the user's own home network (still
"internal" in every practical sense), not a third party; it only becomes truly external
when `LLM_MODEL` is explicitly configured to point at a remote API instead.

`render_video` (ffmpeg) runs on the CPU worker, not the GPU worker — muxing a static
image, an audio track, and burned-in subtitles has no GPU-accelerated step in this
pipeline (see §10), so it shares the lightweight worker with metadata generation rather
than contending with synthesis/transcription for GPU time.

### 5.2 Deployment topology (Docker Compose)

```mermaid
graph LR
    subgraph "Docker host (GPU-equipped)"
        subgraph "docker-compose project: mx-narrator"
            web[web<br/>frontend]
            api[api<br/>FastAPI]
            temporal[temporal<br/>server]
            temporalui[temporal-ui]
            temporaldb[(temporal-postgres)]
            mongo[(mongo)]
            gpuworker["gpu-worker<br/>(--gpus all,<br/>nvidia-container-toolkit)"]
            cpuworker[cpu-worker]
            vol[("shared volume:<br/>media files")]
        end
    end
    web --> api
    api --> temporal
    api --> mongo
    temporal --> temporaldb
    temporalui --> temporal
    gpuworker --> temporal
    cpuworker --> temporal
    gpuworker --> mongo
    cpuworker --> mongo
    gpuworker --> vol
    cpuworker --> vol
    api --> vol
```

Each worker type is its own Docker image/service so the GPU-bound one (needing
`nvidia-container-toolkit`) doesn't force GPU requirements onto the lightweight metadata
worker, and so task queues can scale independently. `api` and `cpu-worker` both reuse
the `gpu-worker` image (same monorepo, same `uv.lock`) rather than paying for a second
multi-hundred-second ML-stack build for services that don't need it — they just run a
different command against the same image. No publish worker exists — there's nothing
for it to do.

The compose project is named `mx-narrator` (renamed from `narrator-studio`; see §13),
but the named volumes and the `MONGODB_DATABASE` value were deliberately **not**
renamed alongside it — they still point at `narrator-studio_*`/`narrator_studio` so the
rename doesn't strand or migrate real production data. Both are config, not hardcoded,
so a future clean rename remains possible without a code change.

## 6. Data Model

### 6.1 Entity-relationship diagram

```mermaid
erDiagram
    SCRIPTS ||--o{ RENDER_JOBS : generates
    VOICES ||--o{ SCRIPTS : "optionally voices"
    RENDER_JOBS ||--o{ VIDEO_JOBS : "feeds into"
    VIDEO_JOBS ||--o| VIDEO_METADATA : produces

    SCRIPTS {
        string _id PK
        string unit_id
        string lang
        string series_name
        string series_album
        string text
        object id3
        string engine_name
        float speed
        float exaggeration
        float cfg_weight
        int seed
        string voice_id FK
        datetime created_at
    }
    VOICES {
        string _id PK
        string name
        object samples "lang -> wav path"
        datetime created_at
    }
    RENDER_JOBS {
        string _id PK
        string script_id FK
        string status
        string audio_path
        string audio_url
        datetime audio_replaced_at
        string error
        datetime created_at
        datetime completed_at
    }
    VIDEO_JOBS {
        string _id PK
        string render_job_id FK
        string active_workflow_id
        string image_path
        string audio_url
        string srt_path
        object correctness_check
        string status
        string video_path
        string video_url
        datetime video_rendered_at
        boolean manually_uploaded
        datetime manually_uploaded_at
        string error
        datetime created_at
    }
    VIDEO_METADATA {
        string _id PK
        string render_job_id FK
        string title
        string description
        array tags
        datetime approved_at
    }
```

This has drifted from the ER shape originally proposed (§13): there is no `users`
collection (no auth, §4); `scripts` stores the render parameters directly rather than
splitting them into a separate always-1:1 entity; `video_metadata` keys off
`render_job_id` (one series of metadata per render, reused across caption revisions of
the same video), not `video_job_id`. IDs throughout are plain UUID strings (`str(uuid.uuid4())`),
not `ObjectId` — chosen so the API layer, the Temporal workflow ID (`video-prod-{video_job_id}`),
and the shared-volume directory name (`{video_job_id}/`) can all use the same literal
string with no translation.

### 6.2 Collection field reference

**`scripts`**

| Field | Type | Notes |
|---|---|---|
| `_id` | string (uuid) | |
| `unit_id` | string | matches `mx_narrator`'s `<unit-id>` convention |
| `lang` | string | one of `mx_narrator.prep.registry.available_languages()` (currently `es`/`en`/`pt`) |
| `series_name` | string | groups episodes for `generate_metadata`'s prior-titles context |
| `series_album` | string | MP3 `album` ID3 default; independent of `series_name` |
| `text` | string | the script content, as `mx_narrator` expects it |
| `id3` | object | `{artist, title, album, track, year, genre, comments}` |
| `engine_name`, `speed`, `exaggeration`, `cfg_weight`, `seed` | — | passed straight through to synthesis |
| `voice_id` | string \| null | references a `voices` document; null means the engine's built-in default |
| `created_at` | datetime | |

**`voices`** — user-managed reference voices, independent of any one script

| Field | Type | Notes |
|---|---|---|
| `_id` | string (uuid) | |
| `name` | string | |
| `samples` | object | `{lang: wav_path}` — one reference sample per language, addable/replaceable/deletable independently |
| `created_at` | datetime | |

**`render_jobs`** — one per script render attempt (`AudioGenerationWorkflow`)

| Field | Type | Notes |
|---|---|---|
| `_id` | string (uuid), also the Temporal workflow ID's key | |
| `script_id` | string → `scripts` | |
| `status` | string | `queued` \| `rendering` \| `complete` \| `failed` |
| `audio_path`, `audio_url` | string | shared-volume path and its `/media/...` URL |
| `audio_replaced_at` | datetime | set only when the audio was manually replaced post-completion (§8.4) — drives client-side cache-busting |
| `error` | string | present only when `status == "failed"` |
| `created_at`, `completed_at` | datetime | |

**`video_jobs`** — one per video production attempt for a `render_job`

| Field | Type | Notes |
|---|---|---|
| `_id` | string (uuid) | also the suffix of the owning Temporal workflow ID |
| `render_job_id` | string → `render_jobs` | |
| `active_workflow_id` | string | which Temporal workflow execution currently owns this job — updated when a caption revision starts a fresh `ReviseCaptionsWorkflow` execution, so signals keep reaching the right place |
| `image_path` | string | background image, shared volume |
| `audio_url` | string | copied from the render job at creation time |
| `srt_path` | string | written right after transcription, before human approval, so the review UI can pre-fill from it |
| `correctness_check` | object | `{status: "pass"\|"mismatch", mismatches: [{expected, actual, approx_time}]}` |
| `status` | string | see §7.3 state diagram |
| `video_path`, `video_url` | string | final MP4, once rendered |
| `video_rendered_at` | datetime | set every time `render_video` completes (including revisions) — drives client-side cache-busting, since the URL itself never changes |
| `manually_uploaded`, `manually_uploaded_at` | boolean, datetime | user-toggled, purely for the user's own tracking |
| `error` | string | present only when `status == "failed"` |
| `created_at` | datetime | |

**`video_metadata`** — one per render job's generated YouTube copy

| Field | Type | Notes |
|---|---|---|
| `_id` | string (uuid) | |
| `render_job_id` | string → `render_jobs` | |
| `title`, `description` | string | LLM output, human-editable before approval |
| `tags` | array\<string\> | |
| `approved_at` | datetime | set once the human approves/edits and confirms |

No YouTube video ID, visibility, or publish-status fields — the system never uploads
anything, so there's nothing to track on YouTube's side. `manually_uploaded` exists only
so the dashboard can show "which episodes have I already put up," set by hand.

## 7. Workflows

### 7.1 `AudioGenerationWorkflow`

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Web UI
    participant API as FastAPI
    participant T as Temporal
    participant GW as GPU Worker
    participant M as MongoDB

    U->>UI: Upload script + render params + ID3 tags (+ optional voice_id)
    UI->>API: POST /scripts
    API->>M: insert scripts doc, insert render_jobs (status=rendering)
    API->>T: start AudioGenerationWorkflow(render_job_id)
    T->>GW: Activity: synthesize (task queue: gpu-tasks)
    GW->>GW: mx_narrator: prep -> chunk -> engine.synth -> assemble
    T->>M: mark_render_job(complete, audio_path) or (failed, error)
    API-->>UI: live status via SSE
    UI-->>U: "Audio ready"
```

The Activity body is essentially `src/mx_narrator/batch.py`'s render path, called with
parameters built from the UI form fields instead of CLI args. `synthesize` runs with
`maximum_attempts=1` — a bad engine name, malformed script, or corrupt voice file fails
the same way every time, so retrying blindly would just leave the job stuck at
`rendering` instead of surfacing the failure; transient infra hiccups are handled by
Temporal's own worker-restart durability, not activity-level retry.

### 7.2 `VideoProductionWorkflow`

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Web UI
    participant T as Temporal
    participant GW as GPU Worker
    participant CW as CPU Worker
    participant M as MongoDB
    participant LLM as LLM endpoint<br/>(config-driven)

    U->>UI: Start video production (render_job_id, image)
    UI->>T: start VideoProductionWorkflow
    T->>GW: Activity: transcribe (Whisper large-v2, gpu-tasks)
    T->>M: mark_video_job(checking_correctness, srt_path)
    T->>CW: Activity: correctness_check(script_text, words) (cpu-tasks)
    alt mismatch found
        T->>M: video_jobs.status = mismatch_needs_review, correctness_check
        T->>UI: signal-wait: acknowledge_mismatch
        U->>UI: review mismatches inline (highlighted against caption rows)
        UI->>T: signal: acknowledge_mismatch
    end
    T->>M: video_jobs.status = srt_review_pending
    T->>UI: signal-wait: approve_srt (always required)
    U->>UI: review / edit every caption row
    UI->>T: signal: approve_srt(srt_text)
    T->>GW: Activity: finalize_srt, then align_captions (forced alignment, gpu-tasks)
    T->>M: video_jobs.status = srt_approved, then rendering
    T->>CW: Activity: render_video (ffmpeg: burn in captions, mux audio, cpu-tasks)
    T->>M: video_jobs.status = generating_metadata, video_path, video_rendered_at
    T->>CW: Activity: generate_metadata(render_job_id) (cpu-tasks)
    CW->>M: read series' prior human-approved episode titles (context)
    CW->>LLM: structured completion call (single call, no agent/tool use)
    LLM-->>CW: title / description / tags (schema-validated)
    CW->>M: write video_metadata (draft)
    T->>M: video_jobs.status = metadata_review_pending
    T->>UI: signal-wait: approve_metadata
    U->>UI: edit captions/image/metadata together on one "Final review" screen
    UI->>T: signal: approve_metadata(title, description, tags)
    T->>M: video_jobs.status = ready_for_manual_upload
    T-->>UI: workflow complete — video + metadata ready to download/copy
```

Workflow ends at metadata approval. There is no publish step, no OAuth, no upload
Activity — the user takes the finished MP4 and the approved title/description/tags from
the UI and uploads to YouTube themselves. `generate_metadata` is a single deterministic
Temporal Activity, not an agent — no tool use, no multi-step reasoning, no autonomous
retries beyond Temporal's own bounded `RetryPolicy` (`maximum_attempts=2`: one retry
covers a transient LLM-endpoint network hiccup; a persistent misconfiguration or a
schema-validation failure on the LLM's own output is deterministic and shouldn't retry
indefinitely). It pre-fetches context (prior human-approved episode titles in the same
`series_name`) before making one structured LLM call. The LLM provider and target
machine are both config-driven (`LLM_MODEL`, `LLM_API_BASE`) — defaulting to an
Ollama-served model on the deployment host itself, with a remote API (e.g. Anthropic,
via `ANTHROPIC_API_KEY`) available as an explicit opt-in override. See §10 and §13 for
the technology choice and rationale.

Any Activity failure from `render_video` onward (unattended system work: ffmpeg, an LLM
call) is caught and recorded as `video_jobs.status = "failed"` with the error message —
it does not leave the job silently stuck. Everything before that point is a human
signal-wait with no timeout of its own; `VideoProductionWorkflow` deliberately has no
workflow-level execution timeout, unlike every Activity in this codebase — it's the
first workflow that legitimately sits idle for human review timescales.

### 7.3 `ReviseCaptionsWorkflow`

A second, separate workflow, started after a video job has already reached
`metadata_review_pending`, `ready_for_manual_upload`, or `failed` — i.e., captions have
already been through review once. It re-renders the video against corrected caption
text (and optionally a new background image, and optionally new metadata) without
re-running transcription or the correctness check, since a human edit at this point
already *is* the correction.

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Web UI
    participant API as FastAPI
    participant T as Temporal
    participant GW as GPU Worker
    participant CW as CPU Worker
    participant M as MongoDB

    U->>UI: Edit captions and/or image and/or metadata on Final review
    UI->>API: POST /video_jobs/{id}/revise-all (or /srt/revise, /image/revise)
    alt captions unchanged (parsed text identical)
        API->>T: signal running workflow: approve_metadata (fast path, no re-render)
    else captions or image changed
        API->>T: terminate previous execution, start ReviseCaptionsWorkflow
        T->>M: video_jobs.status = rendering
        T->>GW: Activity: finalize_srt, then align_captions (gpu-tasks)
        T->>CW: Activity: render_video (cpu-tasks)
        T->>M: video_jobs.status = generating_metadata, video_path, video_rendered_at
        alt metadata submitted in the same revise-all call
            T->>CW: Activity: approve_metadata(title, description, tags)
            T->>CW: Activity: reset_manually_uploaded
            T->>M: video_jobs.status = ready_for_manual_upload
        else metadata not touched
            T->>CW: Activity: generate_metadata (regenerate, since caption wording didn't matter here — image-only or caption-only revise)
            T->>M: video_jobs.status = metadata_review_pending
            T->>UI: signal-wait: approve_metadata
        end
    end
```

`POST /video_jobs/{id}/revise-all` (backing the unified Final review screen, §8.3) is
the one endpoint that can touch captions, image, and metadata in a single submit. It
compares the *parsed caption text* of the new SRT against the current one — not the raw
SRT string — to decide whether a re-render is actually needed, since re-serializing
through the caption editor introduces harmless floating-point timestamp drift on every
save even with zero real edits; comparing raw strings was tried first and produced false
"needs re-render" positives. When nothing changed, it takes the fast path: signal the
still-running workflow's `approve_metadata` directly rather than tearing anything down.

`ReviseCaptionsWorkflow` needs its own `approve_metadata` signal — Temporal signals are
scoped to one running execution, so it can't reuse `VideoProductionWorkflow`'s. This
duplicates a small signal-plus-tail block rather than sharing a base class; both
workflows call the exact same Activities, so they can't drift on *what* happens, only on
orchestration order.

### 7.4 `video_jobs.status` state machine

```mermaid
stateDiagram-v2
    [*] --> transcribing
    transcribing --> checking_correctness
    checking_correctness --> mismatch_needs_review: text mismatch found
    checking_correctness --> srt_review_pending: check passed
    mismatch_needs_review --> srt_review_pending: human acknowledges
    srt_review_pending --> srt_approved: human approves captions
    srt_approved --> rendering
    rendering --> generating_metadata
    generating_metadata --> metadata_review_pending
    metadata_review_pending --> ready_for_manual_upload: human approves metadata
    ready_for_manual_upload --> rendering: revise (captions/image changed)
    ready_for_manual_upload --> ready_for_manual_upload: revise (fast path, nothing needed a re-render)
    generating_metadata --> failed: any unattended step throws
    rendering --> failed: any unattended step throws
    failed --> rendering: revise (captions/image changed)
    ready_for_manual_upload --> [*]
```

`ready_for_manual_upload` is a terminal state, not a queue waiting on further system
action — the dashboard can optionally flip `manually_uploaded` later purely for the
user's own tracking, and a job can always be revised out of this state later, but
nothing in the workflow depends on either happening.

The correctness check compares **exact text** — the ground truth is the same
prepared/chunked text `mx_narrator` already fed to TTS — not a fuzzy LLM judgment.
Normalization handles known sources of false mismatches rather than flagging them as
real ones: punctuation and case are stripped, accented vowels fold to their base form
(Whisper is inconsistent about reproducing accents), a handful of Spanish words with two
valid one-word/two-word spellings are merged to one canonical form on both sides, and
transcribed spoken numbers are re-expanded to words (`mx_narrator`'s own prepared text
already spells numbers out; Whisper writes them back as digits) via the same
per-language `expand_numbers()` used during prep. See `worker/diff.py` for the full
normalization pipeline. Whisper transcribes the **final assembled** audio — the same
file synthesis produced — not individual pre-assembly chunks, so timestamps stay in sync
with what the video will actually play.

## 8. Human-in-the-Loop Design

### 8.1 Signal-wait points

Every point below is a Temporal signal-wait:

1. **Correctness-check mismatch** — halts; human acknowledges before continuing. The
   mismatch list is shown highlighted directly against the corresponding caption rows in
   the SRT editor (not a separate list the reviewer has to cross-reference by
   timestamp), so a flagged mismatch and the text to fix it are in the same view.
2. **Caption review** — always required, regardless of correctness-check outcome; human
   reads/edits every caption row before it becomes burned-in text. Editing here is what
   *is* the correction when the automated check flagged something.
3. **Metadata review** — human edits/approves LLM-generated title/description/tags. This
   is the workflow's last step — once approved, the video and metadata sit in the UI,
   finished, waiting for the user to manually upload to YouTube on their own time.

There is deliberately no publish-approval gate, because there is no publish action for
one to gate.

### 8.2 Final review screen

The metadata-review step and everything before it converge on a single "Final review"
screen: the rendered (or in-progress) video, the caption editor (with mismatch
highlighting if any were found), and the title/description/tags/background-image fields
are all visible together, not split across screens or hidden behind a collapsed
section. One save posts a multipart form (`srt_text`, `title`, `description`, `tags`,
optional `image`) to `revise-all`. A tabbed sub-view separates "Captions" from
"Background image" within the same screen when a revise is needed after the fact — an
earlier version used two separate collapsible toggles with links out to the raw SRT and
video, which the user found harder to work with than seeing both directly.

### 8.3 Revise after approval

Once a job reaches `ready_for_manual_upload` or `failed`, the same Final review screen
stays available and can trigger `ReviseCaptionsWorkflow` (§7.3) — for a correction
noticed after the fact, or to recover a failed render without starting over from
transcription.

### 8.4 Replace audio

Independent of video production: on the render-job status page, once a render reaches
`complete` or `failed`, the user can upload a replacement audio file (e.g. after adding
background music externally) that becomes the canonical audio for that render job —
used by any subsequent video production or revision. This is a pure file-and-document
operation with no Temporal involvement (the `AudioGenerationWorkflow` execution has
already finished by then); it does not run ID3 tagging against the upload, since it
might not even be an MP3.

## 9. Security & Secrets

- **`LLM_MODEL`, `LLM_API_BASE`**: plain config (not secrets) selecting the LLM
  provider and target machine for metadata generation — e.g. `LLM_MODEL=ollama/
  llama3.1:8b` with `LLM_API_BASE=http://host.docker.internal:11434` for the
  deployment host's own Ollama instance (the current default), or `hosted_vllm/<model>`
  with a vLLM host's `/v1` endpoint for a different LAN machine.
- **`ANTHROPIC_API_KEY`**: `.env`-provided, excluded from any image build context —
  **only required when `LLM_MODEL` is explicitly configured to select a remote
  provider** (e.g. `anthropic/claude-...`). Not required, and not read, when using the
  LAN-hosted default. When it is in use, it's the system's only outbound network
  dependency to a third party.
- **Auth**: none (§4). The API and UI are exposed only on the local network — not a
  public internet-facing service. Treat reachability to the Docker host as equivalent to
  full access to the system; there is no further access control layer.
- **`MONGODB_DATABASE`**: config, not a secret — decouples the Mongo database name from
  the Docker Compose project name, specifically so a cosmetic project rename (§13) never
  implies migrating or renaming live data.

## 10. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend/API | FastAPI (Python) | `mx_narrator` is already Python; Temporal's Python SDK (`temporalio`) is first-class. |
| Frontend | React 19 + Vite, plain JavaScript (ES Modules, no TypeScript), inline CSS-in-JS with a shared color-token system | Matches the user's other trilingual Bible project — same conventions, same stack, no new tooling to learn or maintain. |
| Workflow engine | Temporal, self-hosted via Docker Compose | Durable execution + native signal/query primitives, which map directly onto "pause and wait for a human." |
| Database | MongoDB (Motor async driver), self-hosted via Docker | Self-hosted, not managed cloud, per the project's general cost/ownership stance. |
| Auth | None (§4, §9) | Single-user, single-network tool; no external identity provider or session layer exists. |
| Video captions | **Burned in** (`ffmpeg -vf subtitles=...`, libass), not a soft/muxed track | Changed from the original soft-track design: a `mov_text` side-track alone turned out invisible in practice — no common player auto-displays it, and YouTube doesn't pull captions from one either. A `mov_text` track is still muxed in alongside the burned-in text, but burned-in is what actually makes captions visible without the viewer taking any action. |
| Caption timing | Whisper (`faster-whisper`, model `large-v2`) for the initial transcript, then forced word-level alignment (`worker/align.py`) of the *human-approved* text against the real audio | Whisper's own segment boundaries can drift; realigning the approved text keeps caption timing tied to the actual speech rather than to whatever Whisper guessed before the human's edits. Best-effort — a failed alignment degrades gracefully (falls back to Whisper's own timing) rather than blocking the workflow. |
| LLM access (metadata generation) | LiteLLM, one function-call abstraction (`litellm.acompletion(model=..., ...)`), model/provider selected via config (`LLM_MODEL`/`LLM_API_BASE`), local-network-first default | Not an agent framework — this task is a single structured completion, not tool use/multi-step reasoning. Covers Ollama, vLLM (`hosted_vllm/*`), and Anthropic through the same call shape; swapping the model string is the entire provider-switch surface. |

### 10.1 Observability & Live Progress

The web UI itself shows live pipeline progress — the user is never sent to Temporal's
separate Web UI (still available at `:8080` for deeper debugging) to check on things.

- **Live status push, not polling.** Every Activity writes a status transition to
  MongoDB (`render_jobs.status`, `video_jobs.status`, and every other field on those
  documents) as it progresses. The API watches these via a **MongoDB change stream**
  per open job and pushes the *entire updated document* to connected UI clients over
  **Server-Sent Events** (`GET /render_jobs/{id}/events`, `GET /video_jobs/{id}/events`).
  Because the whole document is serialized generically (`datetime` → ISO string, no
  per-field allowlist), any new field added to a job document automatically reaches the
  frontend with no additional plumbing. The dashboard and any open review screen update
  in real time with no manual refresh.
- **Structured logging.** Workers and the API emit logs with consistent fields
  (`workflow_id`, `job_id`, `stage`, `status`) to stdout, captured by Docker's own
  logging driver — `docker compose logs -f` is the debugging path for a specific job.
- **Metrics.** Temporal's own Prometheus metrics and Web UI cover workflow/activity-level
  observability; no separate Grafana/Prometheus stack exists, since the UI's own
  dashboard (aggregated from MongoDB) already covers the stated need.
- **`GET /dashboard`**: counts of episodes per pipeline stage plus a recent-activity
  feed, aggregated server-side from MongoDB.
- **Media caching.** `StaticFiles` sets `Last-Modified`/`ETag` but no `Cache-Control` by
  default, and a video/audio URL's path never changes across a re-render or a replace —
  which let browsers serve a stale cached file indefinitely after a real update
  server-side. Fixed with two parts, applied identically to video and to replaced audio:
  a `Cache-Control: no-cache` middleware on all `/media/*` responses (the browser still
  validates via ETag rather than caching blind), and a client-side `?t=<timestamp>`
  query param on the `<video>`/`<audio>` `src`, keyed off `video_rendered_at` /
  `audio_replaced_at` so the URL actually changes when the content does.

## 11. Reused From `mx_narrator`

| Component | File | Reused as |
|---|---|---|
| Render orchestration | `src/mx_narrator/batch.py` | Body of the `synthesize` Activity |
| Text prep + scripture/number expansion | `src/mx_narrator/prep/` | Also re-run to derive correctness-check ground truth and to normalize Whisper's transcript |
| Chunking | `src/mx_narrator/chunk.py` | Also used for ground truth |
| Engines | `src/mx_narrator/engines/chatterbox.py`, `kokoro.py` | Real voice cloning |
| Assembly + ID3 tagging | `src/mx_narrator/assemble.py` | `tag_mp3()` |
| Voice resolution | `src/mx_narrator/voices.py` | Underlies the `voices` collection's per-language sample resolution |

## 12. Decision Log

Kept as a record of *why* things are the way they are — not reproduced from scratch each
time this document changes, only appended to.

- **Subtitle burn-in vs. soft track** → started as soft-track-only (§10 originally), then
  changed to burned-in after the soft track proved invisible in every real player and on
  YouTube itself. A `mov_text` track is still muxed alongside the burned-in text.
- **Caption timing** → Whisper's own segment timing, then forced alignment of the
  human-approved text was added on top once Whisper-only timing was observed to drift
  from the actual speech in some episodes.
- **Correctness-check UX** → mismatches were originally a separate list keyed by
  timestamp; changed to inline highlighting directly on the corresponding caption rows
  after a real review session showed the separate-list version required the reviewer to
  hold timestamps in their head to connect a flagged mismatch to the text that needed
  fixing.
- **Metadata + captions + image review** → originally three separate screens/toggles;
  unified into one "Final review" screen with a tabbed sub-view for captions vs. image,
  after the split version (collapsed sections, two out-of-line links to the raw SRT and
  video) was found harder to actually review from than seeing everything together.
- **Revise after approval** (`ReviseCaptionsWorkflow`) → added once real use showed a
  mistake is sometimes only caught after a job already reached `ready_for_manual_upload`
  or failed a render; re-running the entire pipeline from transcription was unnecessary
  since a human edit at that point already is the correction.
- **Frontend framework** → React 19 + Vite, plain JS, matching the user's other
  trilingual Bible project (`ebpi`) — same conventions, no new tooling.
- **Real YouTube API publishing (with a human approval gate)** — this was the initial
  direction and was fully designed (OAuth, publish worker, publish-approval signal,
  default-private-then-make-public safety layer) before being explicitly reversed: even
  a gated automated publish is more surface (credentials, quota, a real API call that
  goes live somewhere) than the actual need, which is just having finished assets ready
  for a human to upload by hand.
- **LLM-based fuzzy correctness check** — considered, rejected in favor of exact-text
  comparison: the ground truth is fully known (`mx_narrator`'s own prepared text), so
  fuzzy semantic judgment would only add cost/latency without adding accuracy; the real
  risk is timing sync, not content ambiguity.
- **Anthropic API as the only metadata-generation provider** — this was the original
  design, reconsidered once it became clear the user already has machines on their home
  network capable of running Ollama or vLLM — using one of those by default means no
  data leaves the network by default, not just "except one deliberate call." A remote
  API remains available as a config-driven opt-in via the same `LLM_MODEL`/
  `LLM_API_BASE` mechanism.
- **LiteLLM over Pydantic AI or a hand-rolled adapter** — Pydantic AI was rejected
  because its core primitive is literally named `Agent` and it's positioned as an agent
  framework, conceptually the wrong shape for one deterministic completion call with
  pre-fetched context. A hand-rolled per-provider adapter was rejected because each
  provider's JSON-schema-constrained-decoding wire format genuinely differs (Ollama's
  `format`, vLLM's `guided_json`/`response_format`, Anthropic's forced-tool-use trick) —
  a solved problem, not worth reimplementing per provider.
- **`mx-narrator` rename** — the project (and Python package, `src/narrator/` →
  `src/mx_narrator/`) was renamed from `narrator`/`narrator-studio` to avoid a name
  collision on PyPI/GitHub. The rename deliberately did **not** touch the Docker Compose
  volume names or `MONGODB_DATABASE`'s value, so no production data needed migrating for
  a purely cosmetic change (§5.2, §9).

## 13. Proposed Rollout (historical — completed)

The original phased plan, kept for reference:

1. Docker Compose skeleton: Temporal + Mongo + Temporal UI, no application code yet.
2. `AudioGenerationWorkflow` + minimal UI (upload script, set tags, trigger render, see
   status).
3. `VideoProductionWorkflow` stages one at a time: transcription → correctness check →
   caption review UI → video render → metadata generation → metadata review UI.
4. Hardening pass: secrets management, error/retry policy tuning, worker resource
   limits.

All four phases are complete, followed by substantial iteration beyond the original
scope (forced alignment, mismatch highlighting, the unified Final review screen, revise-
after-approval, audio replacement, the burn-in switch, the project rename) — captured
above rather than as a fifth phase, since this document no longer tracks toward a single
finish line.

---

*This document is maintained alongside the system it describes. When in doubt about
whether something here is still accurate, the code is the final authority — update this
document to match it, not the other way around.*
