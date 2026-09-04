## Why

User asked: since we already have the script text, do we really need full ASR
transcription just to sync captions to audio? Investigation found the real
answer is nuanced — Whisper's transcription currently does two jobs at once:
(1) independently verifying TTS actually said what the script says
(`correctness_check`), and (2) sourcing the caption text/timing shown to the
user and burned into video.

Forced alignment (given known-correct text, find where each word occurs in
the audio) is a fundamentally different, much cheaper technique that could
replace job #2 — but empirical testing (three deliberate real-audio
corruptions: substitution, deletion, insertion) confirmed it **cannot safely
replace job #1**: it completely failed to detect a dropped word (the aligner
silently absorbed the missing word's audio into neighboring word boundaries,
zero score anomaly), which is likely TTS's single most common failure mode.
Substitution and insertion were detectable, deletion was not — disqualifying
a full replacement of the ASR-based QA gate.

## What Changes

Hybrid approach: `worker/diff.py`'s ASR-based `correctness_check` stays
completely unchanged as the QA gate. New: once caption text is *already
trusted* (a clean correctness_check pass, or the user's own manual SrtReview
corrections), a new `align_captions` step re-times each SRT entry's
start/end to the exact word boundaries CTC forced alignment finds in the
real audio — tighter sync, using the exact approved wording instead of
Whisper's own (sometimes slightly different, and potentially *stale* after a
manual text edit) segment timestamps.

- New `worker/align.py`: `align_captions(audio_path, lang, srt_path)` using
  `ctc-forced-aligner` (MMS/wav2vec2-CTC, BSD-licensed package; the
  underlying model itself is CC-BY-NC-4.0 — confirmed this project is
  non-commercial, so that's not a blocker). Best-effort by design: any
  internal failure or word-count mismatch between the SRT and the aligner's
  output leaves the existing SRT untouched rather than risk corrupting
  caption sync.
- New `align_captions` Activity (`worker/activities.py`), registered on
  `gpu-tasks` (`worker/main.py`) — runs right after `finalize_srt` in both
  `VideoProductionWorkflow` and `ReviseCaptionsWorkflow`, before
  `render_video`. New `ALIGN_CAPTIONS_RETRY_POLICY`/timeout in
  `worker/workflows.py`.
- `ReviseCaptionsWorkflowInput` gained a required `lang` field (needed by
  the aligner; `api/main.py`'s `/video_jobs/{id}/srt/revise` now passes
  `render_job["lang"]`, which every render_job document already has).
- `pyproject.toml`: `ctc-forced-aligner`, pinned to a specific git commit
  (matching the existing `chatterbox-tts` pattern) rather than the PyPI
  release — PyPI's published 1.0.2 replaced the low-level API this is built
  on with an unrelated, unvalidated higher-level interface.
- `deploy/gpu-worker/Dockerfile`: added `build-essential` (a native extension
  needs compiling during `uv sync` for this git-sourced package).

## Capabilities

No new API/data-model/UI contract — this improves the accuracy of an
existing capability (caption timing) the same way the transcription-tuning
changes did, not a new one. `skip_specs: true`.

## Impact

- New files: `worker/align.py`.
- Modified: `worker/activities.py`, `worker/workflows.py`, `worker/main.py`,
  `worker/types.py`, `api/main.py`, `pyproject.toml`, `uv.lock`,
  `deploy/gpu-worker/Dockerfile`.
- Verified via a real, isolated proof-of-concept against real episode audio
  before any implementation: measured alignment quality/speed (~13s for a
  16-minute episode, vs. Whisper's 85-256s), and the critical
  substitution/deletion/insertion detectability test that determined the
  hybrid design (see Why).
- Verified end-to-end through the real Temporal pipeline on both workflows:
  created a throwaway `video_job`, ran transcribe → correctness_check →
  finalize_srt → align_captions → render_video → generate_metadata →
  approve_metadata to `ready_for_manual_upload`, confirmed the SRT's
  timestamps changed (tightened) with no errors; then triggered
  `ReviseCaptionsWorkflow` with a real text edit and confirmed both the edit
  and its re-alignment applied correctly.
- Caught and fixed a real deploy-consistency bug during verification: `api`
  and `cpu-worker` reuse the `gpu-worker` image but weren't redeployed
  alongside it, so `api` briefly ran old code that omitted
  `ReviseCaptionsWorkflowInput.lang`, causing a real `TypeError` on workflow
  input deserialization. Fixed by redeploying all three services together;
  the stuck failing workflow execution was terminated and the revise
  retried successfully.
- Also caught and fixed: `uv.lock` wasn't regenerated after adding the new
  dependency to `pyproject.toml`, so the Dockerfile's `uv sync --frozen`
  silently didn't lock it in, and `uv run` was falling back to an ad-hoc
  network install/build at every container *startup*. Fixed with `uv lock`
  before rebuilding.
