## 1. Render progress and playback URL

- [x] 1.1 Add an optional `progress_callback` parameter to
      `src/narrator/batch.py::render_job()` (a function parameter, not a `RenderJob`
      field, since `RenderJob` instances are pickled through `multiprocessing.Queue`
      in `run_batch()`/`_worker()`), called after each chunk finishes synthesizing —
      verified a multi-chunk script invokes the callback once per chunk with
      correctly incrementing `(current, total)`, and that omitting the callback is
      unchanged from before (no regression to the CLI/`run_batch()` path)
- [x] 1.2 Wire `worker/activities.py::synthesize` to pass a closure writing
      `render_jobs.progress` to Mongo on each callback invocation — verified live:
      submitted a real multi-sentence script through the running stack and watched
      `render_jobs.progress` update incrementally in Mongo while synthesis was
      actually running, then confirmed via a real Playwright session that "Chunk X
      of Y" visibly incremented through all 9 chunks of a real render and stopped
      once `status` became `"complete"`
- [x] 1.3 Compute and store `render_jobs.audio_url` in `mark_render_job` when status
      becomes `"complete"` — verified the field appears on completion and flows
      automatically into `GET /render_jobs/{id}/events`'s SSE stream (no field
      allowlist to update) and into the dashboard listing (task 2.1) without either
      endpoint recomputing it; added a fallback computation in both call sites for
      render_jobs docs written before this field existed, confirmed against real
      pre-existing documents in Mongo

## 2. Dashboard listing

- [x] 2.1 Implement `GET /dashboard` in `api/main.py`: iterate `scripts.find()`,
      look up each script's latest `render_jobs` doc and that render job's latest
      `video_jobs` doc (plain per-script lookups, matching the existing
      `_fetch_series_context` pattern rather than an aggregation pipeline) — verified
      against real, pre-existing Mongo data: correct joins, correct `audio_url`
      fallback for older render_jobs docs, correct `progress` while a real render was
      still in-flight
- [x] 2.2 Build `web/src/Dashboard.jsx` as the default landing page (no query
      params): groups episodes by `series_name` with an explicit "No series" bucket,
      shows render/video status badges and inline `<audio controls>` playback —
      verified via real Playwright sessions: episodes grouped correctly by series,
      inline audio actually fetches and plays (`200`, `audio/mpeg`), a real in-flight
      render's chunk progress appeared and updated on the dashboard row itself

## 3. Script deletion

- [x] 3.1 Implement `_delete_render_jobs_for_script()` and `_terminate_workflow()`
      helpers and `DELETE /scripts/{id}` in `api/main.py` (terminate any in-flight
      `audio-gen-*`/`video-prod-*` workflow, best-effort; remove each job's media
      directory; delete the `video_jobs`/`render_jobs`/`scripts` documents) —
      verified against real data: deleting a script with a completed render+video
      job removed both Mongo docs and both media directories; deleting a
      non-existent script id returned 404 with no side effects; re-deleting an
      already-deleted script also 404s
- [x] 3.2 Add a confirm-gated "Delete" control to each `web/src/Dashboard.jsx`
      episode row — verified via Playwright: the browser `confirm()` dialog's
      message names the episode; accepting removes the row and the deletion
      persists after a real page reload (not just local state); dismissing leaves
      the episode untouched

## 4. Series listing and selection

- [x] 4.1 Implement `GET /series` in `api/main.py` as `scripts.distinct
      ("series_name")`, excluding the empty string — deliberately not a stored
      entity (design.md); verified a series disappears from the response the moment
      the last script referencing it is deleted, with no separate cleanup step, and
      persists as long as at least one other script still references it
- [x] 4.2 Add a series dropdown to the shared `web/src/ScriptForm.jsx` (existing
      series fetched from `GET /series`, or "+ New series…" revealing a name field)
      used by both the upload form and the edit form — verified via Playwright:
      creating a script under a new series makes it appear as an existing option on
      the next upload; picking an existing series hides the new-name field;
      dashboard and upload-form series lists both reflect a deletion immediately

## 5. Script detail and edit/regenerate

- [x] 5.1 Implement `GET /scripts/{id}` in `api/main.py`, pulling ID3/render
      parameters from the script's latest render job (scripts themselves don't
      store them) plus a `has_video_job` flag — verified the response round-trips
      correctly for a real script and correctly reflects `has_video_job` both before
      and after a video job is attached
- [x] 5.2 Implement `_start_render()` (factored out of `create_script`, shared with
      regenerate) and `PUT /scripts/{id}/regenerate` — updates the script doc, calls
      the task-3.1 cascade to discard the existing render/video work, then starts a
      fresh render — verified three real scenarios end to end: (a) editing a script
      with no video job yet — old render/media removed, new render created and
      completes; (b) editing a script whose render has an associated video job — old
      render, video job, and both media directories all removed, new render starts
      clean; (c) editing a script while its render is still mid-flight — the running
      workflow terminated cleanly (no crash, no orphaned progress writes), old
      render removed, new one starts
- [x] 5.3 Build `web/src/EditScript.jsx` (pre-filled via task 5.1, reusing
      `ScriptForm.jsx`), showing a persistent warning banner and a `confirm()` gate
      specifically when `has_video_job` is true — verified via Playwright: no dialog
      fires when there's no video job; the dialog's message and the banner text both
      appear when one exists; dismissing the dialog leaves the script unregenerated;
      accepting it regenerates and the old video job is confirmed gone server-side
      afterward
- [x] 5.4 Add "Edit & regenerate" / "Edit script & regenerate" links from
      `Dashboard.jsx` and `RenderJob.jsx` to `EditScript.jsx`, styled consistently
      with the rest of the UI (`styles.link` — no default browser underline/purple) —
      verified visually via a real screenshot after a user-reported style bug, and
      confirmed via Playwright `getComputedStyle` that both the render-detail page's
      and the dashboard's edit links share the same non-underlined, dark-gray style

## 6. Navigation and state persistence

- [x] 6.1 Extract `web/src/RenderJob.jsx` from the old inline `StatusView`/
      `StartVideoProduction` in `App.jsx`, keyed by `?render_job_id=...` in the URL
      instead of React state; `App.jsx`'s submit handler navigates there via
      `window.location.href` instead of `setState` — verified via Playwright: after
      submitting a script, reloading the page at the resulting URL still shows live
      render status instead of resetting to a blank form
- [x] 6.2 Wire `web/src/main.jsx`'s query-param router (`video_job_id` >
      `render_job_id` > `edit_script_id` > `view=upload` > default `Dashboard`) and
      add "← Dashboard" breadcrumbs to every drill-in screen — verified round-trip
      navigation from Dashboard into each screen and back via Playwright, zero
      browser console errors across all sessions

## 7. Documentation

- [x] 7.1 This proposal/design/spec-delta set itself, written and archived after the
      fact to bring `openspec/specs` back in sync with the already-implemented,
      already-verified behavior above (see proposal.md's Why)
