# Review: Text report MVP

## Verdict

**Changes requested.** The main persistence and access-control paths are present, and all existing automated checks pass. However, two high-priority issues can make reports unavailable through the normal bot interface, and four medium-priority issues affect status processing, save reliability, and configuration validation.

The review covered `plan.md`, `completion.md`, the implementation in `src/domovoy/`, configuration examples, and `tests/test_repository.py`. No implementation code was changed.

## Findings

### P1 — Reports beyond the latest 20 are unreachable through the bot interface

**Locations:** `src/domovoy/repository.py:90`, `src/domovoy/repository.py:109`, `src/domovoy/handlers.py:463`, `src/domovoy/handlers.py:500`

Both resident and responder queries apply `LIMIT 20`, while `/my_reports` and `/reports` render only that single page. There is no pagination, offset, filter, or command for selecting an older report. Consequently, a resident cannot open an older report through the interface, and a responder or administrator cannot process one. For an administrator, the limit applies globally across all houses, so activity in one house can hide reports from every other house.

A check with 21 persisted reports returned exactly 20 list entries; the oldest report was absent.

**Recommendation:** Add pagination or another navigation mechanism for both roles. Add a test with at least 21 reports that proves the oldest report remains reachable and actionable.

### P1 — Valid report content can exceed Telegram's message limit and block the workflow

**Locations:** `src/domovoy/handlers.py:368`, `src/domovoy/handlers.py:459`, `src/domovoy/handlers.py:496`, `src/domovoy/handlers.py:514`, `src/domovoy/handlers.py:556`

The confirmation summary and full report details are each sent as one message. Their size is not bounded, although they combine the description, arbitrary configured fields, address, and growing status history. Telegram text messages are limited to 4096 characters. A resident can submit a valid text field close to that limit, but the resulting summary or report details exceed it. Confirmation then fails before the report can be saved; later, an oversized report can also break resident/responder details and status-message editing.

A mocked check using a 4096-character description produced a 4170-character confirmation summary and a 4168-character report body even without history or additional fields.

**Recommendation:** Enforce field and aggregate length budgets, split long output safely, or paginate report details. Keep confirmation/status buttons attached to a valid short message and handle Telegram's message-not-modified and message-too-long errors explicitly. Add boundary tests at and above 4096 characters.

### P2 — Status validation and update are not atomic

**Locations:** `src/domovoy/handlers.py:538`, `src/domovoy/handlers.py:542`, `src/domovoy/handlers.py:550`, `src/domovoy/repository.py:143`

The handler reads and validates the current status, then issues a separate unconditional `UPDATE reports SET status_id=? ... WHERE id=?`. Concurrent actions can invalidate the checked transition between those operations. For example, a responder can validate `new → in_progress`, an administrator can then close the report, and the responder's delayed update can overwrite `closed` back to `in_progress`. The history retains both transitions, so it also exposes the inconsistent sequence.

A targeted stale-state check reproduced exactly this final state: a closed report became `in_progress` and had three history entries.

**Recommendation:** Pass the expected current status into the repository and perform a conditional update such as `WHERE id=? AND status_id=?`, inserting history in the same transaction. If no row is updated, re-read the report and report the conflict to the user. Add a concurrent/stale-transition test.

### P2 — A post-save profile error reports failure and enables duplicate reports

**Locations:** `src/domovoy/handlers.py:442`, `src/domovoy/handlers.py:448`, `src/domovoy/handlers.py:449`, `src/domovoy/repository.py:47`

`create_report()` commits in its own database context. `mark_profile_prompted()` then runs in a separate connection but shares the same broad exception handler. If the profile update fails after the report commit, the user receives "Не удалось сохранить заявку", the FSM remains at confirmation, and the saved report is not announced. Retrying confirmation inserts another report.

A mocked `sqlite3.OperationalError` in `mark_profile_prompted()` left one committed report, produced the failure response, and did not clear the state.

**Recommendation:** Save the report, initial history, and profile marker in one transaction, or treat post-commit profile failures separately and finish the successful report flow. An idempotency token for confirmation would provide additional protection against repeated callbacks. Test a failure at each persistence step.

### P2 — The status keyboard disappears after every status change

**Location:** `src/domovoy/handlers.py:554`

After a successful update, `edit_text()` is called without `reply_markup`. Telegram therefore removes the previous inline keyboard, while the code does not attach a keyboard for the updated status. A responder must run `/reports` again for every subsequent transition; an administrator likewise loses all remaining status choices.

The mocked handler check confirmed that `edit_text()` receives no `reply_markup` argument.

**Recommendation:** Pass `_report_keyboard(updated, configs, admin=admin, responder=not admin)` when editing the message. Add a handler test for the keyboard after each allowed transition and after `closed`.

### P2 — Status configuration validation omits fields required by rendering

**Locations:** `src/domovoy/config.py:111`, `src/domovoy/handlers.py:38`

Startup validates status IDs, order, and the initial marker, but does not require a non-empty string `title`. `_status_title()` accesses `item["title"]` directly. Thus a configuration can pass startup validation and later raise `KeyError` in `/my_reports`, `/reports`, report notifications, or status handling.

A configuration with the `new.title` property removed passed `load_validated_configs()` and then raised `KeyError('title')` during rendering.

**Recommendation:** Validate a non-empty title for every status at startup and validate the types of other consumed properties. Add invalid-configuration tests for missing, empty, and non-string titles.

## What was confirmed

- Confirmed reports, dynamic fields, and initial status history are persisted; the existing repository test passes.
- Resident ownership filters and responder house filters work in the tested repository paths; administrator queries can span houses.
- Required fields reject the skip action, while optional profile/report fields have skip paths.
- New-report notification errors are caught per responder, and resident status-notification errors are caught after the database update.
- The existing migration check preserves a legacy user record.

## Verification performed

- `PYTHONPATH=src python -m unittest discover -s tests -v` — **5 tests passed**.
- `python -m compileall src tests` — **passed**.
- `git diff --check` — **passed**.
- Handler imports with `aiogram 3.32.0` — **passed**.
- Temporary SQLite/mocked-handler checks reproduced all six findings above.

The five existing tests cover repository and configuration behavior, not the handler scenarios where most findings occur. A real Telegram run was not performed because credentials were unavailable; actual Telegram API delivery and UI behavior therefore remain unverified.
