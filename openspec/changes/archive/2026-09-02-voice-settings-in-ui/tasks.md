## 1. Expose voice settings in the form

- [x] 1.1 Add Speed/Expressiveness/CFG Weight number inputs to
      `web/src/ScriptForm.jsx`'s "Voice settings" section, and update
      `initialForm`'s defaults to `cfg_weight: 0.4`, `exaggeration: 0.6`
      (matching the user's real CLI usage) — verified via Playwright: the
      upload form shows exactly `0.95` / `0.6` / `0.4` as defaults
- [x] 1.2 Confirmed custom values submitted through the real UI land correctly
      in the `render_jobs` document (`speed: 1.1, exaggeration: 0.7,
      cfg_weight: 0.35` after submitting those exact values) and that the
      episode rendered successfully with them
- [x] 1.3 Confirmed `EditScript.jsx` (sharing the same `ScriptForm`) correctly
      pre-fills an existing episode's actual stored voice settings, not just
      the defaults

## 2. Documentation

- [x] 2.1 Proposal archived with `skip_specs: true` — pure frontend change
      exposing already-specified API fields, no system-level contract change.
