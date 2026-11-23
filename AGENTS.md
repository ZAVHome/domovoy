# Repository Guidelines

## Project Overview

Domovoy is a Telegram bot starter for collecting residents' reports about building management. The intended flow is for a resident to start a report in a configured building group and continue in a private chat with the bot, preserving the building context through a Telegram deep link.

The current implementation supports text reports end to end. It currently:

- Loads environment settings and initializes the SQLite schema at startup.
- Handles `/report` in a configured group and starts the report wizard from a private-chat deep link.
- Collects optional resident profile details, configured text fields, and saves a report after confirmation.
- Allows residents to page through and view their own reports with `/my_reports`.
- Allows configured responders to process assigned houses with `/reports`; the administrator can process all houses.
- Records status history and sends new-report and status-change notifications.

Photo/video intake, in-bot configuration management, and persistent FSM sessions are not implemented. User-facing bot messages are in Russian; identifiers and code comments/docstrings are in English.

## Documentation Requirements

- Create all project documentation in both Russian and English.
- Keep the Russian and English versions synchronized whenever documentation is added or updated.
- Give every work plan a unique, zero-padded three-digit sequence number. Create folders as `artifacts/NNN-short-name/`, assigning one greater than the highest existing number; never reuse a number. Store the plan and concise completion report there as English and Russian pairs (`plan.md`, `plan.ru.md`, `completion.md`, `completion.ru.md`).
- Work plans record the goal, scope, implementation stages, and acceptance criteria. Completion reports summarize what was implemented, checks performed, and any limitations or follow-up work.

## Technology Stack

- Python 3.11 or newer.
- aiogram `>=3.32,<4`, using long polling rather than webhooks.
- python-dotenv `>=1.0,<2` for loading the root `.env` file.
- SQLite through Python's standard `sqlite3` module.
- setuptools with a `src/` package layout; package discovery is configured in `pyproject.toml`.

There is no lockfile, web framework, external database service, migration tool, task queue, or container configuration in this checkout.

## Project Structure and Module Responsibilities

- `pyproject.toml`: package metadata, Python requirement, runtime dependencies, and setuptools configuration.
- `src/domovoy/__main__.py`: application entry point. Loads settings, initializes the database, creates the aiogram `Bot` and `Dispatcher`, registers the router, and starts long polling. `settings` is passed through `start_polling` for injection into handlers.
- `src/domovoy/config.py`: settings, JSON loading, and startup validation for houses, classification, statuses, and responder assignments.
- `src/domovoy/database.py`: SQLite schema initialization and additive migrations, including report submission idempotency.
- `src/domovoy/repository.py`: parameterized data access, paginated access-filtered queries, transactional report creation, and compare-and-set status updates.
- `src/domovoy/states.py`: report wizard states. FSM state is memory-only and is not restart-persistent.
- `src/domovoy/handlers.py`: report wizard, resident report views, responder processing, status changes, and notifications.
- `src/domovoy/__init__.py`: package docstring only.
- `config/`: sanitized JSON examples for houses, classification, statuses, and responder assignments.
- `artifacts/`: bilingual work plans and concise completion reports in sequentially numbered folders such as `001-text-report-mvp/`.
- `.env.example`: environment variable template.
- `README.md`: concise setup instructions and current implementation status.

## Local Setup, Build, and Run

Use the root of the checkout as the working directory:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set `BOT_TOKEN` and a numeric `ADMIN_TELEGRAM_ID` in `.env`. Replace the example chat ID and building address in `config/houses.json`, and configure the other JSON files as needed. Add the bot to the configured building group, then run:

```sh
python -m domovoy
```

Use `/report` in that group to receive the private-chat link. A real functional run requires valid Telegram credentials and a reachable Telegram API.

`PROJECT_ROOT` is derived from `src/domovoy/config.py`, and `CONFIG_DIR` is always `<project root>/config`. `DATABASE_PATH` defaults to `./data/domovoy.sqlite3`; relative paths are resolved against the project root, not the caller's current directory. Database initialization creates missing parent directories and applies migrations. Houses, categories, statuses, and responder assignments remain JSON-backed and are validated at startup rather than seeded into SQLite.

## Configuration Files

Environment variables:

- `BOT_TOKEN`: required; startup fails with a `RuntimeError` if it is empty.
- `ADMIN_TELEGRAM_ID`: required and must contain decimal digits only. It currently controls the administrator greeting in `/start`; it does not create a database role.
- `DATABASE_PATH`: optional SQLite path, defaulting to `./data/domovoy.sqlite3`.

JSON configuration:

- `config/houses.json`: `chats` maps exact Telegram group IDs to house IDs and addresses.
- `config/classification.json`: `locations` contain categories and text fields; field ID `description` is stored as the report description.
- `config/statuses.json`: statuses must be `new`, `in_progress`, `resolved`, and `closed` in that order, with only `new` marked initial.
- `config/responders.json`: `assignments` maps each configured house ID to positive Telegram user IDs.

JSON is validated at startup, including references from responder assignments to configured houses. There is no administrative configuration interface; edit JSON and restart the bot to apply changes.

## Coding Conventions

Follow the existing Python style: four-space indentation, descriptive module and function names, type annotations on public functions and settings, `pathlib.Path` for paths, and absolute `domovoy.*` imports. Telegram handlers are `async` functions registered on the shared `Router`. Keep user-facing text in Russian unless the product language is intentionally changed.

JSON examples use two-space indentation. Keep their placeholder Telegram IDs, addresses, and tokens sanitized.

No formatter or linter is configured in `pyproject.toml`, and no formatting/lint command is established. Do not claim a particular tool is enforced; if one is introduced, document its configuration and command here.

## Testing and Verification

The test suite uses the Python standard library `unittest`; handler control tests run when the project dependency aiogram is installed. Run `python -m unittest discover -s tests`.

A standard-library syntax check can be run with:

```sh
python -m compileall src
```

Run `python -m compileall src tests` for a syntax check. For functional verification, exercise the flow with valid Telegram credentials: `/report` in a configured group, profile skips, report confirmation, `/my_reports`, `/reports`, and status notification. Database changes must preserve data in an existing database as well as initialize a fresh one.

## Intended Domain Behavior

The existing project guidance describes the following requirements for future implementation; they are not current runtime behavior:

- Reports support text and photo/video. Configured locations determine available categories, and categories define required and optional fields.
- Residents are identified by Telegram profile. On first contact, section, floor, and apartment are optional and individually skippable.
- Residents create text reports and can see all details and status history of their own reports.
- Responders are configured per house in JSON and process only assigned houses. The administrator from `ADMIN_TELEGRAM_ID` may process all houses.
- Report content is visible to assigned responders and administrators.
- Responders are notified of new reports, and residents are notified of status changes.

Keep these authorization and privacy requirements in mind when implementing the currently empty report and role workflows.

## Security and Deployment Notes

Keep credentials and local settings in environment variables. `.env`, virtual environments, Python caches, and SQLite files are listed in `.gitignore`. Never commit real bot tokens, credentials, private keys, production configuration, or local databases; keep examples sanitized. The schema includes resident profile details and report content, so database files and Telegram file IDs must be treated as application data with appropriate access controls.

Deployment currently consists of running the single long-polling Python process with its environment, JSON configuration, and a writable SQLite path. FSM progress is memory-only and is lost on restart. There is no Docker, CI, webhook, process-manager, or backup configuration in this checkout; do not describe those as existing deployment steps.

## Commit and Pull Request Guidelines

Before each commit intended for GitHub, increase the bot version in `pyproject.toml` by `0.01` and include that version change in the commit. Start at `0.01`, then use `0.02`, `0.03`, and so on. The initial project commit is on branch `master`; use concise, imperative commit subjects such as `Add configuration loader`. Pull requests should explain the change and motivation, list validation performed, link relevant issues where applicable, and include screenshots for user-facing visual changes.
