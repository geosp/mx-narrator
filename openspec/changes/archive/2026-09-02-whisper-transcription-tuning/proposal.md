## Why

User reported many transcription errors and asked whether a Spanish-specific
Whisper model, or a missing `language` flag, was the cause. Neither was:
`transcribe_audio()` already passed `language=lang` (e.g. `"es"`) explicitly
per episode, not auto-detect, and there is no official Spanish-only Whisper
checkpoint — `large-v3` (already in use) is already near state-of-the-art for
Spanish. What the call was missing was any accuracy tuning beyond
`language`/`word_timestamps`.

## What Changes

- `worker/transcription.py`: added `vad_filter=True` to the `.transcribe()`
  call. Verified on real audio (an already-produced Spanish episode) that
  this reduces `correctness_check` mismatches (33 → 31 on the same audio) and
  fixes at least one confirmed real transcription error ("Tomás quería
  **saber cómo llegar**" — matching the actual script — vs. the prior
  baseline's hallucinated "Tomás quería **conocer a Jesús**").
- Two other candidate tunings were tried and explicitly rejected after real
  verification showed they made transcription *worse*, not better:
  - `compute_type="float16"` (up from the default `int8_float16`): caused a
    reproducible hallucinated sentence ("Jesús le anuncia que antes de ir a
    la iglesia, Jesús estaba en la iglesia...", not present in the script or
    audio) and a duplicated clause, confirmed via an isolated single-variable
    test to be caused by this setting specifically, not run-to-run noise.
  - `condition_on_previous_text=False`: caused word/clause duplication
    ("Pedro lo **lo** habrá negado", "**31 31** pronuncia", "La forma de
    **de** este discurso") and progressive loss of capitalization/
    punctuation partway through longer audio files.
  - Both are left at faster-whisper's defaults (`int8_float16`,
    `condition_on_previous_text=True`).
- `initial_prompt` was considered and deliberately excluded: priming Whisper
  with the episode's own script text would bias it toward "hearing" words
  that TTS may have actually dropped or mispronounced, undermining
  `correctness_check`'s entire purpose (independently verifying what TTS
  actually said). Not pursued in this change.

## Capabilities

No capability changes — internal accuracy tuning to an existing activity's
implementation detail, no observable API/UI/data-model contract change.
`skip_specs: true`.

## Impact

- `worker/transcription.py` only.
- Verified via direct, isolated real-audio testing (old vs. new settings,
  each candidate tuning tested individually against the same real episode
  audio) run inside the `gpu-worker` container using the actual
  `WhisperModel`/`faster-whisper` stack — no mocking.
- Verified through the real Temporal pipeline: created a fresh `video_job`
  for the same real, already-synthesized episode audio, ran it through the
  actual `transcribe` → `mark_video_job` → `correctness_check` activity chain
  on the redeployed `gpu-worker`, confirmed no errors and a lower mismatch
  count than the pre-change run on the same audio, then cleaned up the
  throwaway `video_job`/workflow/media.
