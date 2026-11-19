"""Environment and JSON configuration loading."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_telegram_id: int
    database_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        admin_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is required; copy .env.example to .env")
        if not admin_id.isdecimal():
            raise RuntimeError("ADMIN_TELEGRAM_ID must be a numeric Telegram user ID")

        database_path = Path(os.getenv("DATABASE_PATH", "./data/domovoy.sqlite3"))
        if not database_path.is_absolute():
            database_path = PROJECT_ROOT / database_path
        return cls(token, int(admin_id), database_path)


def load_json_config(name: str) -> dict[str, Any]:
    """Load a named JSON file from the project's config directory."""
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)
