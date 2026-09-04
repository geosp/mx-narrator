## 1. Feasibility research (before any implementation)

- [x] 1.1 Confirmed forced alignment is a real, distinct technique from ASR, with viable es/en/pt tooling (torchaudio MMS_FA, ctc-forced-aligner, aeneas)
- [x] 1.2 Found torchaudio's forced-alignment API is deprecated (removed in 2.9) — ruled out as the long-term foundation
- [x] 1.3 Found the underlying MMS alignment model is CC-BY-NC-4.0 — confirmed with the user the project is non-commercial before proceeding
- [x] 1.4 Ran a real proof-of-concept (`ctc-forced-aligner`, git-pinned) against real episode audio: ~13s for a 16-minute episode, clean alignment
- [x] 1.5 Ran the decisive test: three deliberate real-audio text corruptions (substitution, deletion, insertion) against the unmodified real audio
      - Substitution: detected (score -2.06 vs. -0.03 baseline)
      - Insertion: detected clearly (-9.25, with cascading corruption into neighboring words)
      - Deletion: **not detected at all** — aligner silently absorbed the missing word's audio into neighboring boundaries, zero score anomaly
- [x] 1.6 Concluded: forced alignment cannot replace `correctness_check` (dropped words are likely TTS's most common failure and are invisible to it); hybrid design adopted instead

## 2. Implementation

- [x] 2.1 New `worker/align.py`: `align_captions()` — best-effort, re-times SRT entries in place, never corrupts text or crashes the pipeline on failure
- [x] 2.2 `pyproject.toml`: added `ctc-forced-aligner`, git-pinned to the exact commit tested (not the PyPI release, which has an incompatible, unvalidated API)
- [x] 2.3 `uv lock` regenerated (was initially missed — caught during verification, see 3.5)
- [x] 2.4 `deploy/gpu-worker/Dockerfile`: added `build-essential` for the native-extension build
- [x] 2.5 `worker/types.py`: `AlignCaptionsInput`/`AlignCaptionsResult`; `ReviseCaptionsWorkflowInput` gained `lang`
- [x] 2.6 `worker/activities.py`: new `align_captions` Activity
- [x] 2.7 `worker/main.py`: registered `align_captions` on `gpu-tasks`
- [x] 2.8 `worker/workflows.py`: new retry policy/timeout constants; `align_captions` called after `finalize_srt` in both `VideoProductionWorkflow` and `ReviseCaptionsWorkflow`
- [x] 2.9 `api/main.py`: `/video_jobs/{id}/srt/revise` passes `render_job["lang"]`

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Rebuilt `gpu-worker`, confirmed no workflow was mid-activity, redeployed
- [x] 3.2 Caught a real bug: container startup was re-fetching/rebuilding the git dependency over the network every start (stale `uv.lock`) — fixed with `uv lock`, rebuilt, redeployed, confirmed clean/fast startup with no runtime network dependency
- [x] 3.3 Ran a real episode through `VideoProductionWorkflow` end-to-end to `ready_for_manual_upload`: confirmed `align_captions` ran (SRT timestamps measurably tightened, e.g. `00:00:00,000→00:00:01,460` became `00:00:00,160→00:00:01,420`), no errors, no word-count-mismatch warnings
- [x] 3.4 Triggered `ReviseCaptionsWorkflow` with a real caption text edit: initially failed with `TypeError: ReviseCaptionsWorkflowInput.__init__() missing 1 required positional argument: 'lang'` — root cause: `api`/`cpu-worker` reuse the `gpu-worker` image but hadn't been redeployed. Redeployed all three, terminated the stuck failed workflow execution, retried — confirmed both the text edit and its re-alignment applied correctly
- [x] 3.5 Cleaned up the throwaway `video_job`, its media, and scratch files
