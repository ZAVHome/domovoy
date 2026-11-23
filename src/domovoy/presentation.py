"""Telegram-safe text formatting helpers."""


TELEGRAM_TEXT_LIMIT = 4096
SAFE_MESSAGE_UNITS = 3500


def split_telegram_text(text: str, max_units: int = SAFE_MESSAGE_UNITS) -> list[str]:
    """Split text into chunks below Telegram's limit, counting UTF-16 code units."""
    if max_units <= 0 or max_units > TELEGRAM_TEXT_LIMIT:
        raise ValueError("max_units must be between 1 and Telegram's text limit")
    if not text:
        return [""]
    chunks: list[str] = []
    current: list[str] = []
    current_units = 0
    for character in text:
        character_units = len(character.encode("utf-16-le")) // 2
        if current and current_units + character_units > max_units:
            chunks.append("".join(current))
            current = []
            current_units = 0
        current.append(character)
        current_units += character_units
    if current:
        chunks.append("".join(current))
    return chunks
