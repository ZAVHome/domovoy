# Domovoy

Domovoy is a Telegram bot for collecting residents' reports about building management. It uses Python, aiogram long polling, JSON configuration, and SQLite. Russian-language documentation: [README.ru.md](README.ru.md).

## Current features

- Residents start a report in a configured building group and continue in a private chat through a deep link.
- The bot collects optional resident profile details, then guides the resident through configured locations, categories, and text fields. The report can be cancelled and is saved only after confirmation.
- Residents can page through their reports and view details and status history with `/my_reports`.
- Configured responders can list reports assigned to their houses with `/reports`, view their content, and move them through `new → in_progress → resolved → closed`.
- The administrator configured by `ADMIN_TELEGRAM_ID` can view reports across all houses and set any status.
- Responders receive new-report notifications; residents receive status-change notifications. Failed Telegram delivery is logged; the database update is retained.

Photos and videos, in-bot configuration management, and persistent conversation recovery are not implemented. FSM progress is held in memory and is lost if the process restarts.

## Requirements and local setup

- Python 3.11 or newer
- A Telegram bot token from BotFather
- The numeric Telegram user ID of the initial administrator

From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set `BOT_TOKEN` and `ADMIN_TELEGRAM_ID` in `.env`. Optionally set `DATABASE_PATH`; it defaults to `./data/domovoy.sqlite3` and relative paths resolve from the repository root. Review the JSON files in `config/`, add the bot to each configured group, and start it:

```sh
python -m domovoy
```

The process uses long polling and must be kept running. Responders must open the bot at least once before it can send them private notifications. A working run requires valid credentials and access to the Telegram API.

## Configuration

- `config/houses.json` maps Telegram group IDs to house IDs and addresses. Use the exact integer chat ID, including its minus sign.
- `config/classification.json` defines locations, categories, and text fields. Fields may be required or optional; a field with ID `description` becomes the report description.
- `config/statuses.json` must contain `new`, `in_progress`, `resolved`, and `closed` in that order, with `new` as the only initial status.
- `config/responders.json` maps each configured `house_id` to Telegram user IDs. The administrator is configured separately through `ADMIN_TELEGRAM_ID`.

Configuration is validated at startup, including cross-file house references. Edit JSON files directly to change assignments or report categories. Do not put real credentials in them. `.env`, SQLite databases, and virtual environments are ignored by Git.

## Data and access

SQLite stores resident profiles, reports, dynamic field values, and status history. Startup applies schema migrations and preserves existing records. Report submission uses an idempotency token, and status changes use a conditional transactional update. Residents can access only their own reports. Responders can access only houses assigned to them; the administrator can access all houses. Protect the database file as application data.

## Project map

- `src/domovoy/__main__.py`: configuration validation, database initialization, and long polling.
- `src/domovoy/config.py`: environment settings and validated JSON loading.
- `src/domovoy/handlers.py` and `src/domovoy/states.py`: Telegram commands, callbacks, and report wizard.
- `src/domovoy/repository.py` and `src/domovoy/database.py`: SQLite operations and schema migration.
- `config/`: sanitized examples for houses, classification, statuses, and responders.
- `artifacts/`: bilingual work plans and concise completion reports in sequentially numbered folders such as `001-text-report-mvp/`.

Run the standard-library checks with `python -m unittest discover -s tests` and `python -m compileall src tests`. There is no formatter, linter, or container configured.
