## 1. Change

- [x] 1.1 Change `WHISPER_MODEL` default from `"large-v3"` to `"large-v2"` in `worker/transcription.py`

## 2. Verification (real infrastructure, no mocking)

- [x] 2.1 Ran the real `transcribe_audio()` + `check_correctness()` functions with `large-v2` against the same real episode audio and script text used throughout this session's transcription investigation
- [x] 2.2 Confirmed a ~48% drop in mismatches (31 → 16) vs. the `large-v3` baseline
- [x] 2.3 Manually reviewed all 16 remaining mismatches — confirmed all are mundane ASR quirks (numbers spoken as words, minor mishearings), not hallucinations/duplication/corruption
- [x] 2.4 Spot-checked previously-fragile passages (the "Yo soy el camino, la verdad y la vida" quote, the "Lo hizo Jacob... Lo hizo Moisés... lo hicieron Josué y David" anaphora) — both transcribed correctly
- [x] 2.5 Confirmed via `temporal workflow describe` that the one running workflow had zero pending activities before rebuild/redeploy
- [x] 2.6 Rebuilt and redeployed `gpu-worker`, confirmed clean startup
- [x] 2.7 Ran the real Temporal pipeline end-to-end on a fresh throwaway `video_job` against the same real audio — `transcribe` → `mark_video_job` → `correctness_check` completed without error, 9 mismatches (still far below the 31-mismatch baseline)
- [x] 2.8 Cleaned up the throwaway `video_job`, its Temporal workflow execution, and its media directory
- [x] 2.9 Noted the known speed trade-off (~256s vs. ~90s on this episode) as an accepted cost given transcription runs asynchronously in the background
