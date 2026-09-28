from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU_LEAD = "📝 Записаться на ремонт"
MENU_HUMAN = "👨‍🔧 Позвать мастера"
MENU_PRICE = "💰 Прайс"
MENU_CONTACTS = "📍 Контакты"
CANCEL = "❌ Отмена"
SKIP = "➡️ Пропустить"


class ActionCB(CallbackData, prefix="act"):
    action: str  # lead / human / back_ai


class AdminCB(CallbackData, prefix="adm"):
    action: str  # stats / kb / unanswered / leads / kb_add / kb_upload / kb_download / menu


class KbCB(CallbackData, prefix="kb"):
    action: str  # view / delete / edit / confirm_delete
    id: int


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=MENU_LEAD)],
        [KeyboardButton(text=MENU_PRICE), KeyboardButton(text=MENU_CONTACTS)],
        [KeyboardButton(text=MENU_HUMAN)],
    ], resize_keyboard=True, input_field_placeholder="Задайте вопрос о ремонте или ценах…")


def cancel_kb(skip: bool = False) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=SKIP)]] if skip else []
    rows.append([KeyboardButton(text=CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
        [KeyboardButton(text=CANCEL)],
    ], resize_keyboard=True)


def answer_kb(lead: bool, human: bool) -> InlineKeyboardMarkup | None:
    b = InlineKeyboardBuilder()
    if lead:
        b.button(text="📝 Оставить заявку", callback_data=ActionCB(action="lead"))
    if human:
        b.button(text="👨‍🔧 Позвать мастера", callback_data=ActionCB(action="human"))
    b.adjust(1)
    return b.as_markup() if (lead or human) else None


def back_to_ai_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🤖 Вернуться к консультанту", callback_data=ActionCB(action="back_ai"))
    return b.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data=AdminCB(action="stats"))
    b.button(text="❓ Без ответа", callback_data=AdminCB(action="unanswered"))
    b.button(text="📝 Заявки", callback_data=AdminCB(action="leads"))
    b.button(text="📚 База знаний", callback_data=AdminCB(action="kb"))
    b.adjust(2)
    return b.as_markup()


def _back(b: InlineKeyboardBuilder, to: str = "menu") -> None:
    from aiogram.types import InlineKeyboardButton
    b.row(InlineKeyboardButton(text="« Назад", callback_data=AdminCB(action=to).pack()))


def back_kb(to: str = "menu") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder(); _back(b, to)
    return b.as_markup()


def kb_list_kb(sections) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for s in sections:
        b.button(text=s["title"][:60], callback_data=KbCB(action="view", id=s["id"]))
    b.button(text="➕ Добавить раздел", callback_data=AdminCB(action="kb_add"))
    b.button(text="📥 Загрузить файл", callback_data=AdminCB(action="kb_upload"))
    b.button(text="📤 Скачать базу", callback_data=AdminCB(action="kb_download"))
    b.adjust(*([1] * len(sections)), 1, 2)
    _back(b)
    return b.as_markup()


def kb_section_kb(section_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Заменить текст", callback_data=KbCB(action="edit", id=section_id))
    b.button(text="🗑 Удалить", callback_data=KbCB(action="delete", id=section_id))
    b.adjust(2)
    _back(b, "kb")
    return b.as_markup()


def kb_confirm_delete_kb(section_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да, удалить", callback_data=KbCB(action="confirm_delete", id=section_id))
    b.button(text="Нет", callback_data=KbCB(action="view", id=section_id))
    return b.as_markup()
