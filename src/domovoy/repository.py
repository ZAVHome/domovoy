"""SQLite operations and access checks for residents and reports."""

import sqlite3
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_user(path: Path, user_id: int, username: str | None,
                display_name: str) -> dict[str, Any]:
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO users(telegram_user_id, username, display_name)
               VALUES (?, ?, ?)
               ON CONFLICT(telegram_user_id) DO UPDATE SET
                 username=excluded.username, display_name=excluded.display_name""",
            (user_id, username, display_name),
        )
        row = connection.execute(
            "SELECT * FROM users WHERE telegram_user_id=?", (user_id,)
        ).fetchone()
        return dict(row)


def save_profile(path: Path, user_id: int, values: dict[str, str | None]) -> None:
    with _connect(path) as connection:
        connection.execute(
            """UPDATE users SET section=?, floor=?, apartment=?, profile_prompted=1
               WHERE telegram_user_id=?""",
            (values.get("section"), values.get("floor"), values.get("apartment"), user_id),
        )


def create_report(path: Path, *, house_id: str, author_id: int, address: str,
                  location_id: str, category_id: str, description: str,
                  fields: dict[str, str], submission_token: str) -> int:
    with _connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO reports
               (house_id, author_telegram_user_id, address, location_id, category_id,
                description, status_id, submission_token)
               VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
               ON CONFLICT(submission_token) DO NOTHING""",
            (house_id, author_id, address, location_id, category_id, description,
             submission_token),
        )
        if cursor.rowcount == 0:
            existing = connection.execute(
                "SELECT id FROM reports WHERE submission_token=?", (submission_token,)
            ).fetchone()
            if existing is None:
                raise RuntimeError("Report insert was ignored without an idempotency match")
            return int(existing["id"])
        report_id = int(cursor.lastrowid)
        connection.executemany(
            "INSERT INTO report_fields(report_id, field_id, value) VALUES (?, ?, ?)",
            [(report_id, field_id, value) for field_id, value in fields.items()
             if field_id != "description"],
        )
        connection.execute(
            """INSERT INTO report_status_history
               (report_id, status_id, changed_by_telegram_user_id, note)
               VALUES (?, 'new', ?, 'Заявка создана')""",
            (report_id, author_id),
        )
        connection.execute(
            "UPDATE users SET profile_prompted=1 WHERE telegram_user_id=?", (author_id,)
        )
        return report_id


def _report_details(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    report = dict(row)
    report["fields"] = {
        field["field_id"]: field["value"]
        for field in connection.execute(
            "SELECT field_id, value FROM report_fields WHERE report_id=? ORDER BY field_id",
            (report["id"],),
        )
    }
    report["history"] = [dict(item) for item in connection.execute(
        """SELECT status_id, changed_by_telegram_user_id, note, created_at
           FROM report_status_history WHERE report_id=? ORDER BY id""",
        (report["id"],),
    )]
    return report


def list_resident_reports(path: Path, user_id: int, *, limit: int = 10,
                          offset: int = 0) -> tuple[list[dict[str, Any]], bool]:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT * FROM reports WHERE author_telegram_user_id=?
               ORDER BY id DESC LIMIT ? OFFSET ?""", (user_id, limit + 1, offset)
        ).fetchall()
        has_more = len(rows) > limit
        return [_report_details(connection, row) for row in rows[:limit]], has_more


def get_report_for_resident(path: Path, report_id: int,
                            user_id: int) -> dict[str, Any] | None:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT * FROM reports WHERE id=? AND author_telegram_user_id=?",
            (report_id, user_id),
        ).fetchone()
        return _report_details(connection, row) if row else None


def list_responder_reports(path: Path, house_ids: list[str] | None,
                           *, limit: int = 10, offset: int = 0
                           ) -> tuple[list[dict[str, Any]], bool]:
    if house_ids is not None and not house_ids:
        return [], False
    with _connect(path) as connection:
        if house_ids is None:
            rows = connection.execute(
                "SELECT * FROM reports ORDER BY id DESC LIMIT ? OFFSET ?", (limit + 1, offset)
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in house_ids)
            rows = connection.execute(
                f"SELECT * FROM reports WHERE house_id IN ({placeholders}) "
                "ORDER BY id DESC LIMIT ? OFFSET ?", (*house_ids, limit + 1, offset),
            ).fetchall()
        has_more = len(rows) > limit
        return [_report_details(connection, row) for row in rows[:limit]], has_more


def get_report_for_responder(path: Path, report_id: int,
                             house_ids: list[str] | None = None) -> dict[str, Any] | None:
    with _connect(path) as connection:
        if house_ids is None:
            row = connection.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        elif house_ids:
            placeholders = ",".join("?" for _ in house_ids)
            row = connection.execute(
                f"SELECT * FROM reports WHERE id=? AND house_id IN ({placeholders})",
                (report_id, *house_ids),
            ).fetchone()
        else:
            return None
        return _report_details(connection, row) if row else None


def change_report_status(path: Path, report_id: int, status_id: str,
                         actor_id: int, *, expected_status: str,
                         note: str | None = None) -> bool:
    with _connect(path) as connection:
        cursor = connection.execute(
            """UPDATE reports SET status_id=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=? AND status_id=?""",
            (status_id, report_id, expected_status),
        )
        if cursor.rowcount != 1:
            return False
        connection.execute(
            """INSERT INTO report_status_history
               (report_id, status_id, changed_by_telegram_user_id, note)
               VALUES (?, ?, ?, ?)""",
            (report_id, status_id, actor_id, note),
        )
        return True
