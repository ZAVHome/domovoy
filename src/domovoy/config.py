"""Environment and JSON configuration loading."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_telegram_id: int
    database_path: Path

    @classmethod
    def from_env(cls) -> "Settings":
        from dotenv import load_dotenv

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
    if Path(name).name != name:
        raise ValueError("Configuration name must be a file name")
    path = CONFIG_DIR / name
    with path.open(encoding="utf-8") as config_file:
        return json.load(config_file)


def load_validated_configs() -> dict[str, Any]:
    """Load and cross-check runtime configuration files."""
    houses = load_json_config("houses.json")
    classification = load_json_config("classification.json")
    statuses = load_json_config("statuses.json")
    responders = load_json_config("responders.json")

    for name, value in (("houses.json", houses), ("classification.json", classification),
                        ("statuses.json", statuses), ("responders.json", responders)):
        if not isinstance(value, dict):
            raise RuntimeError(f"{name} must contain a JSON object")

    chats = houses.get("chats")
    if not isinstance(chats, list) or not chats:
        raise RuntimeError("houses.json must contain at least one chat")
    chat_ids: set[int] = set()
    house_ids: set[str] = set()
    for chat in chats:
        if not isinstance(chat, dict) or not isinstance(chat.get("telegram_chat_id"), int):
            raise RuntimeError("Each house chat must have an integer telegram_chat_id")
        if (not isinstance(chat.get("house_id"), str) or not chat["house_id"]
                or not isinstance(chat.get("address"), str) or not chat["address"]):
            raise RuntimeError("Each house chat must have house_id and address")
        if chat["telegram_chat_id"] in chat_ids:
            raise RuntimeError("telegram_chat_id values in houses.json must be unique")
        chat_ids.add(chat["telegram_chat_id"])
        house_ids.add(chat["house_id"])

    locations = classification.get("locations")
    if not isinstance(locations, list) or not locations:
        raise RuntimeError("classification.json must contain at least one location")
    location_ids: set[str] = set()
    category_ids: set[str] = set()
    for location in locations:
        if (not isinstance(location, dict) or not isinstance(location.get("id"), str)
                or not location["id"] or not isinstance(location.get("title"), str)
                or not location["title"]):
            raise RuntimeError("Each location must have id and title")
        if location["id"] in location_ids:
            raise RuntimeError("Location IDs in classification.json must be unique")
        location_ids.add(location["id"])
        if not isinstance(location.get("categories"), list):
            raise RuntimeError(f"Location {location['id']} must have a categories array")
        for category in location["categories"]:
            if (not isinstance(category, dict) or not isinstance(category.get("id"), str)
                    or not category["id"] or not isinstance(category.get("title"), str)
                    or not category["title"]):
                raise RuntimeError(f"Each category in {location['id']} must have id and title")
            if category["id"] in category_ids:
                raise RuntimeError("Category IDs in classification.json must be unique")
            category_ids.add(category["id"])
            fields = category.get("fields", [])
            if not isinstance(fields, list):
                raise RuntimeError(f"Category {category['id']} fields must be an array")
            field_ids: set[str] = set()
            for field in fields:
                if (not isinstance(field, dict) or not isinstance(field.get("id"), str)
                        or not field["id"] or not isinstance(field.get("title"), str)
                        or not field["title"]
                        or field.get("type") != "text"):
                    raise RuntimeError(f"Fields in {category['id']} must have id, title, and type=text")
                if field["id"] in field_ids or not isinstance(field.get("required", False), bool):
                    raise RuntimeError(f"Fields in {category['id']} need unique IDs and boolean required flags")
                field_ids.add(field["id"])

    status_list = statuses.get("statuses")
    required_statuses = ["new", "in_progress", "resolved", "closed"]
    if (not isinstance(status_list, list) or not all(isinstance(item, dict) for item in status_list)
            or [item.get("id") for item in status_list] != required_statuses):
        raise RuntimeError("statuses.json must list new, in_progress, resolved, closed in order")
    if any(not isinstance(item.get("title"), str) or not item["title"].strip()
           or len(item["title"].encode("utf-16-le")) // 2 > 40
           for item in status_list):
        raise RuntimeError("Every status needs a non-empty title of at most 40 UTF-16 units")
    if any("initial" in item and not isinstance(item["initial"], bool) for item in status_list):
        raise RuntimeError("Status initial markers must be booleans")
    if sum(item.get("initial", False) for item in status_list) != 1 or not status_list[0].get("initial"):
        raise RuntimeError("The new status must be the only initial status")

    assignments = responders.get("assignments")
    if not isinstance(assignments, list):
        raise RuntimeError("responders.json must contain an assignments array")
    assigned_houses: set[str] = set()
    for assignment in assignments:
        ids = assignment.get("telegram_user_ids") if isinstance(assignment, dict) else None
        house_id = assignment.get("house_id") if isinstance(assignment, dict) else None
        if (not isinstance(house_id, str) or house_id not in house_ids
                or house_id in assigned_houses or not isinstance(ids, list)):
            raise RuntimeError("Responder assignments must reference unique configured house IDs")
        if not all(isinstance(value, int) and value > 0 for value in ids):
            raise RuntimeError(f"Responder IDs for {house_id} must be positive integers")
        assigned_houses.add(house_id)

    return {"houses": houses, "classification": classification,
            "statuses": statuses, "responders": responders}
