"""Persistence and authorization tests using only the standard library."""

import sqlite3
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from domovoy import config
from domovoy.database import initialize_database
from domovoy.repository import (
    change_report_status,
    create_report,
    ensure_user,
    get_report_for_resident,
    get_report_for_responder,
    list_resident_reports,
    list_responder_reports,
    save_profile,
)


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "domovoy.sqlite3"
        initialize_database(self.database_path)
        ensure_user(self.database_path, 101, "resident", "Resident One")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_report_history_and_access_filters(self) -> None:
        report_id = create_report(
            self.database_path, house_id="house-a", author_id=101, address="1 Main St",
            location_id="grounds", category_id="cleaning", description="Broken lamp",
            fields={"description": "Broken lamp", "entrance": "2"},
            submission_token="report-one",
        )

        report = get_report_for_resident(self.database_path, report_id, 101)
        self.assertIsNotNone(report)
        assert report is not None
        self.assertEqual(report["status_id"], "new")
        self.assertEqual(report["fields"], {"entrance": "2"})
        self.assertEqual(len(report["history"]), 1)
        self.assertIsNone(get_report_for_resident(self.database_path, report_id, 202))
        self.assertEqual(list_responder_reports(self.database_path, ["house-b"]), ([], False))
        self.assertEqual(len(list_responder_reports(self.database_path, ["house-a"])[0]), 1)
        self.assertIsNone(get_report_for_responder(self.database_path, report_id, ["house-b"]))

        self.assertTrue(change_report_status(
            self.database_path, report_id, "in_progress", 303, expected_status="new"
        ))
        updated = get_report_for_resident(self.database_path, report_id, 101)
        assert updated is not None
        self.assertEqual(updated["status_id"], "in_progress")
        self.assertEqual(len(updated["history"]), 2)

    def test_stale_status_change_is_rejected_atomically(self) -> None:
        report_id = create_report(
            self.database_path, house_id="house-a", author_id=101, address="1 Main St",
            location_id="grounds", category_id="cleaning", description="Broken lamp",
            fields={}, submission_token="stale-status",
        )
        self.assertTrue(change_report_status(
            self.database_path, report_id, "closed", 999, expected_status="new"
        ))
        self.assertFalse(change_report_status(
            self.database_path, report_id, "in_progress", 303, expected_status="new"
        ))
        report = get_report_for_resident(self.database_path, report_id, 101)
        assert report is not None
        self.assertEqual(report["status_id"], "closed")
        self.assertEqual([item["status_id"] for item in report["history"]], ["new", "closed"])

    def test_submission_is_idempotent_and_profile_marker_is_atomic(self) -> None:
        arguments = dict(
            house_id="house-a", author_id=101, address="1 Main St", location_id="grounds",
            category_id="cleaning", description="Broken lamp", fields={},
            submission_token="same-confirmation",
        )
        first_id = create_report(self.database_path, **arguments)
        repeated_id = create_report(self.database_path, **arguments)
        self.assertEqual(first_id, repeated_id)
        self.assertEqual(len(list_resident_reports(self.database_path, 101)[0]), 1)
        report = get_report_for_resident(self.database_path, first_id, 101)
        assert report is not None
        self.assertEqual(len(report["history"]), 1)
        with sqlite3.connect(self.database_path) as connection:
            prompted = connection.execute(
                "SELECT profile_prompted FROM users WHERE telegram_user_id=101"
            ).fetchone()[0]
        self.assertEqual(prompted, 1)

    def test_failed_report_transaction_rolls_back_profile_and_report(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("""CREATE TRIGGER fail_initial_history
                BEFORE INSERT ON report_status_history
                BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            create_report(
                self.database_path, house_id="house-a", author_id=101, address="1 Main St",
                location_id="grounds", category_id="cleaning", description="Broken lamp",
                fields={}, submission_token="rolled-back",
            )
        self.assertEqual(list_resident_reports(self.database_path, 101)[0], [])
        with sqlite3.connect(self.database_path) as connection:
            prompted = connection.execute(
                "SELECT profile_prompted FROM users WHERE telegram_user_id=101"
            ).fetchone()[0]
        self.assertEqual(prompted, 0)

    def test_report_pagination_keeps_oldest_resident_and_admin_reports_reachable(self) -> None:
        ids = []
        for index in range(21):
            ids.append(create_report(
                self.database_path, house_id=f"house-{index % 2}", author_id=101,
                address=f"{index} Main St", location_id="grounds", category_id="cleaning",
                description=f"Issue {index}", fields={}, submission_token=f"page-{index}",
            ))
        resident_page, resident_more = list_resident_reports(
            self.database_path, 101, limit=10, offset=0
        )
        resident_last, resident_last_more = list_resident_reports(
            self.database_path, 101, limit=10, offset=20
        )
        admin_first, admin_more = list_responder_reports(
            self.database_path, None, limit=10, offset=0
        )
        admin_page, admin_last_more = list_responder_reports(
            self.database_path, None, limit=10, offset=20
        )
        assigned_first, assigned_more = list_responder_reports(
            self.database_path, ["house-0"], limit=10, offset=0
        )
        assigned_last, assigned_last_more = list_responder_reports(
            self.database_path, ["house-0"], limit=10, offset=10
        )
        self.assertTrue(resident_more)
        self.assertEqual(len(resident_page), 10)
        self.assertFalse(resident_last_more)
        self.assertEqual(resident_last[0]["id"], ids[0])
        self.assertTrue(admin_more)
        self.assertEqual(len(admin_first), 10)
        self.assertFalse(admin_last_more)
        self.assertEqual(admin_page[0]["id"], ids[0])
        self.assertIsNotNone(get_report_for_responder(self.database_path, ids[0]))
        self.assertTrue(assigned_more)
        self.assertEqual(len(assigned_first), 10)
        self.assertFalse(assigned_last_more)
        self.assertEqual(assigned_last[0]["id"], ids[0])
        self.assertIsNotNone(get_report_for_responder(self.database_path, ids[0], ["house-0"]))

    def test_profile_is_optional_and_prompted_once(self) -> None:
        user = ensure_user(self.database_path, 101, "resident", "Resident One")
        self.assertEqual(user["profile_prompted"], 0)
        save_profile(self.database_path, 101, {"section": "A", "floor": None, "apartment": "4"})
        with sqlite3.connect(self.database_path) as connection:
            section, floor, apartment, prompted = connection.execute(
                "SELECT section, floor, apartment, profile_prompted FROM users WHERE telegram_user_id=101"
            ).fetchone()
        self.assertEqual((section, floor, apartment, prompted), ("A", None, "4", 1))

    def test_existing_database_is_migrated_without_losing_users(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as connection:
            connection.executescript("""
                CREATE TABLE users (
                    telegram_user_id INTEGER PRIMARY KEY, username TEXT,
                    display_name TEXT NOT NULL, section TEXT, floor TEXT, apartment TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO users(telegram_user_id, display_name) VALUES (77, 'Existing');
                CREATE TABLE reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    house_id TEXT NOT NULL,
                    author_telegram_user_id INTEGER NOT NULL REFERENCES users(telegram_user_id),
                    address TEXT NOT NULL,
                    location_id TEXT,
                    category_id TEXT,
                    description TEXT,
                    status_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO reports
                    (id, house_id, author_telegram_user_id, address, description, status_id)
                    VALUES (17, 'legacy-house', 77, 'Old address', 'Old report', 'new');
            """)
        initialize_database(legacy_path)
        with sqlite3.connect(legacy_path) as connection:
            row = connection.execute(
                "SELECT display_name, profile_prompted FROM users WHERE telegram_user_id=77"
            ).fetchone()
            report_row = connection.execute(
                "SELECT id, description, submission_token FROM reports WHERE id=17"
            ).fetchone()
        self.assertEqual(row, ("Existing", 0))
        self.assertEqual(report_row, (17, "Old report", None))

    def test_runtime_configuration_is_valid(self) -> None:
        configs = config.load_validated_configs()
        self.assertEqual(configs["statuses"]["statuses"][0]["id"], "new")

    def test_unknown_responder_house_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_dir = Path(directory)
            for name in ("houses.json", "classification.json", "statuses.json", "responders.json"):
                shutil.copy(config.CONFIG_DIR / name, config_dir / name)
            responder_file = config_dir / "responders.json"
            responder_data = json.loads(responder_file.read_text(encoding="utf-8"))
            responder_data["assignments"][0]["house_id"] = "unknown-house"
            responder_file.write_text(json.dumps(responder_data), encoding="utf-8")
            with patch.object(config, "CONFIG_DIR", config_dir):
                with self.assertRaisesRegex(RuntimeError, "unique configured house IDs"):
                    config.load_validated_configs()

    def test_status_titles_are_required_and_non_empty_strings(self) -> None:
        for invalid_title in (None, "", 123):
            with self.subTest(title=invalid_title), tempfile.TemporaryDirectory() as directory:
                config_dir = Path(directory)
                for name in ("houses.json", "classification.json", "statuses.json", "responders.json"):
                    shutil.copy(config.CONFIG_DIR / name, config_dir / name)
                status_file = config_dir / "statuses.json"
                statuses = json.loads(status_file.read_text(encoding="utf-8"))
                if invalid_title is None:
                    del statuses["statuses"][0]["title"]
                else:
                    statuses["statuses"][0]["title"] = invalid_title
                status_file.write_text(json.dumps(statuses), encoding="utf-8")
                with patch.object(config, "CONFIG_DIR", config_dir):
                    with self.assertRaisesRegex(RuntimeError, "non-empty title"):
                        config.load_validated_configs()


if __name__ == "__main__":
    unittest.main()
