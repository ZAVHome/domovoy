# Text report MVP

## Goal

Deliver a usable first version of Domovoy's text-report workflow from a configured building group through resident follow-up and responder status handling.

## Scope and stages

1. Validate house, classification, status, and responder JSON at startup. Add a versioned SQLite schema change that preserves existing data and a repository layer for report operations.
2. Guide residents through optional section, floor, and apartment details; configured locations, categories, and text fields; cancellation; and a final confirmation before saving.
3. Let residents list their own reports and view report details and status history, with access limited by Telegram user ID.
4. Notify responders assigned to a house, let them process only that house's reports through `new → in_progress → resolved → closed`, let the administrator process any house and choose any status, and notify residents of status changes.
5. Update English and Russian project documentation and add standard-library checks for persistence, access rules, configuration, and migration behavior.

## Acceptance criteria

- A confirmed report and its initial status history are stored in SQLite; cancelled drafts are not stored.
- Residents can only retrieve their own reports. Responders can only retrieve reports for assigned houses. The administrator can retrieve reports across all houses.
- Optional profile and report fields can be skipped; required report fields cannot.
- Status changes update the report and append history. Notification failures do not roll back saved report data or status changes.
- Startup rejects invalid or cross-referenced configuration errors clearly, and migration preserves existing user data.
- Automated checks pass. A real Telegram run is additionally required before deployment.

## Excluded from this plan

Photo and video intake, in-bot configuration or assignment management, and persistence of unfinished conversations across process restarts.
