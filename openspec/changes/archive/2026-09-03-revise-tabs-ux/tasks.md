## 1. Implementation

- [x] 1.1 Extracted `ImageReviseForm` from `ReviseImageToggle`'s guts
- [x] 1.2 New `ReviseTabs` component: two-tab switcher, "Captions" default, "Background image" second
- [x] 1.3 Replaced both `ReviseCaptionsToggle`+`ReviseImageToggle` usage sites (`ReadyForUpload`, `failed` block) with `ReviseTabs`
- [x] 1.4 Removed now-unused `ReviseCaptionsToggle`/`ReviseImageToggle`

## 2. Verification (real infrastructure, no mocking)

- [x] 2.1 Built and linted clean
- [x] 2.2 Pushed a throwaway test video_job to `ready_for_manual_upload`
- [x] 2.3 Playwright screenshot: "Captions" tab active by default, video/metadata visible above, no collapsed content
- [x] 2.4 Playwright screenshot: clicked "Background image" tab, confirmed clean switch
- [x] 2.5 Cleaned up the throwaway video_job, media, and scratch files
