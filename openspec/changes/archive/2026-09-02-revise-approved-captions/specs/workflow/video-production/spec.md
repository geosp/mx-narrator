## ADDED Requirements

### Requirement: Approved captions can be revised, with the video re-rendered to match
Once captions have been approved at least once (the episode has reached
`metadata_review_pending`, `ready_for_manual_upload`, or `failed`), the system
SHALL allow submitting corrected caption text and SHALL re-render the video
against the correction. The system SHALL NOT re-run transcription or the
correctness check when revising — the human-submitted text is authoritative.
When metadata was already approved, the system SHALL NOT regenerate it; when it
was not yet approved, the system SHALL generate and require review of it again.

#### Scenario: Revising after full completion
- **WHEN** a video job at `ready_for_manual_upload` has its captions revised
- **THEN** the video is re-rendered with the corrected captions burned in, and
  the episode returns to `ready_for_manual_upload` without regenerating
  metadata

#### Scenario: Revising before metadata was ever approved
- **WHEN** a video job at `metadata_review_pending` (metadata not yet approved)
  has its captions revised
- **THEN** the video is re-rendered, metadata is generated again, and the
  episode returns to `metadata_review_pending` for review

#### Scenario: Revising doubles as a retry after a failure
- **WHEN** a video job at `failed` has its captions resubmitted (corrected or
  unchanged)
- **THEN** rendering is attempted again from that submission

#### Scenario: A stale manual-upload record is cleared on revision
- **WHEN** a video job that had already been marked manually uploaded has its
  captions revised
- **THEN** the manually-uploaded record is cleared, since the previously
  uploaded file no longer matches the corrected video

#### Scenario: Approval signals reach whichever execution is currently active
- **WHEN** a human approves metadata for a video job whose captions were
  revised (a new workflow execution, distinct from the one that ran
  originally)
- **THEN** the approval reaches that current execution, not the original one
