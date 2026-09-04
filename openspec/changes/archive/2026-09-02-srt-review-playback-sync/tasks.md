## 1. SRT parse/serialize utility

- [x] 1.1 Add `web/src/srt.js` (`parseSrt`/`serializeSrt`) — verified a full
      round-trip against a real episode's actual 274-entry SRT file: parsed,
      re-serialized, re-parsed, zero content/timestamp mismatches across all
      entries
- [x] 1.2 Confirm the backend still accepts the reserialized output — fed it
      directly to the real `srt.parse()` the API uses for validation: parsed
      cleanly, same entry count, matching first/last entries

## 2. Synced review UI

- [x] 2.1 Rework `SrtReview` (`web/src/VideoReview.jsx`) into one row per
      caption (clickable timestamp + editable text), replacing the single raw
      SRT textarea — verified via Playwright against a real in-progress review
- [x] 2.2 Wire `<audio>` `timeupdate`/`seeked` to compute and highlight the
      active row, and scroll it into view only when the active entry changes —
      verified during real playback: all three real captions in a test episode
      highlighted in sequence as audio actually played
- [x] 2.3 Wire each row's timestamp to seek playback there on click — verified
      clicking any row (first/middle/last) both seeks the audio to the right
      time and highlights exactly that row
- [x] 2.4 **Real bug found and fixed**: `timeupdate` doesn't reliably fire after
      a programmatic seek while the audio is paused (browser-dependent) —
      clicking a timestamp seeked correctly but the highlight didn't move. Fixed
      by also listening for the `seeked` event
- [x] 2.5 **Second real bug found and fixed**: after the above fix, seeking to
      the *last* caption's own start time still failed to highlight it —
      browser seek precision landed `currentTime` a hair below the exact
      requested value, failing a strict `t >= e.start` comparison. Fixed with a
      small (50ms) epsilon tolerance on both bounds
- [x] 2.6 Verified the full edit flow end-to-end for real: edited one caption's
      text through the new per-row UI, approved, and confirmed via
      `GET /video_jobs/{id}/srt` that the edit landed exactly as typed with all
      surrounding entries' timestamps unchanged

## 3. Documentation

- [x] 3.1 Proposal written and archived with `skip_specs: true` — a pure
      frontend UX change with no system-level contract change, not forcing a
      UI-interaction requirement into specs that don't otherwise describe that
      level of detail.
