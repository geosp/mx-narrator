## ADDED Requirements

### Requirement: A selected voice is resolved and applied during synthesis
When a render job specifies a voice, the workflow SHALL resolve that voice's
reference sample for the render job's language (falling back to the voice's
language-independent sample if no language-specific one exists) and use it for
synthesis, without requiring any change to narrator's own synthesis pipeline.

#### Scenario: Language-specific sample available
- **WHEN** a render job specifies a voice that has a sample for the render job's
  language
- **THEN** synthesis uses that language-specific sample

#### Scenario: Falls back to the voice's default sample
- **WHEN** a render job specifies a voice that has no sample for the render job's
  language but does have a language-independent fallback sample
- **THEN** synthesis uses the fallback sample

#### Scenario: No voice specified
- **WHEN** a render job specifies no voice
- **THEN** synthesis uses the engine's built-in default voice, unchanged from
  behavior before voice selection existed
