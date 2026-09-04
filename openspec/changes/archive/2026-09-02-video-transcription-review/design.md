## Context

Phase 2 (`AudioGenerationWorkflow`) and `llm-metadata-generation` (a standalone
`generate_metadata` Activity, not yet wired into any workflow) are both complete and
archived. This is the first slice of Phase 3 (`VideoProductionWorkflow`, RFC §7.2).
See proposal.md for motivation and scoping rationale.

## Goals / Non-Goals

**Goals:**
- Transcribe a finished MP3, run an exact-text correctness check against narrator's
  own known TTS input, and get a human-approved SRT file — the first three stages of
  `VideoProductionWorkflow`, and this codebase's first use of Temporal signal-wait
  (human-in-the-loop).
- Fix `api/scripts` so `generate_metadata`'s series-context feature has real data.

**Non-Goals:**
- `render_video` (ffmpeg image+audio+subtitle muxing) — no video/image handling
  exists anywhere in this codebase yet; a separate future change.
- Wiring `generate_metadata` into `VideoProductionWorkflow`, or the metadata-review
  signal-wait — `generate_metadata` stays standalone until the follow-up change.
- A "retry render" path for correctness-check mismatches (re-invoking
  `AudioGenerationWorkflow`) — real cross-workflow orchestration, speculative until
  real-world mismatch frequency is known. This slice implements
  acknowledge-and-continue only.
- Auth/attribution on the new signal endpoints — consistent with Phase 2's already-
  accepted "no auth yet" gap, not a new omission specific to this change.

## Decisions

- **faster-whisper, `large-v3`, `compute_type="int8_float16"`, explicit
  `language=<script's lang>`, `word_timestamps=True`.** Confirmed via live research
  as the right library for an NVIDIA GPU in Docker (CTranslate2 backend, clear
  speed/VRAM winner vs. whisper.cpp/openai-whisper; all three share the same
  underlying weights so accuracy is equivalent). `large-v3` over a smaller model
  deliberately: the correctness check's trustworthiness depends entirely on
  transcription accuracy, and a smaller model mishears scripture vocabulary/
  chapter:verse phrasing more — exactly where false positives would hurt most.
  Configurable via `WHISPER_MODEL`/`WHISPER_COMPUTE_TYPE` env vars, mirroring the
  `LLM_MODEL` precedent from `llm-metadata-generation`.
- **No new VRAM-contention handling needed.** `gpu-worker`'s `Worker(...)` already has
  `max_concurrent_activities=1` (narrator's own single-GPU constraint) — Whisper and
  Chatterbox never run concurrently in one process regardless. `transcribe` reloads
  its model fresh per call, same already-accepted inefficiency as `synthesize`.
- **`.srt` is written immediately inside `transcribe`**, using the `srt` PyPI package
  (`srt.compose()`/`srt.parse()`) — matches RFC's diagram (write right after
  transcribe), and a small well-scoped library is the right size of abstraction for
  correct timestamp formatting and round-tripping human-edited text later, same
  precedent as including LiteLLM in the prior change.
- **`correctness_check` ground truth is `prepare(script_text, lang).full_text`
  alone**, not also `chunk_prepared_script()` as RFC §7.3's prose literally says —
  chunking exists to size TTS calls, not to produce a flat comparison string;
  `full_text` already is that flat, ordered ground truth. This is a disclosed
  correction to the RFC's imprecise wording, not a new design choice.
- **Diff algorithm: stdlib `difflib.SequenceMatcher`** on normalized word lists —
  zero new dependency, `get_opcodes()` gives exactly the equal/replace/delete/insert
  spans needed for `{expected, actual, approx_time}` mismatches. Not a fuzzy/
  Levenshtein-style library — RFC §13 already rejected fuzzy/LLM judgment in favor of
  exact-text comparison.
- **Normalization must include number normalization — the single highest-leverage
  correctness decision in this change.** Narrator's prepared text spells numbers out
  as words (`prepare()`'s own expansion step); Whisper's raw transcript writes spoken
  numbers back as digits. Left unhandled, this creates a *systematic* false-positive
  mismatch on every chapter:verse reference and enumerated number in every script —
  in a Bible-reflection project, that's most sentences. Fix: reuse the existing
  per-language `pack.expand_numbers()` (already generic over arbitrary text) on
  Whisper's transcript before diffing, so both sides share the same canonical form.
  No new code path — the same function `prepare()` already calls, applied to the
  other side of the comparison. Also: lowercase, strip punctuation, collapse
  whitespace on both sides.
- **`correctness_check` runs on `cpu-tasks`, not `gpu-tasks`** — it's pure CPU text
  processing with no GPU/model dependency, exactly what `cpu-worker` (already
  running `generate_metadata`) exists for. One `task_queue=` argument difference at
  the call site, no new service.
- **Signals**: `acknowledge_mismatch()` (no payload — no auth to attribute it to,
  Temporal's own history already timestamps it) and `approve_srt(srt_text: str)`
  (the full edited SRT text, one-shot, no partial-save stream — matches a
  single-reviewer raw-textarea UI). **Validation happens at the API boundary**
  (`srt.parse()` before `handle.signal(...)`), not inside the signal handler, since
  signals are fire-and-forget with no synchronous return path for rejecting bad
  input — matches the existing `ScriptIn`/`available_languages()` validate-at-the-
  edge convention.
- **No workflow-level execution timeout** (or a very generous one, e.g. weeks) — this
  is the first workflow that legitimately sits idle for human timescales. Every
  existing timeout elsewhere in this codebase is Activity-scoped; this is a
  deliberate exception to that pattern, not an oversight, and is called out with an
  explicit comment in the workflow module.
- **New API surface stays on the existing `api` service** — RFC §7.2's sequence
  diagram omits an "API" participant (unlike §7.1's, which explicitly shows
  `UI->>API->>T`), read as diagram economy, not a design change; Phase 2 already
  established API-mediates-everything (Mongo writes, workflow start/signal, SSE), and
  this change keeps that consistent rather than introducing direct UI→Temporal
  integration.
- **First multipart/file-upload endpoint in this API** (`POST /video_jobs`, image
  upload) — needs `python-multipart` added explicitly (FastAPI's file/form parsing
  depends on it at request time, not import time, so it's easy to miss).
- **New static-media-serving gap, built now rather than discovered later**:
  `api/main.py` has no way to serve audio playback today. RFC §8 frames SRT review as
  reviewing text "before it becomes captions" — reviewing blind text with no audio
  is a materially weaker review than the RFC asks for. `app.mount("/media", ...)`
  costs nothing and directly serves that intent.
- **Frontend: raw-textarea SRT editing + a native `<audio controls>` element**, no
  waveform/scrubber/click-to-seek — matches this project's established minimal,
  inline-styled, no-framework convention (Phase 2's UI), and real UI engineering
  effort beyond that isn't what a single-user internal tool calls for. New file
  `web/src/VideoReview.jsx` (not grown into `App.jsx`, which is Phase 2's one
  screen) — no router added (`package.json` has no `react-router`; a
  `?video_job_id=...` query-param check is enough for two screens).
- **`api/scripts` fix is purely additive**: `series_name: str = ""` on `ScriptIn`,
  stored as submitted. Empty value behaves exactly as today (no series context) —
  `_fetch_series_context` (from `llm-metadata-generation`) already degrades to `[]`
  gracefully for that case, so no change needed on the metadata-harness side.

## Risks / Trade-offs

- [Risk] Number-normalization false positives are the one thing that must be right on
  the first pass — everything else below is a "watch for it, cheap fix later" risk,
  this one would make the correctness check actively harmful (alert fatigue →
  rubber-stamped approvals) if wrong. → Mitigation: reuse `expand_numbers()` exactly
  as designed above; verify explicitly against a real chapter:verse-containing script
  in tasks.md.
- [Risk] Whisper's own transcription errors are indistinguishable from genuine TTS
  content errors. → Mitigation: `large-v3` model choice, plus the review UI itself —
  a human can tell "Whisper mishearing" from context, which is exactly why this is a
  review step, not an automated pass/fail gate.
- [Risk] CUDA allocator behavior across repeated load/unload cycles in one long-lived
  `gpu-worker` process could creep VRAM usage over time. → Mitigation: same category
  as the already-accepted no-engine-cache inefficiency in `synthesize`; not solved
  pre-emptively, `torch.cuda.empty_cache()` per Activity is a cheap later fix if it
  ever manifests in practice.
- [Risk] First `transcribe` call downloads ~3GB (`large-v3`) from HF Hub. →
  Mitigation: reuses the already-mounted `${HOME}/.cache/huggingface` bind mount (same
  `HF_HOME` Chatterbox already uses) — one-time cost, not a tax on every restart.
- [Risk] Temporal payload size for very long transcripts' word-timestamp lists. →
  Mitigation: should be fine at typical devotional-episode lengths; sanity-checked
  against a real episode in tasks.md rather than assumed to scale indefinitely.

## Migration Plan

Purely additive — new workflow, new Activities, new `video_jobs` collection, new API
endpoints, new frontend screen, three new dependencies. The one existing-behavior
change is `api/scripts` accepting an additional optional field, which is
non-breaking for any caller omitting it. No changes to `AudioGenerationWorkflow`,
`synthesize`, `generate_metadata`, or any existing service's shape. Rollback: remove
the new endpoints/workflow/Activities; Phase 2 and `llm-metadata-generation` are
unaffected.
