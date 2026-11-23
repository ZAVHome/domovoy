"""Tests for Telegram-safe long text formatting."""

import unittest

from domovoy.presentation import SAFE_MESSAGE_UNITS, split_telegram_text


class PresentationTests(unittest.TestCase):
    def test_splits_long_text_by_utf16_units_without_losing_content(self) -> None:
        text = ("Домовой 🏠\n" * 800) + "Конец"
        chunks = split_telegram_text(text)
        self.assertEqual("".join(chunks), text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(
            len(chunk.encode("utf-16-le")) // 2 <= SAFE_MESSAGE_UNITS
            for chunk in chunks
        ))

    def test_handles_text_at_and_above_message_boundary(self) -> None:
        for length in (4095, 4096, 4097):
            with self.subTest(length=length):
                text = "я" * length
                chunks = split_telegram_text(text)
                self.assertEqual("".join(chunks), text)
                self.assertTrue(all(len(chunk) <= SAFE_MESSAGE_UNITS for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
