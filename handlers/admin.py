from collections import Counter
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

import config
import consultant
import db
import keyboards as kb
from consultant import WORD_RE
from utils import kb_to_markdown, parse_kb_markdown

router = Router()
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))

STOPWORDS = {"как", "что", "это", "для", "где", "когда", "сколько", "можно", "есть", "ваш", "вас", "мне",
             "меня", "нужно", "надо", "стоит", "будет", "или", "если", "под", "при", "про", "так", "уже",
             "здравствуйте", "добрый", "день", "привет", "подскажите", "пожалуйста", "спасибо", "у вас"}


class KbEdit(StatesGroup):
    title = State()
    content = State()
    replace = State()   # новый текст существующего раздела
    upload = State()


# ---------- Ответ клиенту через Reply ----------

async def handoff_target(message: Message) -> dict | bool:
    r = message.reply_to_message
    if not r:
        return False
    uid = await db.handoff_user(message.chat.id, r.message_id)
    return {"target_user": uid} if uid else False


@router.message(handoff_target)
async def relay_to_client(message: Message, target_user: int):
    try:
        await message.bot.send_message(target_user, "👨‍🔧 <b>Мастер:</b>")
        await message.copy_to(target_user)
    except Exception as e:
        return await message.reply(f"Не доставлено: {escape(str(e))}")
    if message.text:
        consultant.remember(target_user, "assistant", f"(ответ мастера) {message.text}")
    await message.reply("✅ Отправлено клиенту")


# ---------- Меню ----------

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔧 <b>Админка консультанта</b>", reply_markup=kb.admin_menu())


@router.callback_query(kb.AdminCB.filter(F.action == "menu"))
async def menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("🔧 <b>Админка консультанта</b>", reply_markup=kb.admin_menu())
    await cb.answer()


@router.callback_query(kb.AdminCB.filter(F.action == "stats"))
async def stats(cb: CallbackQuery):
    lines = ["📊 <b>Статистика</b>"]
    for days, label in ((1, "Сегодня"), (7, "За 7 дней")):
        qs = await db.questions_since(days)
        answered = sum(q["answered"] for q in qs)
        pct = f" ({answered * 100 // len(qs)}% с ответом)" if qs else ""
        lines.append(f"\n<b>{label}</b>\nВопросов: {len(qs)}{pct}\n"
                     f"Заявок: {await db.leads_count_since(days)}\n"
                     f"Звали мастера: {await db.handoffs_count_since(days)}")
    words = Counter(w for q in await db.questions_since(7) for w in WORD_RE.findall(q["text"].lower())
                    if len(w) > 3 and w not in STOPWORDS)
    if words:
        lines.append("\n<b>О чём спрашивают (7 дней):</b>\n" + ", ".join(f"{w} ({n})" for w, n in words.most_common(12)))
    await cb.message.edit_text("\n".join(lines), reply_markup=kb.back_kb())
    await cb.answer()


@router.callback_query(kb.AdminCB.filter(F.action == "unanswered"))
async def unanswered(cb: CallbackQuery):
    qs = [q for q in await db.questions_since(30) if not q["answered"]][:15]
    text = ("❓ <b>Бот не смог ответить (30 дней)</b>\n\n"
            + "\n".join(f"• {q['created_at'][5:16]} — {escape(q['text'][:150])}" for q in qs)
            + "\n\nДобавьте ответы в базу знаний — и бот начнёт отвечать сам.") if qs else "Все вопросы отвечены 👍"
    await cb.message.edit_text(text, reply_markup=kb.back_kb())
    await cb.answer()


@router.callback_query(kb.AdminCB.filter(F.action == "leads"))
async def leads(cb: CallbackQuery):
    rows = await db.leads_last(10)
    text = ("📝 <b>Последние заявки</b>\n\n" + "\n\n".join(
        f"#{r['id']} {r['created_at'][5:16]}\n{escape(r['name'] or '')}, {escape(r['phone'] or '')}\n"
        f"🚗 {escape(r['car'] or '')}\n🔧 {escape((r['problem'] or '(см. переписку)')[:200])}" for r in rows)
    ) if rows else "Заявок пока нет."
    await cb.message.edit_text(text, reply_markup=kb.back_kb())
    await cb.answer()


# ---------- База знаний ----------

async def show_kb(message: Message, edit: bool = True):
    sections = await db.kb_all()
    size = sum(len(s["content"]) for s in sections)
    text = (f"📚 <b>База знаний</b>: {len(sections)} разделов, {size} символов\n\n"
            "Нажмите на раздел, чтобы посмотреть или изменить.")
    if edit:
        await message.edit_text(text, reply_markup=kb.kb_list_kb(sections))
    else:
        await message.answer(text, reply_markup=kb.kb_list_kb(sections))


@router.callback_query(kb.AdminCB.filter(F.action == "kb"))
async def kb_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_kb(cb.message)
    await cb.answer()


@router.callback_query(kb.KbCB.filter(F.action == "view"))
async def kb_view(cb: CallbackQuery, callback_data: kb.KbCB):
    s = await db.kb_get(callback_data.id)
    if not s:
        return await cb.answer("Раздел уже удалён", show_alert=True)
    await cb.message.edit_text(f"<b>{escape(s['title'])}</b>\n\n{escape(s['content'])[:3800]}",
                               reply_markup=kb.kb_section_kb(s["id"]))
    await cb.answer()


@router.callback_query(kb.KbCB.filter(F.action == "delete"))
async def kb_delete(cb: CallbackQuery, callback_data: kb.KbCB):
    s = await db.kb_get(callback_data.id)
    if not s:
        return await cb.answer("Раздел уже удалён", show_alert=True)
    await cb.message.edit_text(f"Удалить раздел «{escape(s['title'])}»?",
                               reply_markup=kb.kb_confirm_delete_kb(s["id"]))
    await cb.answer()


@router.callback_query(kb.KbCB.filter(F.action == "confirm_delete"))
async def kb_confirm_delete(cb: CallbackQuery, callback_data: kb.KbCB):
    await db.kb_delete(callback_data.id)
    await cb.answer("Удалено")
    await show_kb(cb.message)


@router.callback_query(kb.KbCB.filter(F.action == "edit"))
async def kb_edit(cb: CallbackQuery, callback_data: kb.KbCB, state: FSMContext):
    await state.set_state(KbEdit.replace)
    await state.update_data(section_id=callback_data.id)
    await cb.message.answer("Пришлите новый текст раздела одним сообщением. /admin — отмена.")
    await cb.answer()


@router.message(KbEdit.replace, F.text)
async def kb_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.kb_update(data["section_id"], message.text.strip())
    await state.clear()
    await message.answer("✅ Раздел обновлён — бот уже отвечает по новому тексту.")
    await show_kb(message, edit=False)


@router.callback_query(kb.AdminCB.filter(F.action == "kb_add"))
async def kb_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(KbEdit.title)
    await cb.message.answer("Название раздела? Например: «Прайс: кузовной ремонт». /admin — отмена.")
    await cb.answer()


@router.message(KbEdit.title, F.text)
async def kb_add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip()[:100])
    await state.set_state(KbEdit.content)
    await message.answer("Теперь текст раздела одним сообщением: цены, условия, ответы на частые вопросы.")


@router.message(KbEdit.content, F.text)
async def kb_add_content(message: Message, state: FSMContext):
    data = await state.get_data()
    await db.kb_add(data["title"], message.text.strip())
    await state.clear()
    await message.answer(f"✅ Раздел «{escape(data['title'])}» добавлен.")
    await show_kb(message, edit=False)


@router.callback_query(kb.AdminCB.filter(F.action == "kb_upload"))
async def kb_upload(cb: CallbackQuery, state: FSMContext):
    await state.set_state(KbEdit.upload)
    await cb.message.answer(
        "Пришлите файл .md или .txt. Разделы начинаются со строки «## Заголовок».\n"
        "⚠️ Файл <b>заменит всю базу</b>. Текущую можно сначала скачать кнопкой «📤 Скачать базу».\n/admin — отмена.")
    await cb.answer()


@router.message(KbEdit.upload, F.document)
async def kb_upload_file(message: Message, state: FSMContext):
    doc = message.document
    if not (doc.file_name or "").lower().endswith((".md", ".txt")) or doc.file_size > 500_000:
        return await message.answer("Нужен файл .md или .txt до 500 КБ.")
    raw = (await message.bot.download(doc)).read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1251")
    sections = parse_kb_markdown(text)
    if not sections:
        return await message.answer("Не нашёл разделов. Каждый раздел должен начинаться со строки «## Заголовок».")
    await db.kb_replace(sections)
    await state.clear()
    await message.answer(f"✅ База заменена: {len(sections)} разделов.")
    await show_kb(message, edit=False)


@router.callback_query(kb.AdminCB.filter(F.action == "kb_download"))
async def kb_download(cb: CallbackQuery):
    md = kb_to_markdown(await db.kb_all())
    await cb.message.answer_document(BufferedInputFile(md.encode("utf-8"), filename="knowledge_base.md"),
                                     caption="Текущая база знаний. Отредактируйте и загрузите обратно.")
    await cb.answer()
