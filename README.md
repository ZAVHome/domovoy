# Domovoy

Domovoy is a Telegram bot starter for collecting residents' reports about building management. It uses Python, aiogram long polling, JSON configuration, and SQLite. Russian-language documentation: [README.ru.md](README.ru.md).

## Current implementation

The current scaffold loads environment settings, creates the SQLite schema, and supports the entry point from a configured building group to a private bot chat:

1. A resident sends `/report` in a configured group.
2. The bot replies with a button linking to its private chat and carrying the source group ID.
3. `/start report_<chat_id>` resolves that ID to the configured house and displays its address.

The report wizard, profile collection, report/media persistence, role management, responder assignment, status changes, and notifications are not implemented yet. `ADMIN_TELEGRAM_ID` currently adds an administrator greeting only; it does not grant persistent permissions.

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

Set `BOT_TOKEN` and `ADMIN_TELEGRAM_ID` in `.env`. Optionally set `DATABASE_PATH`; it defaults to `./data/domovoy.sqlite3` and relative paths resolve from the repository root. Then replace the sample group ID and address in `config/houses.json`, add the bot to that group, and start it:

```sh
python -m domovoy
```

The process uses long polling and must be kept running. A working run requires valid credentials and access to the Telegram API.

## Configuration

All example configuration is JSON and can be edited directly:

- `config/houses.json` maps Telegram group IDs to house IDs and addresses. Use the exact integer chat ID, including its minus sign.
- `config/classification.json` models locations, their categories, and each category's required or optional fields. It is a future configuration shape and is not read by the running bot yet.
- `config/statuses.json` lists report statuses and marks the initial status. Not yet consumed by runtime code.
- `config/responders.json` maps house IDs to responder Telegram user IDs. Not yet consumed by runtime code.

JSON is currently loaded without schema or cross-file validation. Do not put real credentials in these files. `.env`, SQLite databases, and virtual environments are ignored by Git.

## Project map

- `src/domovoy/__main__.py`: startup and long polling.
- `src/domovoy/config.py`: environment settings and JSON loading.
- `src/domovoy/handlers.py`: `/report` and `/start` handlers.
- `src/domovoy/database.py`: initial SQLite tables for users, reports, report fields, media, and status history. No migrations or repository functions yet.
- `config/`: sanitized JSON examples.
- `AGENTS.md` and `AGENTS.ru.md`: English and Russian contributor guides with detailed project behavior requirements.

There is no test suite, formatter, linter, migration framework, or deployment container configured yet.
