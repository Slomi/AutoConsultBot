import logging
import re
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove, User
from aiogram.utils.chat_action import ChatActionSender

import config
import consultant
import db
import keyboards as kb
from llm import LLMError
from utils import notify_admins, now

router = Router()
_busy: set[int] = set()  # у кого сейчас генерируется ответ


class Lead(StatesGroup):
    name = State()
    phone = State()
    car = State()
    problem = State()


def _who(user: User) -> str:
    link = f'<a href="tg://user?id={user.id}">{escape(user.full_name)}</a>'
    return f"{link} (@{user.username})" if user.username else link


def _dialog(user_id: int) -> str:
    lines = []
    for m in consultant.transcript(user_id):
        who = "🙋" if m["role"] == "user" else "🤖"
        lines.append(f"{who} {escape(m['content'][:400])}")
    return "\n".join(lines) or "(диалога ещё не было)"


# ---------- Меню ----------

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    consultant.reset(message.from_user.id)
    await db.set_human_until(message.from_user.id, None)
    await message.answer(
        f"Здравствуйте, {escape(message.from_user.first_name)}! 👋\n\n"
        f"Я AI-консультант автосервиса <b>«{config.BUSINESS_NAME}»</b>. Отвечу на вопросы о ценах, сроках, "
        f"гарантии и запчастях в любое время суток.\n\n"
        f"Например:\n"
        f"• «Сколько стоит заменить колодки на Octavia?»\n"
        f"• «Можно приехать со своим маслом?»\n"
        f"• «Стучит подвеска, что делать?»\n\n"
        f"Пишите вопрос 👇",
        reply_markup=kb.main_menu(),
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(StateFilter(None), F.text == kb.MENU_CONTACTS)
async def contacts(message: Message):
    await message.answer(
        f"📍 <b>Автосервис «{config.BUSINESS_NAME}»</b>\n\n"
        f"Адрес: {config.ADDRESS}\nТелефон: {config.PHONE}\nРаботаем {config.HOURS}\n\n"
        f'<a href="{config.MAP_URL}">Открыть на карте</a>',
        disable_web_page_preview=True,
    )


@router.message(StateFilter(None), F.text == kb.MENU_PRICE)
async def price(message: Message):
    sections = [s for s in await db.kb_all() if s["title"].lower().startswith("прайс")]
    if not sections:
        return await answer_ai(message, message.bot, "Какие у вас цены?")
    text = "\n\n".join(f"<b>{escape(s['title'])}</b>\n{escape(s['content'])}" for s in sections)
    await message.answer(text[:4000] + "\n\nСпросите про свою машину — подскажу точнее 🙂")


# ---------- Заявка ----------

async def start_lead(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Lead.name)
    await message.answer("Оформим заявку, мастер перезвонит и подберёт время.\n\nКак к вам обращаться?",
                         reply_markup=kb.cancel_kb())


@router.message(StateFilter(None), F.text == kb.MENU_LEAD)
async def lead_from_menu(message: Message, state: FSMContext):
    await start_lead(message, state)


@router.callback_query(kb.ActionCB.filter(F.action == "lead"))
async def lead_from_button(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await start_lead(cb.message, state)


@router.message(StateFilter(Lead), F.text == kb.CANCEL)
async def lead_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Заявку отменил. Если будут вопросы — пишите 🙂", reply_markup=kb.main_menu())


@router.message(Lead.name, F.text)
async def lead_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip()[:100])
    await state.set_state(Lead.phone)
    await message.answer("Номер телефона для связи — кнопкой ниже или вручную:", reply_markup=kb.phone_kb())


@router.message(Lead.phone, F.contact | F.text)
async def lead_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text.strip()
    if not 10 <= len(re.sub(r"\D", "", phone)) <= 15:
        return await message.answer("Похоже, номер с ошибкой. Пример: +7 900 123-45-67")
    await state.update_data(phone=phone)
    await state.set_state(Lead.car)
    await message.answer("Марка, модель и год машины? Например: «Skoda Octavia 2017»",
                         reply_markup=kb.cancel_kb())


@router.message(Lead.car, F.text)
async def lead_car(message: Message, state: FSMContext):
    await state.update_data(car=message.text.strip()[:100])
    await state.set_state(Lead.problem)
    has_dialog = bool(consultant.transcript(message.from_user.id))
    await message.answer(
        "Коротко опишите, что нужно сделать."
        + ("\nЕсли уже рассказали мне выше — нажмите «Пропустить», мастер увидит переписку." if has_dialog else ""),
        reply_markup=kb.cancel_kb(skip=has_dialog),
    )


@router.message(Lead.problem, F.text)
async def lead_problem(message: Message, state: FSMContext):
    problem = "" if message.text == kb.SKIP else message.text.strip()[:1000]
    data = await state.get_data()
    await state.clear()
    lead_id = await db.add_lead(message.from_user.id, data["name"], data["phone"], data["car"], problem)
    await message.answer(
        "✅ Заявка принята! Мастер перезвонит в течение 15 минут в рабочее время "
        f"({config.HOURS}).\n\nПока можете задавать вопросы здесь.",
        reply_markup=kb.main_menu(),
    )
    await notify_admins(
        message.bot,
        f"📝 <b>Заявка #{lead_id}</b>\n\n"
        f"👤 {escape(data['name'])} — {_who(message.from_user)}\n"
        f"📱 {escape(data['phone'])}\n🚗 {escape(data['car'])}\n"
        f"🔧 {escape(problem) or '(см. переписку)'}\n\n<b>Переписка:</b>\n{_dialog(message.from_user.id)}",
    )


# ---------- Передача мастеру ----------

async def handoff(bot: Bot, user: User, reply_to: Message):
    until = now() + timedelta(minutes=config.HUMAN_MODE_MIN)
    await db.set_human_until(user.id, until.isoformat())
    sent = await notify_admins(
        bot,
        f"🆘 <b>Клиент просит мастера</b>\n{_who(user)}\n\n<b>Переписка:</b>\n{_dialog(user.id)}\n\n"
        f"<i>Ответьте на это сообщение (Reply) — я перешлю ответ клиенту.</i>",
    )
    for m in sent:
        await db.add_handoff(m.chat.id, m.message_id, user.id)
    if not sent:
        await db.set_human_until(user.id, None)
        return await reply_to.answer(f"Сейчас мастер недоступен в чате. Позвоните: {config.PHONE}")
    await reply_to.answer(
        "👨‍🔧 Позвал мастера — он ответит прямо здесь. Всё, что напишете дальше, я передам ему.",
        reply_markup=kb.back_to_ai_kb(),
    )


@router.message(StateFilter(None), F.text == kb.MENU_HUMAN)
async def human_from_menu(message: Message):
    await handoff(message.bot, message.from_user, message)


@router.callback_query(kb.ActionCB.filter(F.action == "human"))
async def human_from_button(cb: CallbackQuery):
    await cb.answer()
    await handoff(cb.bot, cb.from_user, cb.message)


@router.callback_query(kb.ActionCB.filter(F.action == "back_ai"))
async def back_to_ai(cb: CallbackQuery):
    await db.set_human_until(cb.from_user.id, None)
    await cb.answer()
    await cb.message.answer("🤖 Снова на связи консультант. Спрашивайте!", reply_markup=kb.main_menu())


async def in_human_mode(user_id: int) -> bool:
    until = await db.get_human_until(user_id)
    return bool(until) and datetime.fromisoformat(until) > now()


# ---------- Вопросы к AI ----------

async def answer_ai(message: Message, bot: Bot, question: str):
    uid = message.chat.id
    if uid in _busy:
        return await message.answer("Секунду, ещё отвечаю на предыдущий вопрос ⏳")
    _busy.add(uid)
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=uid):
            ans = await consultant.ask(uid, question)
    except LLMError:
        logging.exception("LLM недоступна")
        await db.log_question(uid, question, answered=False)
        return await message.answer(
            "Консультант временно недоступен 😔 Оставьте заявку или позовите мастера — ответим как можно скорее.",
            reply_markup=kb.answer_kb(lead=True, human=True),
        )
    finally:
        _busy.discard(uid)
    await db.log_question(uid, question, answered=not ans.no_answer)
    await message.answer(ans.text or "…", reply_markup=kb.answer_kb(
        lead=ans.lead or ans.no_answer, human=ans.human or ans.no_answer))


@router.message(StateFilter(None), F.text)
async def any_text(message: Message, bot: Bot):
    if await in_human_mode(message.from_user.id):
        consultant.remember(message.from_user.id, "user", message.text)
        sent = await notify_admins(bot, f"💬 {_who(message.from_user)}:\n{escape(message.text)}\n\n"
                                        f"<i>Reply — чтобы ответить</i>")
        for m in sent:
            await db.add_handoff(m.chat.id, m.message_id, message.from_user.id)
        return
    await answer_ai(message, bot, message.text.strip()[:2000])


@router.message(StateFilter(None))
async def non_text(message: Message):
    await message.answer("Пока понимаю только текст 🙂 Опишите вопрос словами.")
