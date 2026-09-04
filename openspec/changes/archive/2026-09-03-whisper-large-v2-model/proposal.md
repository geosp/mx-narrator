## Why

Continuing the transcription-accuracy investigation from
`whisper-transcription-tuning` and `bounded-retry-policies` — user asked
whether others report similar transcription issues; web research turned up a
widely-reported, specific finding: `large-v3` hallucinates more than
`large-v2` on real-world (non-benchmark) audio despite scoring better on
clean academic benchmarks (SYSTRAN/faster-whisper#777: "Large-v3 model
hallucinates, large-v2 doesn't"; independent write-ups report up to 4x more
hallucinations on real-world audio). `large-v2` had never been tried this
session.

## What Changes

- `worker/transcription.py`: `WHISPER_MODEL` default changed from
  `"large-v3"` to `"large-v2"` (still overridable via the existing env var).
  No other settings changed — `vad_filter=True`, `int8_float16`,
  `condition_on_previous_text` default all stay as already shipped.

## Verification

Real infrastructure, no mocking, same real episode audio used for every
prior experiment ("No se turbe tu corazón - Juan 14:1-31",
render_job `38f3ffd3-15e7-4942-97f8-f7e5a3a4c70d`):

- Isolated test inside `gpu-worker`: ran the actual
  `worker.transcription.transcribe_audio()` + `worker.diff.check_correctness()`
  functions (not a hand-rolled comparison) with `WHISPER_MODEL=large-v2`
  against the real script text. Result: 16 mismatches, vs. the 31-mismatch
  `large-v3` baseline from the prior change — a real, ~48% reduction.
  Manually reviewed the 16 remaining mismatches: all mundane ASR quirks
  (chapter/verse numbers spoken as words instead of digits, minor
  mishearings like "iscariote"/"escariote") — no hallucinations, no
  duplication, no corrupted quotes. The previously-fragile passages stayed
  correct ("Yo soy el camino, la verdad y la vida" intact; "Lo hizo Jacob...
  Lo hizo Moisés... lo hicieron Josué y David" anaphora transcribed
  correctly, unlike the rejected `no_repeat_ngram_size` experiment).
- Rebuilt and redeployed `gpu-worker` (cache hit on the expensive `uv sync`
  layer — only `worker/` changed) after confirming via `temporal workflow
  describe` that the one running workflow had zero pending activities.
- Ran the real Temporal pipeline end-to-end: created a fresh throwaway
  `video_job` against the same real audio, confirmed `transcribe` →
  `mark_video_job` → `correctness_check` completed without error — 9
  mismatches (even lower than the isolated test, consistent with faster-whisper
  run-to-run variance, still far below the 31-mismatch baseline).
- Cleaned up the throwaway `video_job`, its workflow execution, and media.

**Known trade-off**: `large-v2` transcription is slower — ~256s vs.
`large-v3`'s ~85-97s on this ~16-minute episode (roughly 2.7x). Accepted
because transcription runs asynchronously in the background (Temporal
activity with heartbeating, not blocking any interactive user action), and
the accuracy improvement substantially reduces manual SRT-review burden.

## Capabilities

No capability changes — internal accuracy tuning to an existing activity's
implementation detail, no observable API/UI/data-model contract change.
`skip_specs: true`.

## Impact

`worker/transcription.py` only (one-line default change plus a comment).
