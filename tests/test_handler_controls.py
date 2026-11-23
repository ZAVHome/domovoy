"""Telegram control tests; run when the project dependency aiogram is installed."""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from domovoy.config import Settings


@unittest.skipUnless(importlib.util.find_spec("aiogram"), "aiogram is not installed")
class HandlerControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_transition_keeps_next_action_keyboard(self) -> None:
        from domovoy.handlers import update_report_status

        old_report = {"id": 1, "house_id": "house-a", "status_id": "new",
                      "author_telegram_user_id": 42}
        updated_report = {**old_report, "status_id": "in_progress"}
        message = SimpleNamespace(
            chat=SimpleNamespace(type="private"),
            edit_text=AsyncMock(),
            answer=AsyncMock(),
        )
        callback = SimpleNamespace(
            message=message,
            data="status:1:in_progress",
            from_user=SimpleNamespace(id=7),
            answer=AsyncMock(),
            bot=SimpleNamespace(send_message=AsyncMock()),
        )
        settings = Settings("token", 999, Path("unused.sqlite3"))
        configs = {
            "statuses": {"statuses": [
                {"id": "new", "title": "Новая"},
                {"id": "in_progress", "title": "В работе"},
                {"id": "resolved", "title": "Решена"},
                {"id": "closed", "title": "Закрыта"},
            ]},
            "responders": {"assignments": [
                {"house_id": "house-a", "telegram_user_ids": [7]}
            ]},
        }
        with patch("domovoy.handlers.load_validated_configs", return_value=configs), \
                patch("domovoy.handlers.get_report_for_responder", side_effect=[old_report, updated_report]), \
                patch("domovoy.handlers.change_report_status", return_value=True) as change:
            await update_report_status(callback, settings)

        change.assert_called_once_with(
            settings.database_path, 1, "in_progress", 7, expected_status="new"
        )
        kwargs = message.edit_text.await_args.kwargs
        buttons = kwargs["reply_markup"].inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "status:1:resolved")

    async def test_closed_responder_report_has_no_next_transition(self) -> None:
        from domovoy.handlers import _report_keyboard

        configs = {"statuses": {"statuses": [
            {"id": "new", "title": "Новая"},
            {"id": "in_progress", "title": "В работе"},
            {"id": "resolved", "title": "Решена"},
            {"id": "closed", "title": "Закрыта"},
        ]}}
        self.assertIsNone(_report_keyboard(
            {"id": 1, "status_id": "closed"}, configs, admin=False, responder=True
        ))


if __name__ == "__main__":
    unittest.main()
