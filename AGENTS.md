# Repository Guidelines

## Project Overview

Domovoy is a Telegram bot starter for collecting residents' reports about building management. The intended flow is for a resident to start a report in a configured building group and continue in a private chat with the bot, preserving the building context through a Telegram deep link.

The current implementation is a scaffold, not a complete reporting system. It currently:

- Loads environment settings and initializes the SQLite schema at startup.
- Handles `/report` in a configured non-private chat and replies with a private-chat deep link containing `report_<telegram_chat_id>`.
- Handles `/start`, resolves the deep-link payload back to a configured house, and displays its address.
- Identifies the configured bootstrap administrator by Telegram user ID for an additional greeting. Persistent role management is not implemented.

Profile collection, the report wizard, report persistence, media intake, responder assignment, role management, status changes, and notifications are planned but not yet implemented. User-facing bot messages are in Russian; identifiers and code comments/docstrings are in English.

## Documentation Requirements

- Create all project documentation in both Russian and English.
- Keep the Russian and English versions synchronized whenever documentation is added or updated.

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
- `src/domovoy/config.py`: defines the frozen `Settings` dataclass, resolves the project root and `config/` directory, loads `.env`, validates required settings, resolves the database path, and provides `load_json_config(name)`.
- `src/domovoy/database.py`: creates the SQLite parent directory and tables with `CREATE TABLE IF NOT EXISTS`. The schema contains `users`, `reports`, `report_fields`, `report_media`, and `report_status_history`; foreign keys and report-owned cascades are declared. There are no migrations or data-access/repository functions yet.
- `src/domovoy/handlers.py`: contains the single aiogram `Router` and the `/report` and `/start` handlers. House configuration is loaded when these handlers need it.
- `src/domovoy/__init__.py`: package docstring only.
- `config/`: sanitized JSON examples for houses, classification, statuses, and responder assignments.
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

`PROJECT_ROOT` is derived from `src/domovoy/config.py`, and `CONFIG_DIR` is always `<project root>/config`. `DATABASE_PATH` defaults to `./data/domovoy.sqlite3`; relative paths are resolved against the project root, not the caller's current directory. Database initialization creates missing parent directories and tables, but startup does not seed houses, statuses, responders, or roles from JSON.

## Configuration Files

Environment variables:

- `BOT_TOKEN`: required; startup fails with a `RuntimeError` if it is empty.
- `ADMIN_TELEGRAM_ID`: required and must contain decimal digits only. It currently controls the administrator greeting in `/start`; it does not create a database role.
- `DATABASE_PATH`: optional SQLite path, defaulting to `./data/domovoy.sqlite3`.

JSON configuration:

- `config/houses.json`: top-level `chats` array. Each entry has `telegram_chat_id`, `house_id`, `address`, and `title`. This is the only JSON file currently read by runtime handlers. Chat IDs must match Telegram's integer IDs exactly, including the negative sign for groups.
- `config/classification.json`: top-level `locations`; locations contain `categories`, and categories contain `fields` with IDs, titles, types, and required flags. This models future location-dependent report categories and fields but is not consumed by code yet.
- `config/statuses.json`: top-level `statuses`, including an `initial` marker on the example `new` status. It is not consumed by code yet.
- `config/responders.json`: top-level `assignments`, mapping `house_id` to `telegram_user_ids`. It is not consumed by code yet.

JSON is loaded directly with `json.load`; there is no schema validation, cross-file reference validation, caching layer, or administrative configuration interface.

## Coding Conventions

Follow the existing Python style: four-space indentation, descriptive module and function names, type annotations on public functions and settings, `pathlib.Path` for paths, and absolute `domovoy.*` imports. Telegram handlers are `async` functions registered on the shared `Router`. Keep user-facing text in Russian unless the product language is intentionally changed.

JSON examples use two-space indentation. Keep their placeholder Telegram IDs, addresses, and tokens sanitized.

No formatter or linter is configured in `pyproject.toml`, and no formatting/lint command is established. Do not claim a particular tool is enforced; if one is introduced, document its configuration and command here.

## Testing and Verification

There is currently no test suite, test directory, test dependency, or test-runner configuration. Do not assume pytest or another framework is available.

A standard-library syntax check can be run with:

```sh
python -m compileall src
```

For functional verification, install the package and exercise the real flow with `python -m domovoy`: `/report` in a configured group should produce the deep-link button, and the resulting `/start report_<chat_id>` flow should identify the configured house. Also check the unconfigured-group and invalid-house-payload responses when changing these handlers. Database changes should be checked against a fresh SQLite file and an existing file because initialization uses `IF NOT EXISTS` and does not migrate existing tables.

## Intended Domain Behavior

The existing project guidance describes the following requirements for future implementation; they are not current runtime behavior:

- Reports support text and photo/video. Configured locations determine available categories, and categories define required and optional fields.
- Residents are identified by Telegram profile. On first contact, section, floor, and apartment are optional and individually skippable.
- Residents create reports and can see all details and status history of their own reports.
- Responders process assigned reports and change status; administrators manage configuration and assign responders.
- Report content is visible to assigned responders and administrators.
- Responders are notified of new reports, and residents are notified of status changes.

Keep these authorization and privacy requirements in mind when implementing the currently empty report and role workflows.

## Security and Deployment Notes

Keep credentials and local settings in environment variables. `.env`, virtual environments, Python caches, and SQLite files are listed in `.gitignore`. Never commit real bot tokens, credentials, private keys, production configuration, or local databases; keep examples sanitized. The schema includes resident profile details and report content, so database files and Telegram file IDs must be treated as application data with appropriate access controls.

Deployment currently consists of running the single long-polling Python process with its environment, JSON configuration, and a writable SQLite path. There is no Docker, CI, webhook, process-manager, backup, or migration configuration in this checkout; do not describe those as existing deployment steps.

## Commit and Pull Request Guidelines

The repository is initialized on branch `master`, but it has no commits yet, so no established commit convention can be confirmed. Until one is adopted, use concise, imperative commit subjects such as `Add configuration loader`. Pull requests should explain the change and motivation, list validation performed, link relevant issues where applicable, and include screenshots for user-facing visual changes.
