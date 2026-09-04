# api/voices Specification

## Purpose
Upload, list, and delete named Chatterbox voice-cloning samples, so an episode's
narration can use a specific reference voice instead of only the engine's built-in
default.

## Requirements

### Requirement: A named voice can be created from an uploaded sample
The system SHALL allow creating a named voice by uploading one WAV sample tagged
with a language (or a language-independent fallback).

#### Scenario: Create a voice with a language-specific sample
- **WHEN** a client creates a voice with a name and a WAV file tagged `"es"`
- **THEN** a voice is created and listing it shows `"es"` among its available
  languages

#### Scenario: Reject a non-WAV upload
- **WHEN** a client attempts to create a voice with a file that isn't a `.wav`
- **THEN** the request is rejected and no voice is created

### Requirement: Additional samples can be added to an existing voice
The system SHALL allow adding or replacing one language's sample on an existing
voice without affecting its other samples.

#### Scenario: Add a second language to an existing voice
- **WHEN** a client adds an `"en"` sample to a voice that already has an `"es"`
  sample
- **THEN** the voice's available languages include both, and the `"es"` sample is
  unchanged

### Requirement: Voices are listable
The system SHALL provide an endpoint that lists every voice with its name and
available languages.

#### Scenario: List after creation
- **WHEN** a client requests the voice listing after creating one or more voices
- **THEN** each appears with its name and the languages it has samples for

### Requirement: A single sample can be removed without deleting the whole voice
The system SHALL allow removing one language's sample from a voice, but SHALL
reject removing a voice's only remaining sample.

#### Scenario: Remove one of several samples
- **WHEN** a client removes the `"en"` sample from a voice that also has an `"es"`
  sample
- **THEN** the voice still exists with only `"es"` remaining

#### Scenario: Reject removing the last sample
- **WHEN** a client attempts to remove a voice's only remaining sample
- **THEN** the request is rejected and the sample is not removed

### Requirement: A voice can be deleted entirely
The system SHALL allow deleting a voice, removing its record and all of its sample
files, without affecting any render job that previously used it.

#### Scenario: Delete a voice
- **WHEN** a client deletes a voice
- **THEN** it no longer appears in the voice listing and its sample files are gone
