## 1. Normalization fix

- [x] 1.1 Add accent-mark folding to `_normalize_text()` in `worker/diff.py`
      (á/à/â/ä/ã→a, é/è/ê/ë→e, í/ì/î/ï→i, ó/ò/ô/ö/õ→o, ú/ù/û/ü→u, both cases;
      `ñ`/`ç` deliberately excluded — distinct letters, not accent marks) —
      verified by re-running `check_correctness` against a real episode's actual
      script text and actual transcribed captions (the episode that prompted this
      change): all accent-only mismatches (`qué`/`que`, `aún`/`aun`,
      `pódcast`/`podcast`) no longer appear
- [x] 1.2 Add `_merge_split_words()` (Spanish-only): collapses adjacent tokens
      matching a small, explicit set of RAE-recognized two-spelling words
      ("a donde"/"adonde", "por que"/"porque", "con que"/"conque", "si no"/"sino",
      "a parte"/"aparte") to one canonical form on both expected and actual token
      lists, keeping the actual side's timestamp list correctly aligned after
      merging — verified against the same real episode: all three "adonde"/
      "a donde" mismatches are gone
- [x] 1.3 Confirm the fix removes noise without hiding signal: re-ran against the
      same real episode end to end — mismatch count dropped from 24 to 17 (the
      exact false positives identified), while every other real mismatch (two
      dropped occurrences of "no se turbe su corazón", one large unaligned block,
      and plausible ASR mishearings like "iscariote"→"escariote", "hacer"→"ser",
      "los"→"nos", "arrastrarlo"→"gastarlo") is unchanged in content

## 2. Documentation

- [x] 2.1 This proposal and spec delta, written and archived alongside the fix —
      not left to drift, per the standing instruction this session.
