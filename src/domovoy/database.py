"""SQLite bootstrap for persistent bot data."""

import sqlite3
from pathlib import Path


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS users (
                telegram_user_id INTEGER PRIMARY KEY,
                username TEXT,
                display_name TEXT NOT NULL,
                section TEXT,
                floor TEXT,
                apartment TEXT,
                profile_prompted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                house_id TEXT NOT NULL,
                author_telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id),
                address TEXT NOT NULL,
                location_id TEXT,
                category_id TEXT,
                description TEXT,
                status_id TEXT NOT NULL,
                submission_token TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS report_fields (
                report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                field_id TEXT NOT NULL,
                value TEXT,
                PRIMARY KEY (report_id, field_id)
            );

            CREATE TABLE IF NOT EXISTS report_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                media_type TEXT NOT NULL,
                telegram_file_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS report_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                status_id TEXT NOT NULL,
                changed_by_telegram_user_id INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        user_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(users)")
        }
        if "profile_prompted" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN profile_prompted INTEGER NOT NULL DEFAULT 0"
            )
        report_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(reports)")
        }
        if "submission_token" not in report_columns:
            connection.execute("ALTER TABLE reports ADD COLUMN submission_token TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_submission_token "
            "ON reports(submission_token)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_author_created "
            "ON reports(author_telegram_user_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_house_status "
            "ON reports(house_id, status_id, created_at DESC)"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1), (2)"
        )
