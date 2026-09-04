## 1. Fix

- [x] 1.1 Added `scale=trunc(iw/2)*2:trunc(ih/2)*2` as the first filter in `render_video()`'s `-vf` chain, before `subtitles=...`

## 2. Verification (real infrastructure, no mocking)

- [x] 2.1 Reproduced the exact failure: ran the unfixed command against a real 1671x941 test image inside `cpu-worker`, confirmed the same `width not divisible by 2` error
- [x] 2.2 Applied the fix, re-ran against the same test image: exit 0, `ffprobe` confirmed 1670x940 output (both even)
- [x] 2.3 Confirmed no workflow was mid-activity via `temporal workflow describe`, rebuilt the shared image, redeployed `api`/`gpu-worker`/`cpu-worker` together
- [x] 2.4 Did not act on the user's real video job directly; user retried via "Revise captions" and confirmed success independently
