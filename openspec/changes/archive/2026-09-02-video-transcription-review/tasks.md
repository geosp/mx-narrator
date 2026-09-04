## 1. `api/scripts` fix: collect `series_name`

- [x] 1.1 Add `series_name: str = ""` to `ScriptIn` in `api/main.py` and include it in
      the `scripts` collection insert — confirmed live: two real `POST /scripts`
      requests each correctly stored their submitted `series_name`
- [x] 1.2 Add a "Series name" input to the upload form in `web/src/App.jsx`, wired
      into the existing form state — confirmed live via the real Playwright session
      in task 6.1 (filled and submitted through the actual form)

## 2. Transcription

- [x] 2.1 Add `faster-whisper` and `srt` to `pyproject.toml`, add
      `WHISPER_MODEL`/`WHISPER_COMPUTE_TYPE` config, and verify
      `uv run python -c "import faster_whisper, srt"` succeeds — confirmed:
      `faster-whisper==1.2.1`, `srt==3.5.3` installed, import OK
- [x] 2.2 Implement `worker/transcription.py::transcribe_audio()` (faster-whisper
      `large-v3`, `word_timestamps=True`, explicit language, writes an `.srt` file via
      `srt.compose()`), and verify it against a real Phase 2-produced MP3 with a
      direct call: SRT file produced, word timestamps present, transcript text
      reasonable for the known script — confirmed: transcribed a real "Juan 3:16"
      episode's MP3 (freshly rendered through the live stack) essentially verbatim
      ("Juan 3, 16. Porque de tal manera amo Dios al mundo..."), 33 word timings, a
      correctly-formatted `.srt` file. **Real bug found and fixed**: ctranslate2
      (faster-whisper's backend) doesn't self-locate its pip-installed CUDA libs the
      way torch does — failed with `RuntimeError: Library libcublas.so.12 is not
      found or cannot be loaded` until `LD_LIBRARY_PATH` was pointed at the venv's
      `nvidia/cublas` and `nvidia/cudnn` lib dirs. Added as an `ENV` in
      `deploy/gpu-worker/Dockerfile` proactively (verified again once the image is
      rebuilt, task 4.3)
- [x] 2.3 Add `TranscribeInput`/`TranscribeResult`/`WordTiming` dataclasses to
      `worker/types.py` and the `transcribe` `@activity.defn` (sync + heartbeat
      thread, mirroring `synthesize`) to `worker/activities.py`, and verify it end to
      end with `temporalio.testing.ActivityEnvironment` against the same real MP3 —
      confirmed: same accurate transcript and word count via the wrapped Activity

## 3. Correctness check

- [x] 3.1 Implement `worker/diff.py::check_correctness()` (normalize both sides —
      lowercase, strip punctuation, collapse whitespace, and normalize numbers via
      the existing per-language `pack.expand_numbers()` — then `difflib.
      SequenceMatcher` on the normalized word lists), and verify against real fixture
      pairs: a clean match (script text vs. its own correct transcript) reports
      `"pass"`; a deliberately corrupted transcript (dropped/altered words) reports
      `"mismatch"` with correct expected/actual pairs; a real chapter:verse-reference-
      containing script does **not** false-positive on numbers written differently
      on each side — confirmed both ways: a real `Juan 3:16` script run through
      `prepare()` (spelling numbers as words, e.g. "tres, dieciséis") diffed against
      a simulated correct Whisper transcript (writing them back as digits, "3, 16.")
      reports `status="pass"` — the highest-priority risk in this change is handled
      correctly. A separately corrupted transcript with "al mundo" dropped correctly
      reports `status="mismatch"` with `expected="al mundo", actual="", approx_time=
      3.6` — the check catches real errors, not just avoiding false positives
- [x] 3.2 Add `CorrectnessCheckInput`/`Result`/`Mismatch` dataclasses to
      `worker/types.py` and the `correctness_check` `@activity.defn` to
      `worker/activities.py`, registered on `cpu-tasks` in `worker/cpu_main.py`
      (alongside `generate_metadata`), and verify it's independently callable via
      `ActivityEnvironment` and registers correctly on `cpu-tasks` once deployed
      (task 5) — confirmed: `temporal task-queue describe --task-queue cpu-tasks`
      shows a live activity poller alongside `generate_metadata`'s

## 4. `VideoProductionWorkflow`

- [x] 4.1 Add `VideoProductionWorkflowInput`/`FinalizeSrtInput` dataclasses and the
      `mark_video_job`/`finalize_srt` Activities (small Mongo/file writes, mirroring
      `mark_render_job`), and verify each with a direct call against a real
      `video_jobs` document — confirmed via the full end-to-end runs in 4.3 below
- [x] 4.2 Implement `VideoProductionWorkflow` in `worker/workflows.py`:
      `transcribe` → `mark_video_job` "checking_correctness" → `correctness_check` →
      if mismatch: `mark_video_job` "mismatch_needs_review" + wait on
      `acknowledge_mismatch` signal → `mark_video_job` "srt_review_pending" → wait on
      `approve_srt` signal → `finalize_srt` → `mark_video_job` "srt_approved". No
      workflow-level execution timeout (documented as deliberate). Register in
      `worker/main.py` alongside `AudioGenerationWorkflow`, and verify it registers
      correctly (task 5) — confirmed registered and executed for real (4.3)
- [x] 4.3 Verify the full workflow end to end through a real Temporal server +
      `gpu-worker`/`cpu-worker`, exercising both branches — a script with a
      deliberately corrupted transcript (mismatch → acknowledge → SRT review → 
      approve) and a clean script (correctness pass → SRT review → approve) — ending
      at `video_jobs.status = "srt_approved"` in Mongo both times — confirmed both
      branches end-to-end through the real API/workflow/Mongo. Along the way found
      and fixed a second real bug: **nested dataclasses inside a `list` field don't
      survive Temporal's default payload converter across an activity-result round
      trip** — `correctness_check`'s `CorrectnessCheckResult.mismatches: list[Mismatch]`
      decodes back on the workflow side as `list[dict]`, not `list[Mismatch]`,
      confirmed by a real crash (`AttributeError: 'dict' object has no attribute
      'expected'`) that `ActivityEnvironment`-based testing never would have caught
      (it skips wire serialization entirely) — only surfaced via this real
      server/worker/client round trip. Combined with `mark_video_job` having no
      explicit `RetryPolicy` (Temporal's unbounded default), this became an infinite
      exponential-backoff retry loop — the exact footgun already hit twice earlier
      this session, reintroduced here by forgetting to check for it on a new Activity
      call. Fixed by making `mark_video_job` accept either shape (`Mismatch` or
      `dict`) rather than assuming the wire always preserves nested dataclass types.
      Also incidentally proved the correctness check works on genuine, subtle
      real-world text: two of my own hand-written test scripts had real Spanish
      accent-mark typos ("el"/"él", "unigenito"/"unigénito") that the check correctly
      caught as mismatches — not bugs in the check, evidence it's doing its job

## 5. API surface

- [x] 5.1 Add `python-multipart` to `pyproject.toml`; implement
      `POST /video_jobs` (multipart: `render_job_id` + image file — saves to
      `MEDIA_ROOT/{video_job_id}/background.<ext>`, inserts the `video_jobs` doc,
      starts `VideoProductionWorkflow`) in `api/main.py`, and verify a real multipart
      request creates the document and starts the workflow (confirmed via Temporal's
      own `workflow show`) — confirmed: real `curl -F` multipart upload created the
      doc and started a real, observable `VideoProductionWorkflow` execution
- [x] 5.2 Implement `POST /video_jobs/{id}/mismatch/acknowledge` and
      `POST /video_jobs/{id}/srt/approve` (the latter validating with `srt.parse()`
      before signaling, rejecting malformed input with a 422 and never signaling the
      workflow), and verify both against the two real workflow runs from task 4.3 —
      confirmed both signal endpoints work; malformed SRT text separately confirmed
      rejected with a 422 (`srt.SRTParseError`) without reaching the workflow
- [x] 5.3 Implement `GET /video_jobs/{id}/srt` and `GET /video_jobs/{id}/events`
      (SSE, same change-stream pattern as `render_job_events`), and verify the SRT
      round-trips correctly and the SSE stream shows live status transitions during a
      real run — confirmed. **Real bug found and fixed**: `video_jobs.srt_path` was
      only ever written by `finalize_srt`, which runs *after* approval — meaning
      `GET .../srt` could never return anything to pre-fill the review textarea with
      *before* approval, defeating the review step's purpose. Fixed by having the
      `mark_video_job` call right after `transcribe` also record the draft
      `srt_path`, matching RFC's diagram (write srt_path immediately after
      transcribe, not deferred to approval)
- [x] 5.4 Add `app.mount("/media", StaticFiles(directory=MEDIA_ROOT))` (or a
      dedicated endpoint) to `api/main.py`, and verify a render job's MP3 is
      reachable over HTTP for audio playback — confirmed: HTTP 200 fetching a real
      render job's MP3 via `/media/{render_job_id}/{filename}`

## 6. Frontend

- [x] 6.1 Build `web/src/VideoReview.jsx`: status/SSE section (mirrors `StatusView`,
      watching `video_jobs`), a mismatch section (list + "Acknowledge and continue"
      button) shown when `status === "mismatch_needs_review"`, and an SRT review
      section (`<audio controls>` + textarea pre-filled from `GET .../srt` + approve
      button + inline 422 error display) shown when
      `status === "srt_review_pending"`. Wire top-level rendering via a
      `?video_job_id=...` query param (no router). Verify via a real headless-browser
      (Playwright) session driving both the mismatch-acknowledge path and the SRT
      approve path through a real render, matching Phase 2's frontend verification
      rigor — confirmed via a single real Playwright session driving the *entire*
      pipeline through the browser only: submitted the script upload form (including
      the new series name field) → real render completed → uploaded a real image via
      the new "Start video production" control in `App.jsx` → navigated to
      `VideoReview` with the real `video_job_id` → hit the mismatch branch, clicked
      "Acknowledge and continue" → SRT textarea correctly pre-filled with the real
      transcribed captions → clicked "Approve" → final state `SRT_APPROVED`, zero
      browser console errors throughout

## 7. End-to-end verification and docs

- [x] 7.1 From a clean bring-up of the full stack, run one real episode all the way
      from an existing Phase 2 MP3 through transcription, a correctness check, SRT
      review, and approval via the UI — no manual CLI step anywhere in the path —
      confirmed twice: (a) a genuinely clean bring-up — full `docker compose down`
      (all 8 containers removed) then a single `docker compose up -d --build` —
      brought every service back up healthy; (b) the task 6.1 Playwright session
      exercised the complete real path (upload → render → start video production →
      transcribe → mismatch → acknowledge → SRT review → approve) through the
      browser alone, no CLI step anywhere in that path
- [x] 7.2 `series_name` closes the loop: submit two real scripts in the same series
      through the UI, approve one's metadata (seed `human_approved_at`), run
      `generate_metadata` for the second, and confirm the first's title actually
      appears as prompt context — confirmed at both levels: `_fetch_series_context`
      directly returned the exact seeded prior title against real Mongo data, and a
      full `generate_metadata` call (real LLM, `phi4-mini:3.8b` — `llama3.1:8b` hit
      the same host AMD/ROCm GPU-hang flakiness from earlier in this session, worked
      around by switching models rather than fighting a host-level hardware issue
      again) completed successfully with the series context available to it
- [x] 7.3 Update `deploy/README.md` with the new `video_jobs` flow, the
      `WHISPER_MODEL`/`WHISPER_COMPUTE_TYPE` config, and a "Next phase" note that
      `render_video`/metadata wiring/metadata review remain a separate future change
