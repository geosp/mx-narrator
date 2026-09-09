# workflow/metadata-generation Specification

## Purpose
The YouTube metadata step: given a render job's script, its own already-decided
episode title, and its series' prior approved episode titles, produces a
schema-valid subtitle/description/tags via a configurable local-or-remote LLM
provider (RFC §7.2), as a single deterministic call — no agent framework, no tool
use — then composes the final title from the fixed episode title and the LLM's
subtitle.

## Requirements

### Requirement: The episode's main title is fixed, not LLM-generated
The system SHALL use the episode's own already-decided title (`unit_id`, chosen
when the script was created) as the fixed main component of the final title, and
SHALL NOT ask the LLM to generate or replace it.

#### Scenario: Final title always starts with the episode's own title
- **WHEN** metadata generation runs for a render job
- **THEN** the returned title begins with that render job's episode title exactly
  as given, unmodified

### Requirement: The LLM contributes only a complementary subtitle
The system SHALL generate, via the configured LLM provider, a short subtitle that
adds specificity about the episode without repeating the fixed title's wording,
and SHALL compose the final title as the fixed title followed by a separator
followed by that subtitle.

#### Scenario: Successful generation
- **WHEN** metadata generation runs for a `render_job_id` with valid script text
- **THEN** it returns a result containing a title composed of the episode's fixed
  title, a separator, and an LLM-generated subtitle; a description; and a list of
  tags, each validated against the schema's length constraints (matching
  YouTube's own description/tag limits)

#### Scenario: The composed title never exceeds YouTube's title limit
- **WHEN** the fixed title, separator, and generated subtitle together would
  exceed YouTube's 100-character title limit
- **THEN** the subtitle is shortened to fit within that limit and the fixed
  title is never truncated

#### Scenario: The fixed title alone is at or beyond the limit
- **WHEN** the episode's fixed title alone is at or exceeds YouTube's
  100-character title limit
- **THEN** the final title is the fixed title truncated to that limit, with no
  subtitle appended

### Requirement: LLM provider and target machine are configurable, not hardcoded
The system SHALL select the LLM provider and the machine serving it from
configuration, not from a hardcoded provider, so the same code path works against a
local-network model or a remote API without modification.

#### Scenario: Switching from a local model to a different provider
- **WHEN** the configured LLM model and target machine are changed (e.g. from an
  Ollama-served model on one LAN machine to a vLLM-served model on another, or to a
  remote API)
- **THEN** metadata generation succeeds against the newly configured provider with no
  code change, using the same request/response contract

#### Scenario: No configuration selects a third-party provider by default
- **WHEN** no explicit remote-provider configuration is set
- **THEN** metadata generation targets a local-network LLM endpoint, not a third-party
  API

### Requirement: Prior series titles inform generation, restricted to approved ones
The system SHALL include previously human-approved episode titles from the same
series as context when generating a new episode's metadata, and SHALL exclude
unapproved or draft titles from that context.

#### Scenario: Series with prior approved episodes
- **WHEN** a render job's script belongs to a series that has previously
  human-approved episode titles
- **THEN** those titles are included as context for the new generation request

#### Scenario: Draft titles are excluded
- **WHEN** a series has prior episode titles that were generated but never
  human-approved
- **THEN** those draft titles are excluded from the context used for a new generation
  request

### Requirement: A failed generation attempt is retried with real recovery time, not silently accepted
The system SHALL retry a metadata-generation request a bounded number of times,
with increasing delay between attempts, when it fails — whether from a
schema-validation failure or a transient provider error (e.g. a connection
failure or a provider-side crash) — and SHALL surface failure after that bound
is reached rather than retrying indefinitely or returning invalid data. The
bound and delay SHALL be long enough to plausibly outlast a real transient
provider outage, not just a near-instant retry.

#### Scenario: Transient failure recovers within the retry window
- **WHEN** a metadata-generation attempt fails (schema validation or a
  provider-side error) but a later attempt within the retry bound succeeds
- **THEN** metadata generation returns the successful attempt's validated result

#### Scenario: Persistent failure surfaces as an error
- **WHEN** every attempt up to the bounded retry limit fails
- **THEN** metadata generation fails with an error rather than retrying
  indefinitely or returning invalid data, and the failure is recorded (not left
  as a silently stuck in-progress state)

### Requirement: Metadata can be regenerated independent of the originating workflow
The system SHALL support re-running metadata generation for a video job whose
originating workflow has already completed, without requiring the workflow to
still be running, and SHALL NOT persist the regenerated result until a human
explicitly saves it.

#### Scenario: Regenerating after the workflow has finished
- **WHEN** a human requests regeneration for a video job that has already
  reached its terminal ready-for-upload state
- **THEN** the system produces a fresh title/description/tags result without
  requiring a live workflow execution

#### Scenario: Regeneration does not overwrite approved metadata by itself
- **WHEN** a human requests regeneration but does not explicitly save the result
- **THEN** the video job's previously approved metadata remains unchanged
