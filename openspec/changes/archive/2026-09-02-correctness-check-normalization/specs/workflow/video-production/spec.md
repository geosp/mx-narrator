## MODIFIED Requirements

### Requirement: Transcript is checked against the script's known text
The system SHALL compare the transcript against the exact text narrator's synthesis
pipeline was given for that script, and record whether they match or where they
diverge.

#### Scenario: Transcript matches the known text
- **WHEN** the transcript's content matches the script's known text after
  transcription
- **THEN** `video_jobs.correctness_check.status` is `"pass"` and no mismatches are
  recorded

#### Scenario: Transcript diverges from the known text
- **WHEN** the transcript is missing or alters words present in the script's known
  text
- **THEN** `video_jobs.correctness_check.status` is `"mismatch"`, and each divergence
  is recorded with the expected text, the actual (transcribed) text, and an
  approximate timestamp

#### Scenario: Correctly narrated numbers are not falsely flagged
- **WHEN** the script's known text contains a number or scripture chapter:verse
  reference that was narrated and transcribed correctly
- **THEN** the correctness check does not report it as a mismatch, regardless of
  whether the number is written as digits or spelled out on either side of the
  comparison

#### Scenario: Accent-mark differences are not falsely flagged
- **WHEN** a word appears with an accent mark on one side of the comparison and
  without it (or with a different accent) on the other, but is otherwise the same
  word
- **THEN** the correctness check does not report it as a mismatch

#### Scenario: Known one-word/two-word Spanish spelling variants are not falsely flagged
- **WHEN** a Spanish word with two RAE-recognized spellings (one word or two, e.g.
  "adonde"/"a donde") is narrated correctly but rendered differently between the
  script and the transcript
- **THEN** the correctness check does not report it as a mismatch
