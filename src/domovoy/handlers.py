"""Telegram handlers for resident reports and responder workflows."""

import logging
from typing import Any
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from domovoy.config import Settings, load_validated_configs
from domovoy.presentation import split_telegram_text
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
from domovoy.states import ReportWizard


logger = logging.getLogger(__name__)
router = Router()
STATUS_FLOW = ["new", "in_progress", "resolved", "closed"]
PAGE_SIZE = 10


def _user_values(message: Message) -> tuple[int, str | None, str]:
    user = message.from_user
    assert user is not None
    display_name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    return user.id, user.username, display_name or str(user.id)


def _status_title(configs: dict[str, Any], status_id: str) -> str:
    return next((item["title"] for item in configs["statuses"]["statuses"]
                 if item["id"] == status_id), status_id)


def _location_keyboard(locations: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=item["title"], callback_data=f"loc:{index}")]
        for index, item in enumerate(locations)
    ])


def _category_keyboard(categories: list[dict[str, Any]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=item["title"], callback_data=f"cat:{index}")]
        for index, item in enumerate(categories)
    ])


def _skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="wizard:skip")],
        [InlineKeyboardButton(text="Отменить заявку", callback_data="wizard:cancel")],
    ])


def _cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить заявку", callback_data="wizard:cancel")]
    ])


def _page_keyboard(kind: str, page: int, has_more: bool) -> InlineKeyboardMarkup | None:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="← Новее", callback_data=f"{kind}_page:{page - 1}"))
    if has_more:
        buttons.append(InlineKeyboardButton(text="Старее →", callback_data=f"{kind}_page:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons]) if buttons else None


async def _send_text_chunks(send: Any, text: str) -> None:
    for chunk in split_telegram_text(text):
        await send(chunk)


def _summary(data: dict[str, Any]) -> str:
    lines = [
        f"Дом: {data['address']}",
        f"Место: {data['location_title']}",
        f"Категория: {data['category_title']}",
    ]
    for title, value in data["summary_fields"]:
        lines.append(f"{title}: {value}")
    return "Проверьте заявку перед отправкой:\n\n" + "\n".join(lines)


def _report_text(report: dict[str, Any], configs: dict[str, Any]) -> str:
    location_title = next((item["title"] for item in configs["classification"]["locations"]
                           if item["id"] == report["location_id"]), report["location_id"])
    category_title = next((category["title"] for location in configs["classification"]["locations"]
                          for category in location["categories"]
                          if category["id"] == report["category_id"]), report["category_id"])
    field_titles = {
        field["id"]: field["title"]
        for location in configs["classification"]["locations"]
        for category in location["categories"]
        if category["id"] == report["category_id"]
        for field in category.get("fields", [])
    }
    lines = [
        f"Заявка #{report['id']} · {_status_title(configs, report['status_id'])}",
        f"Дом: {report['address']}",
        f"Место: {location_title}",
        f"Категория: {category_title}",
    ]
    if report.get("description"):
        lines.append(f"Описание: {report['description']}")
    for key, value in report["fields"].items():
        lines.append(f"{field_titles.get(key, key)}: {value}")
    history = report.get("history", [])
    if history:
        lines.extend(["", "История:"])
        for item in history:
            lines.append(f"{_status_title(configs, item['status_id'])} — {item['created_at']}")
    return "\n".join(lines)


def _report_keyboard(report: dict[str, Any], configs: dict[str, Any], *, admin: bool,
                     responder: bool) -> InlineKeyboardMarkup | None:
    buttons: list[list[InlineKeyboardButton]] = []
    current = report["status_id"]
    if admin:
        for status in STATUS_FLOW:
            if status != current:
                buttons.append([InlineKeyboardButton(
                    text=f"Статус: {_status_title(configs, status)}",
                    callback_data=f"status:{report['id']}:{status}"
                )])
    elif responder and current in STATUS_FLOW and current != "closed":
        next_status = STATUS_FLOW[STATUS_FLOW.index(current) + 1]
        buttons.append([InlineKeyboardButton(
            text=f"Изменить статус: {_status_title(configs, next_status)}",
            callback_data=f"status:{report['id']}:{next_status}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def _role_houses(user_id: int, configs: dict[str, Any]) -> list[str]:
    return [item["house_id"] for item in configs["responders"]["assignments"]
            if user_id in item["telegram_user_ids"]]


async def _notify_responders(message: Message, report_id: int, report_text: str,
                             house_id: str, configs: dict[str, Any]) -> None:
    responder_ids = next((item["telegram_user_ids"]
                          for item in configs["responders"]["assignments"]
                          if item["house_id"] == house_id), [])
    for user_id in responder_ids:
        try:
            await _send_text_chunks(
                lambda chunk: message.bot.send_message(
                    user_id, f"Новая заявка #{report_id}\n\n" + chunk
                ),
                report_text,
            )
        except Exception:
            logger.exception("Could not notify responder %s about report %s", user_id, report_id)


async def _begin_report(message: Message, state: FSMContext, settings: Settings,
                        house: dict[str, Any], configs: dict[str, Any]) -> None:
    user_id, username, display_name = _user_values(message)
    user = ensure_user(settings.database_path, user_id, username, display_name)
    await state.clear()
    await state.update_data(
        house_id=house["house_id"], address=house["address"],
        source_chat_id=house["telegram_chat_id"], profile={"section": None, "floor": None, "apartment": None},
        submission_token=str(uuid4()),
    )
    if not user["profile_prompted"]:
        await state.set_state(ReportWizard.profile_section)
        await message.answer("Укажите секцию. Это поле можно пропустить.", reply_markup=_skip_keyboard())
    else:
        await _prompt_location(message, state, configs)


async def _prompt_location(message: Message, state: FSMContext,
                           configs: dict[str, Any]) -> None:
    await state.set_state(ReportWizard.choose_location)
    await message.answer("Выберите место:", reply_markup=_location_keyboard(
        configs["classification"]["locations"]
    ))


@router.message(Command("report"))
async def start_report_from_group(message: Message, state: FSMContext,
                                  settings: Settings) -> None:
    if message.chat.type == "private":
        await message.answer("Начните создание заявки из группового чата вашего дома.")
        return
    configs = load_validated_configs()
    house = next((item for item in configs["houses"]["chats"]
                  if item["telegram_chat_id"] == message.chat.id), None)
    if house is None:
        await message.answer("Этот групповой чат ещё не настроен для создания заявок.")
        return
    bot_user = await message.bot.get_me()
    deep_link = f"https://t.me/{bot_user.username}?start=report_{message.chat.id}"
    await message.answer(
        "Чтобы создать заявку, перейдите в личный чат с ботом:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Создать заявку", url=deep_link)
        ]]),
    )


@router.message(CommandStart())
async def start_private_chat(message: Message, state: FSMContext,
                             settings: Settings) -> None:
    if message.from_user is None:
        return
    if message.chat.type != "private":
        return
    user_id, username, display_name = _user_values(message)
    ensure_user(settings.database_path, user_id, username, display_name)
    payload = (message.text or "").partition(" ")[2]
    role_note = " Вы администратор проекта." if user_id == settings.admin_telegram_id else ""
    if payload.startswith("report_"):
        try:
            source_chat_id = int(payload.removeprefix("report_"))
        except ValueError:
            source_chat_id = None
        configs = load_validated_configs()
        house = next((item for item in configs["houses"]["chats"]
                      if item["telegram_chat_id"] == source_chat_id), None)
        if house is None:
            await message.answer("Не удалось определить дом. Запустите заявку из чата дома.")
            return
        await _begin_report(message, state, settings, house, configs)
        return
    await state.clear()
    await message.answer(
        "Добро пожаловать в Домовой. Чтобы создать заявку, используйте /report "
        "в групповом чате своего дома." + role_note
    )


@router.message(Command("cancel"))
async def cancel_wizard(message: Message, state: FSMContext) -> None:
    if await state.get_state() is not None:
        await state.clear()
        await message.answer("Создание заявки отменено.")


@router.callback_query(F.data == "wizard:cancel")
async def cancel_wizard_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.edit_text("Создание заявки отменено.")
    await callback.answer()


@router.message(ReportWizard.profile_section)
async def collect_section(message: Message, state: FSMContext) -> None:
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        await message.answer("Ответьте на вопрос или используйте /cancel для отмены.")
        return
    await state.update_data(profile_section=message.text or "")
    await state.set_state(ReportWizard.profile_floor)
    await message.answer("Укажите этаж или пропустите.", reply_markup=_skip_keyboard())


@router.message(ReportWizard.profile_floor)
async def collect_floor(message: Message, state: FSMContext) -> None:
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        await message.answer("Ответьте на вопрос или используйте /cancel для отмены.")
        return
    await state.update_data(profile_floor=message.text or "")
    await state.set_state(ReportWizard.profile_apartment)
    await message.answer("Укажите квартиру или пропустите.", reply_markup=_skip_keyboard())


@router.message(ReportWizard.profile_apartment)
async def collect_apartment(message: Message, state: FSMContext,
                            settings: Settings) -> None:
    if message.chat.type != "private":
        return
    if message.text and message.text.startswith("/"):
        await message.answer("Ответьте на вопрос или используйте /cancel для отмены.")
        return
    data = await state.get_data()
    profile = {
        "section": data.get("profile_section") or None,
        "floor": data.get("profile_floor") or None,
        "apartment": message.text or None,
    }
    save_profile(settings.database_path, message.from_user.id, profile)
    await state.update_data(profile=profile)
    configs = load_validated_configs()
    await _prompt_location(message, state, configs)


@router.callback_query(F.data == "wizard:skip")
async def skip_optional_step(callback: CallbackQuery, state: FSMContext,
                            settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    current = await state.get_state()
    data = await state.get_data()
    if current == ReportWizard.profile_section.state:
        await state.update_data(profile_section="")
        await state.set_state(ReportWizard.profile_floor)
        text = "Укажите этаж или пропустите."
        markup = _skip_keyboard()
    elif current == ReportWizard.profile_floor.state:
        await state.update_data(profile_floor="")
        await state.set_state(ReportWizard.profile_apartment)
        text = "Укажите квартиру или пропустите."
        markup = _skip_keyboard()
    elif current == ReportWizard.profile_apartment.state:
        profile = {"section": data.get("profile_section") or None,
                   "floor": data.get("profile_floor") or None, "apartment": None}
        save_profile(settings.database_path, callback.from_user.id, profile)
        await state.update_data(profile=profile)
        configs = load_validated_configs()
        await state.set_state(ReportWizard.choose_location)
        text = "Выберите место:"
        markup = _location_keyboard(configs["classification"]["locations"])
    elif current == ReportWizard.collect_field.state:
        field = data["category"]["fields"][data["field_index"]]
        if field.get("required", False):
            await callback.answer("Это поле обязательно для заполнения.", show_alert=True)
            return
        await _advance_field(callback.message, state, skipped=True)
        text = "Поле пропущено."
        markup = None
    else:
        await callback.answer("На этом шаге пропуск недоступен.", show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def _advance_field(message: Message, state: FSMContext,
                         skipped: bool = False, value: str | None = None) -> None:
    data = await state.get_data()
    category = data["category"]
    fields = category.get("fields", [])
    index = data["field_index"]
    field = fields[index]
    if not skipped:
        await state.update_data(**{f"field_{field['id']}": value})
    next_index = index + 1
    if next_index < len(fields):
        next_field = fields[next_index]
        await state.update_data(field_index=next_index)
        await state.set_state(ReportWizard.collect_field)
        markup = _skip_keyboard() if not next_field.get("required", False) else _cancel_keyboard()
        await message.answer(next_field["title"], reply_markup=markup)
        return
    fresh = await state.get_data()
    summary_fields: list[tuple[str, str]] = []
    values: dict[str, str] = {}
    description = ""
    for item in fields:
        field_value = fresh.get(f"field_{item['id']}")
        if not field_value:
            continue
        summary_fields.append((item["title"], field_value))
        values[item["id"]] = field_value
        if item["id"] == "description":
            description = field_value
    if not description:
        description = "Заявка без описания"
    await state.update_data(fields=values, description=description,
                            summary_fields=summary_fields)
    await state.set_state(ReportWizard.confirm)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить заявку", callback_data="wizard:confirm")],
        [InlineKeyboardButton(text="Отменить", callback_data="wizard:cancel")],
    ])
    await _send_text_chunks(message.answer, _summary(await state.get_data()))
    await message.answer("Подтвердите отправку заявки:", reply_markup=markup)


@router.callback_query(ReportWizard.choose_location, F.data.startswith("loc:"))
async def choose_location(callback: CallbackQuery, state: FSMContext) -> None:
    configs = load_validated_configs()
    try:
        index = int(callback.data.split(":", 1)[1])
        location = configs["classification"]["locations"][index]
    except (ValueError, IndexError, KeyError):
        await callback.answer("Список изменился. Начните заявку заново.", show_alert=True)
        return
    if not location["categories"]:
        await callback.answer("Для этого места пока нет категорий.", show_alert=True)
        return
    await state.update_data(location_id=location["id"], location_title=location["title"],
                            categories=location["categories"])
    await state.set_state(ReportWizard.choose_category)
    if callback.message:
        await callback.message.edit_text("Выберите категорию:",
                                          reply_markup=_category_keyboard(location["categories"]))
    await callback.answer()


@router.callback_query(ReportWizard.choose_category, F.data.startswith("cat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        index = int(callback.data.split(":", 1)[1])
        category = data["categories"][index]
    except (ValueError, IndexError, KeyError):
        await callback.answer("Список изменился. Начните заявку заново.", show_alert=True)
        return
    fields = list(category.get("fields", []))
    if not any(field["id"] == "description" for field in fields):
        fields.append({"id": "description", "title": "Опишите проблему", "type": "text",
                       "required": True})
    if not fields:
        fields = [{"id": "description", "title": "Опишите проблему", "type": "text",
                   "required": True}]
    await state.update_data(category_id=category["id"], category_title=category["title"],
                            category={**category, "fields": fields}, field_index=0)
    await state.set_state(ReportWizard.collect_field)
    field = fields[0]
    markup = _skip_keyboard() if not field.get("required", False) else _cancel_keyboard()
    if callback.message:
        await callback.message.edit_text(field["title"], reply_markup=markup)
    await callback.answer()


@router.message(ReportWizard.collect_field)
async def collect_report_field(message: Message, state: FSMContext,
                               settings: Settings) -> None:
    if message.chat.type != "private" or not message.text:
        await message.answer("Отправьте текстовый ответ.")
        return
    if message.text.startswith("/"):
        await message.answer("Ответьте на вопрос или используйте /cancel для отмены.")
        return
    value = message.text.strip()
    if not value:
        await message.answer("Ответ не должен быть пустым.")
        return
    await _advance_field(message, state, value=value)


@router.callback_query(ReportWizard.confirm, F.data == "wizard:confirm")
async def confirm_report(callback: CallbackQuery, state: FSMContext,
                         settings: Settings) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    try:
        report_id = create_report(
            settings.database_path, house_id=data["house_id"],
            author_id=callback.from_user.id, address=data["address"],
            location_id=data["location_id"], category_id=data["category_id"],
            description=data["description"], fields=data["fields"],
            submission_token=data["submission_token"],
        )
    except Exception:
        logger.exception("Could not save report for Telegram user %s", callback.from_user.id)
        await callback.answer("Не удалось сохранить заявку. Попробуйте позже.", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    try:
        await callback.message.edit_text(f"Заявка #{report_id} отправлена. Спасибо!")
    except TelegramBadRequest:
        logger.exception("Could not update confirmation message for report %s", report_id)
        try:
            await callback.message.answer(f"Заявка #{report_id} отправлена. Спасибо!")
        except Exception:
            logger.exception("Could not send report success message for report %s", report_id)
    configs = load_validated_configs()
    report = get_report_for_responder(settings.database_path, report_id)
    if report:
        await _notify_responders(callback.message, report_id, _report_text(report, configs),
                                 report["house_id"], configs)


def _short_text(text: str, limit: int = 600) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


async def _show_resident_page(message: Message, settings: Settings,
                             user_id: int, page: int) -> None:
    if page < 0 or page > 100_000:
        await message.answer("Некорректный номер страницы.")
        return
    reports, has_more = list_resident_reports(
        settings.database_path, user_id, limit=PAGE_SIZE,
        offset=page * PAGE_SIZE,
    )
    if not reports:
        await message.answer("У вас пока нет заявок." if page == 0 else "На этой странице заявок нет.")
        return
    configs = load_validated_configs()
    for report in reports:
        await message.answer(
            _short_text(
                f"#{report['id']} · {_status_title(configs, report['status_id'])} · "
                f"{report['address']}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Подробности", callback_data=f"resident:{report['id']}")
            ]]),
        )
    keyboard = _page_keyboard("resident", page, has_more)
    if keyboard:
        await message.answer(f"Заявки · страница {page + 1}", reply_markup=keyboard)


@router.message(Command("my_reports"))
async def my_reports(message: Message, settings: Settings) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    await _show_resident_page(message, settings, message.from_user.id, 0)


@router.callback_query(F.data.startswith("resident_page:"))
async def resident_reports_page(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Откройте список в личном чате с ботом.", show_alert=True)
        return
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный номер страницы.", show_alert=True)
        return
    await callback.answer()
    await _show_resident_page(callback.message, settings, callback.from_user.id, page)


@router.callback_query(F.data.startswith("resident:"))
async def resident_report_details(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Откройте заявку в личном чате с ботом.", show_alert=True)
        return
    try:
        report_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный номер заявки.", show_alert=True)
        return
    report = get_report_for_resident(settings.database_path, report_id, callback.from_user.id)
    if report is None:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return
    configs = load_validated_configs()
    await callback.answer()
    await _send_text_chunks(callback.message.answer, _report_text(report, configs))


async def _show_responder_page(message: Message, settings: Settings, actor_id: int,
                               configs: dict[str, Any], page: int) -> None:
    if page < 0 or page > 100_000:
        await message.answer("Некорректный номер страницы.")
        return
    admin = actor_id == settings.admin_telegram_id
    houses = None if admin else _role_houses(actor_id, configs)
    if not admin and not houses:
        await message.answer("У вас нет доступа к обработке заявок.")
        return
    reports, has_more = list_responder_reports(
        settings.database_path, houses, limit=PAGE_SIZE, offset=page * PAGE_SIZE
    )
    if not reports:
        await message.answer("Заявок пока нет." if page == 0 else "На этой странице заявок нет.")
        return
    for report in reports:
        await message.answer(
            _short_text(
                f"#{report['id']} · {_status_title(configs, report['status_id'])} · "
                f"{report['address']}"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Открыть", callback_data=f"responder:{report['id']}")
            ]]),
        )
    keyboard = _page_keyboard("reports", page, has_more)
    if keyboard:
        await message.answer(f"Заявки · страница {page + 1}", reply_markup=keyboard)


@router.message(Command("reports"))
async def responder_reports(message: Message, settings: Settings) -> None:
    if message.from_user is None or message.chat.type != "private":
        return
    await _show_responder_page(message, settings, message.from_user.id,
                               load_validated_configs(), 0)


@router.callback_query(F.data.startswith("reports_page:"))
async def responder_reports_page(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Откройте список в личном чате с ботом.", show_alert=True)
        return
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный номер страницы.", show_alert=True)
        return
    await callback.answer()
    await _show_responder_page(callback.message, settings, callback.from_user.id,
                               load_validated_configs(), page)


@router.callback_query(F.data.startswith("responder:"))
async def responder_report_details(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Обрабатывайте заявки в личном чате с ботом.", show_alert=True)
        return
    try:
        report_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректный номер заявки.", show_alert=True)
        return
    configs = load_validated_configs()
    admin = callback.from_user.id == settings.admin_telegram_id
    houses = None if admin else _role_houses(callback.from_user.id, configs)
    report = get_report_for_responder(settings.database_path, report_id, houses)
    if report is None:
        await callback.answer("Заявка недоступна.", show_alert=True)
        return
    await callback.answer()
    await _send_text_chunks(callback.message.answer, _report_text(report, configs))
    action_keyboard = _report_keyboard(report, configs, admin=admin, responder=not admin)
    action_text = f"Заявка #{report_id} · {_status_title(configs, report['status_id'])}"
    await callback.message.answer(action_text, reply_markup=action_keyboard)


@router.callback_query(F.data.startswith("status:"))
async def update_report_status(callback: CallbackQuery, settings: Settings) -> None:
    if callback.message is None or callback.message.chat.type != "private":
        await callback.answer("Обрабатывайте заявки в личном чате с ботом.", show_alert=True)
        return
    try:
        _, report_text_id, status_id = callback.data.split(":", 2)
        report_id = int(report_text_id)
    except ValueError:
        await callback.answer("Некорректный запрос.", show_alert=True)
        return
    if status_id not in STATUS_FLOW:
        await callback.answer("Неизвестный статус.", show_alert=True)
        return
    configs = load_validated_configs()
    admin = callback.from_user.id == settings.admin_telegram_id
    houses = None if admin else _role_houses(callback.from_user.id, configs)
    report = get_report_for_responder(settings.database_path, report_id, houses)
    if report is None:
        await callback.answer("Заявка недоступна.", show_alert=True)
        return
    if not admin:
        current = report["status_id"]
        if current not in STATUS_FLOW or current == "closed" or status_id != STATUS_FLOW[STATUS_FLOW.index(current) + 1]:
            await callback.answer("Можно выбрать только следующий статус.", show_alert=True)
            return
    elif status_id == report["status_id"]:
        await callback.answer("Этот статус уже установлен.")
        return
    if not change_report_status(
            settings.database_path, report_id, status_id, callback.from_user.id,
            expected_status=report["status_id"]):
        await callback.answer(
            "Заявку уже изменили. Откройте её заново и проверьте текущий статус.",
            show_alert=True,
        )
        return
    await callback.answer("Статус обновлён.")
    updated = get_report_for_responder(settings.database_path, report_id)
    if updated:
        control_text = f"Заявка #{report_id} · {_status_title(configs, updated['status_id'])}"
        keyboard = _report_keyboard(updated, configs, admin=admin, responder=not admin)
        try:
            await callback.message.edit_text(control_text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).lower():
                logger.exception("Could not refresh status controls for report %s", report_id)
                try:
                    await callback.message.answer(control_text, reply_markup=keyboard)
                except Exception:
                    logger.exception("Could not resend status controls for report %s", report_id)
    try:
        await callback.bot.send_message(
            report["author_telegram_user_id"],
            f"Статус вашей заявки #{report_id} изменён: {_status_title(configs, status_id)}.",
        )
    except Exception:
        logger.exception("Could not notify resident about status change for report %s", report_id)
