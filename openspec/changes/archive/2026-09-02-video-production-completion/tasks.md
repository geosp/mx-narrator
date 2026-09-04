## 1. Video rendering

- [x] 1.1 Add `worker/video.py::render_video()` (ffmpeg: loop image, mux audio +
      approved SRT as a `mov_text` soft subtitle track, `-r 1` low framerate,
      `-shortest`) — kept out of `src/narrator/` (video production was never part
      of the original CLI's scope) — verified via real `ffprobe` output on a
      produced file: exactly one h264 video stream, one AAC audio stream, one
      `mov_text` subtitle stream, duration matching the source audio exactly
- [x] 1.2 Add `RenderVideoInput`/`RenderVideoResult` (`worker/types.py`) and the
      `render_video` Activity (`worker/activities.py`), routed to `cpu-tasks`
      (pure muxing, no GPU) with `maximum_attempts=1` (deterministic given its
      inputs, same reasoning as `correctness_check`) — registered in
      `worker/cpu_main.py`
- [x] 1.3 Thread `image_path` into `VideoProductionWorkflowInput` and
      `create_video_job` (`api/main.py`) — verified the workflow actually receives
      and uses the real uploaded background image path

## 2. Metadata generation and review

- [x] 2.1 Add `save_metadata_draft`/`approve_metadata` Activities and
      `SaveMetadataDraftInput`/`ApproveMetadataInput` — `generate_metadata` itself
      left completely unchanged from `llm-metadata-generation` — verified a real
      call produced a genuine LLM-generated title/description/tags draft in
      `video_metadata`, and that editing and approving through the API correctly
      overwrote them with the human-edited values plus a `human_approved_at`
      timestamp
- [x] 2.2 Wire both into `VideoProductionWorkflow` (`worker/workflows.py`):
      `rendering` → `generating_metadata` → `metadata_review_pending` → (signal
      `approve_metadata`) → `ready_for_manual_upload` — verified a real episode
      end to end through all four transitions via direct API/SSE polling
- [x] 2.3 Verify `_fetch_series_context` (dormant since `llm-metadata-generation`,
      never having had real data) now returns real data: approved a first
      episode's metadata, submitted a second script in the same series, and
      confirmed `_fetch_series_context` returned the first episode's real approved
      title — and that the second episode's own LLM-generated description
      organically referenced "previous episodes," confirming the context actually
      reached the prompt

## 3. API and terminal-state bookkeeping

- [x] 3.1 Add `GET /video_jobs/{id}/metadata`, `POST
      /video_jobs/{id}/metadata/approve` (signals the workflow, mirroring
      `approve_srt`), and `POST /video_jobs/{id}/manually_uploaded` (direct Mongo
      write, no signal — the workflow has already completed; no YouTube call of
      any kind, per RFC §6.2) — verified all three against real data, including
      the manually-uploaded flag persisting across a real page reload

## 4. Failure handling (found necessary during verification, not pre-planned)

- [x] 4.1 Wrap the `render_video` → `generate_metadata` → `save_metadata_draft`
      span in a try/except recording `video_jobs.status = "failed"` with an error
      message — closes the gap `episode-lifecycle-management`'s design.md already
      flagged as deferred, hit for real: the first verification run failed with
      "No such file or directory" because `cpu-worker` had no `MEDIA_ROOT` volume
      mounted (it previously only did pure-text/LLM work). Fixed in
      `deploy/docker-compose.yml`, then reran the exact same episode successfully

## 5. Frontend

- [x] 5.1 `web/src/VideoReview.jsx`: busy state for `rendering`/
      `generating_metadata`; a metadata review form (editable title/description/
      tags, prefilled from the draft, plus a `<video>` preview) for
      `metadata_review_pending`; a `ready_for_manual_upload` screen (final video,
      approved metadata, a manually-uploaded checkbox); a `failed` error display.
      New status colors in `web/src/lib.js` — verified via a full real Playwright
      session driving the entire remaining pipeline through the browser alone:
      mismatch acknowledge → SRT approve → (real wait through rendering +
      metadata generation) → metadata review with a video preview and a prefilled
      title → edited and approved → terminal screen showing the edited title and
      a real playable video → manually-uploaded checkbox toggled and confirmed
      persisted after a real page reload

## 6. Documentation

- [x] 6.1 This proposal/design/spec-delta set, written and archived alongside the
      implementation above — not left to drift, per the standing instruction this
      session.
