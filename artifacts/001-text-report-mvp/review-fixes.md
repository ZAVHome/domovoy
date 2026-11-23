# Review fixes: Text report MVP

## Result

All six findings in `review.md` have been addressed in the implementation.

## Changes made

1. **Report pagination:** resident and responder/admin lists now fetch pages of ten reports with older/newer navigation. Report detail actions re-check ownership or assigned-house access. Administrator pagination queries all stored houses.
2. **Telegram message limits:** long summaries, details, and responder notifications are split into messages of at most 3,500 UTF-16 code units. Confirmation and status buttons stay on short control messages. Confirmation/status edits catch Telegram bad-request errors, including unchanged-message responses.
3. **Atomic status transitions:** status updates compare the expected old status inside the same SQLite transaction that updates the report and appends history. Stale actions receive a conflict message and cannot overwrite a newer status.
4. **Atomic, idempotent report creation:** report data, dynamic fields, initial history, and the profile-prompt marker commit together. Each wizard receives a UUID submission token backed by a unique SQLite index, so retrying a confirmation returns the already-created report instead of inserting a duplicate.
5. **Status keyboard retention:** after a status change, the short control message is updated with the next keyboard. Responders retain the next step; administrators retain the remaining status choices. Closed responder reports have no further transition button.
6. **Status configuration validation:** startup now rejects missing, empty, or non-string titles and invalid `initial` marker types. Tests cover the invalid title cases.

## Verification

- `PYTHONPATH=src python -m unittest discover -s tests -v` — 12 tests passed; 2 handler-control tests were skipped because aiogram is not installed in this environment.
- `python -m compileall src tests` — passed.
- `git diff --check` — passed.
- Tests cover 21-report pagination for residents, administrators, and assigned responders; UTF-16 message boundaries; stale status updates; report idempotency and rollback; and invalid status titles.

## Remaining verification

The aiogram handler-control test is present but could not run in this environment, and no real Telegram run was performed. Install project dependencies and use valid Telegram credentials to verify callback navigation, inline keyboards, and actual message delivery before deployment.
