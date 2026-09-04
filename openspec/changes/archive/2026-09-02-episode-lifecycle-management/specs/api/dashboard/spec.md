## Purpose

Cross-collection read endpoints that let the UI show what the database currently
holds — every script's render/video status and every series in use — without the
client already knowing a specific job id.

## ADDED Requirements

### Requirement: Every script's current status is listable in one request
The system SHALL provide an endpoint that returns every script joined with its most
recent render job's status and its most recent video job's status, if any.

#### Scenario: Script with a completed render and no video job
- **WHEN** a client requests the dashboard listing
- **THEN** the script appears with its render job's status and playback URL, and no
  video job entry

#### Scenario: Script with an in-progress render
- **WHEN** a client requests the dashboard listing while a script's render job is
  still `"rendering"`
- **THEN** the script's entry includes the render job's current chunk progress

#### Scenario: Script with multiple video jobs
- **WHEN** a client requests the dashboard listing for a script whose render job has
  had more than one video job created against it
- **THEN** only the most recently created video job appears in the listing

### Requirement: Series in use are listable
The system SHALL provide an endpoint that returns the distinct, non-empty series
names currently referenced by any script.

#### Scenario: Series with at least one script
- **WHEN** a client requests the series listing
- **THEN** every series name referenced by at least one script appears exactly once

#### Scenario: No stored series entity
- **WHEN** every script referencing a given series name is deleted or edited to a
  different series name
- **THEN** that series name no longer appears in the series listing, with no
  separate deletion step required
