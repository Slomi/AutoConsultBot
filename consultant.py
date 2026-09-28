"""Мозг консультанта: собирает промпт из базы знаний и истории, разбирает служебные метки в ответе."""
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from html import escape

import config
import db
from llm import make_llm

FLAG_RE = re.compile(r"\[(NO_ANSWER|LEAD|HUMAN)\]")
WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}")

SYSTEM_PROMPT = """Ты — консультант {kind}а «{name}» в Telegram. Отвечай по-русски, на «вы», дружелюбно и коротко: 2–6 предложений.

Правила:
1. Используй ТОЛЬКО факты из базы знаний ниже. Не выдумывай цены, сроки, акции, адреса и услуги.
2. Цены называй так же, как в базе («от 900 ₽»). Уточняй, что точная стоимость зависит от машины и определяется после осмотра, если это так.
3. Если ответа в базе нет — честно скажи, что это уточнит мастер, предложи оставить заявку или позвать мастера, и добавь в конце метку [NO_ANSWER].
4. Если клиент хочет записаться, приехать, оставить заявку или спрашивает «когда можно приехать» — предложи оформить заявку и добавь в конце метку [LEAD].
5. Если клиент просит живого человека, мастера, менеджера, или недоволен — добавь в конце метку [HUMAN].
6. Метки пиши в квадратных скобках в самом конце, текст метки клиенту не объясняй. Не упоминай «базу знаний».
7. Не используй markdown-заголовки. Списки — через «•».
8. На вопросы не про автомобили и сервис вежливо отвечай, что ты консультант автосервиса, и предлагай помощь по теме.

База знаний:
{kb}"""


@dataclass
class Answer:
    text: str          # уже в HTML
    no_answer: bool
    lead: bool
    human: bool


_llm = None
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=config.HISTORY_MESSAGES))


def llm():
    global _llm
    if _llm is None:
        _llm = make_llm()
    return _llm


def reset(user_id: int) -> None:
    _history.pop(user_id, None)


def transcript(user_id: int, last: int = 10) -> list[dict]:
    return list(_history[user_id])[-last:]


def _stems(text: str) -> set[str]:
    return {w[:5] for w in WORD_RE.findall(text.lower())}


def select_sections(sections, query: str) -> list:
    """Вся база, если она небольшая; иначе — разделы с наибольшим пересечением слов с вопросом."""
    if sum(len(s["title"]) + len(s["content"]) for s in sections) <= config.MAX_KB_CHARS:
        return sections
    q = _stems(query)
    ranked = sorted(sections, key=lambda s: -len(q & _stems(s["title"] + " " + s["content"])))
    picked, size = [], 0
    for s in ranked:
        n = len(s["title"]) + len(s["content"])
        if size + n > config.MAX_KB_CHARS:
            continue
        picked.append(s); size += n
    return sorted(picked, key=lambda s: s["id"])


def to_html(text: str) -> str:
    text = escape(text.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?m)^#+\s*", "", text)
    return text.replace("*", "")


async def ask(user_id: int, question: str) -> Answer:
    history = _history[user_id]
    recent_user = " ".join(m["content"] for m in history if m["role"] == "user")
    sections = select_sections(await db.kb_all(), f"{recent_user} {question}")
    kb_text = "\n\n".join(f"### {s['title']}\n{s['content']}" for s in sections) or "(база пуста)"

    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(
        kind=config.BUSINESS_KIND, name=config.BUSINESS_NAME, kb=kb_text)}]
    messages += list(history)
    messages.append({"role": "user", "content": question})

    raw = await llm().complete(messages)
    flags = set(FLAG_RE.findall(raw))
    clean = FLAG_RE.sub("", raw).strip()

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": clean})
    return Answer(to_html(clean), "NO_ANSWER" in flags, "LEAD" in flags, "HUMAN" in flags)


def remember(user_id: int, role: str, content: str) -> None:
    """Реплики вне AI (ответ мастера и т.п.) — чтобы консультант знал контекст."""
    _history[user_id].append({"role": role, "content": content})
