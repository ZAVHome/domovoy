"""Finite-state steps for the resident report flow."""

from aiogram.fsm.state import State, StatesGroup


class ReportWizard(StatesGroup):
    profile_section = State()
    profile_floor = State()
    profile_apartment = State()
    choose_location = State()
    choose_category = State()
    collect_field = State()
    confirm = State()
