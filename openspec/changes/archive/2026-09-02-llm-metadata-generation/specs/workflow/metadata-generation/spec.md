## Purpose

The LLM-generated YouTube metadata step: given a render job's script and its series'
prior approved episode titles, produces schema-valid title/description/tags via a
configurable local-or-remote LLM provider (RFC §7.2), as a single deterministic call —
no agent framework, no tool use.

## ADDED Requirements

### Requirement: Metadata generation produces structured, schema-valid output
The system SHALL produce a title, description, and tags for a render job's episode by
calling a configured LLM provider and validating its response against a fixed schema
before returning it.

#### Scenario: Successful generation
- **WHEN** metadata generation runs for a `render_job_id` with valid script text
- **THEN** it returns a result containing a title, a description, and a list of tags,
  each validated against the schema's length constraints (matching YouTube's own
  title/description/tag limits)

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

### Requirement: A malformed LLM response is retried, not silently accepted
The system SHALL retry a metadata-generation request a bounded number of times when
the LLM's response fails schema validation, and SHALL surface failure after that bound
is reached rather than retrying indefinitely or returning invalid data.

#### Scenario: Transient schema-validation failure recovers
- **WHEN** an LLM response fails schema validation on a first attempt but a retry
  succeeds
- **THEN** metadata generation returns the successful retry's validated result

#### Scenario: Persistent schema-validation failure surfaces as an error
- **WHEN** an LLM response fails schema validation on every attempt up to the bounded
  retry limit
- **THEN** metadata generation fails with an error rather than retrying indefinitely
  or returning unvalidated data
