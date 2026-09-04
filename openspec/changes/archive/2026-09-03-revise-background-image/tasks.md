## 1. Backend

- [x] 1.1 New `POST /video_jobs/{video_job_id}/image/revise` endpoint, mirroring `revise_srt`'s revisability check and workflow-termination/restart pattern
- [x] 1.2 Reuses `ReviseCaptionsWorkflow` (current SRT text unchanged, new `image_path`) instead of a new workflow

## 2. Frontend

- [x] 2.1 New `ReviseImageToggle` component (file input + submit, collapsed by default)
- [x] 2.2 Wired into `MetadataReview`, `ReadyForUpload`, and the `failed` block, alongside `ReviseCaptionsToggle`

## 3. Verification (real infrastructure, no mocking)

- [x] 3.1 Built a throwaway test video_job, pushed it to `metadata_review_pending`
- [x] 3.2 Called `/image/revise` with a new, deliberately odd-dimensioned image
- [x] 3.3 Confirmed the workflow re-rendered and returned to `metadata_review_pending` with the new `image_path` recorded, no errors
- [x] 3.4 Extracted a frame from the output video and visually confirmed it shows the new image's color (red), not the original (black)
- [x] 3.5 Confirmed output dimensions were correctly normalized to even (1670x940) on this path too
- [x] 3.6 Cleaned up the throwaway video_job, workflow, media, and scratch files
