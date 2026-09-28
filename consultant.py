"""Мозг консультанта: ответ по базе знаний с учётом истории + отдельная разметка (ответил / заявка / нужен человек)."""
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from html import escape

import config
import db
from llm import make_llm

FLAG_RE = re.compile(r"\[(NO_ANSWER|LEAD|HUMAN)\]")  # на случай, если модель всё же напишет метку
WORD_RE = re.compile(r"[а-яёa-z0-9]{3,}")

SYSTEM_PROMPT = """Ты — консультант {kind}а «{name}» в Telegram. Отвечай по-русски, на «вы», дружелюбно и коротко: 2–6 предложений.

Правила:
1. Используй ТОЛЬКО факты из базы знаний ниже. Не выдумывай цены, сроки, акции, адреса и услуги. Если услуги нет в прайсе — НЕ говори, что мы её делаем.
2. Цены называй так же, как в базе («от 900 ₽»). Уточняй, что точная стоимость зависит от машины и определяется после осмотра, если это так.
3. Если сведений в базе нет — честно скажи, что это уточнит мастер, и предложи оставить заявку или позвать мастера.
4. Если клиент хочет приехать или записаться — предложи оформить заявку кнопкой «📝 Оставить заявку» под ответом.
5. Если клиент просит мастера или живого человека — не обещай, что уже позвал, и не выдумывай, чем заняты мастера. Скажи, что по кнопке «👨‍🔧 Позвать мастера» мастер ответит ему прямо здесь.
6. Не упоминай «базу знаний». Не используй markdown-заголовки. Списки — через «•».
7. На вопросы не про автомобили и сервис вежливо отвечай, что ты консультант автосервиса, и предлагай помощь по теме.

База знаний:
{kb}"""

CLASSIFY_PROMPT = """Ты размечаешь переписку клиента с консультантом автосервиса. Верни ТОЛЬКО JSON, без пояснений:
{{"answered": true|false, "lead": true|false, "human": true|false}}

answered=false — консультант НЕ дал ответа по существу: сказал, что не знает, что это уточнит мастер, или не назвал ни цены, ни факта.
answered=true — назвал цену, срок, условие, факт или чётко сказал «делаем» / «не делаем». Вежливый отказ от оффтопа — тоже true.
lead=true — клиент хочет записаться, приехать, оставить заявку или явно собирается ремонтировать машину.
human=true — клиент просит живого человека, мастера, менеджера, оператора, или недоволен.

Клиент: {question}
Консультант: {answer}"""

JSON_RE = re.compile(r"\{.*?\}", re.S)
HUMAN_RE = re.compile(r"(живо|человек|оператор|менеджер|позов\w* мастер|мастера позов|с мастером)", re.I)


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
    clean = FLAG_RE.sub("", raw).strip()
    answered, lead, human = await classify(question, clean)
    if human:
        answered = True  # просьба позвать человека — не пробел в базе знаний

    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": clean})
    return Answer(to_html(clean), not answered, lead, human)


async def classify(question: str, answer: str) -> tuple[bool, bool, bool]:
    """(answered, lead, human). Если разметка не удалась — считаем, что ответ дан, и смотрим ключевые слова."""
    fallback_human = bool(HUMAN_RE.search(question))
    try:
        raw = await llm().complete([{"role": "user", "content": CLASSIFY_PROMPT.format(
            question=question[:1000], answer=answer[:1500])}])
        data = json.loads(JSON_RE.search(raw).group())
        return bool(data.get("answered", True)), bool(data.get("lead")), bool(data.get("human")) or fallback_human
    except Exception:
        return True, False, fallback_human


def remember(user_id: int, role: str, content: str) -> None:
    """Реплики вне AI (ответ мастера и т.п.) — чтобы консультант знал контекст."""
    _history[user_id].append({"role": role, "content": content})
