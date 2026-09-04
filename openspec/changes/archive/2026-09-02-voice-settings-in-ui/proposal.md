## Why

`ScriptIn`/`SynthesizeInput`/`RenderJob` have always accepted `speed`,
`exaggeration` (narrator CLI's `--expressiveness`), and `cfg_weight`
(`--cfg-weight`) — the same three tuning parameters the CLI exposes
(`src/narrator/cli.py`) — but `ScriptForm.jsx` never rendered inputs for them.
Every episode rendered through the UI silently used the hardcoded defaults
(`speed=0.95, exaggeration=0.3, cfg_weight=0.5`), with no way to match the
settings the user actually uses via the CLI for real narrations (per the
example command they gave: `--cfg-weight 0.4 --expressiveness 0.6 --speed
0.95`).

## What Changes

- `ScriptForm.jsx` gains a "Voice settings" section with Speed, Expressiveness,
  and CFG Weight number inputs, with hint text drawn from the CLI's own
  `--help` strings.
- `initialForm`'s defaults changed to match the user's actual CLI usage:
  `cfg_weight: 0.4`, `exaggeration: 0.6` (`speed` was already `0.95`,
  unchanged).
- No backend change — these fields already flowed end-to-end
  (`ScriptIn` → `AudioGenerationWorkflowInput` → `SynthesizeInput` →
  `RenderJob`); only the form UI was missing.

## Capabilities

No capability changes — pure frontend UX, exposing existing, already-specified
API fields that were simply never rendered as form inputs. `skip_specs: true`.

## Impact

- `web/src/ScriptForm.jsx` only. Both `App.jsx` (new script) and
  `EditScript.jsx` (edit existing) get the new fields automatically, since both
  already share this component.
