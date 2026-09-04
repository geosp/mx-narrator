## 1. Change

- [x] 1.1 Add `vad_filter=True` to the `model.transcribe(...)` call in `worker/transcription.py`
- [x] 1.2 Leave `compute_type` at its existing default (`int8_float16`) — `float16` tried and reverted (see 2.2)
- [x] 1.3 Leave `condition_on_previous_text` at faster-whisper's default (`True`) — `False` tried and reverted (see 2.3)
- [x] 1.4 Do not add `initial_prompt` — would risk biasing transcription toward the script text it's meant to independently verify against, undermining `correctness_check`

## 2. Verification (real infrastructure, no mocking, isolated single-variable tests)

- [x] 2.1 Baseline: transcribed a real, already-produced Spanish episode with the pre-change settings (`int8_float16`, no `vad_filter`, default `condition_on_previous_text`) inside the `gpu-worker` container
- [x] 2.2 Isolated `compute_type="float16"` alone: reproduced a hallucinated sentence not present in the script/audio and a duplicated clause — rejected
- [x] 2.3 Isolated `condition_on_previous_text=False` alone: reproduced word/clause duplication and progressive capitalization/punctuation loss — rejected
- [x] 2.4 Isolated `vad_filter=True` alone: clean output, no new artifacts; word-level diff against baseline confirmed a genuine accuracy improvement (correctly transcribed "saber cómo llegar" against the actual script, where the baseline hallucinated "conocer a Jesús")
- [x] 2.5 Confirmed `_normalize_text()` in `worker/diff.py` already lowercases and strips punctuation before comparing, so capitalization/punctuation differences seen in rejected candidates don't affect `correctness_check` — the word-duplication and hallucination were the disqualifying issues, not casing
- [x] 2.6 Rebuilt `gpu-worker` (cache hit on the expensive `uv sync` layer — only `worker/` changed) and redeployed, after confirming via `temporal workflow describe` that the one running workflow had zero pending activities (idle, waiting on a signal)
- [x] 2.7 Ran the real Temporal pipeline end-to-end through `transcribe` → `mark_video_job` → `correctness_check` on a fresh `video_job` against the same real episode audio; confirmed no errors and a lower mismatch count (31 vs. 33) than the pre-change run on identical audio
- [x] 2.8 Cleaned up the throwaway `video_job`, its Temporal workflow execution, and its media directory
