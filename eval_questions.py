"""Прогон типичных вопросов через LLM: проверка меток и отсутствия выдумок.
Запуск: .venv\Scripts\python eval_questions.py [модель ...]"""
import asyncio, os, sys

import config
import db

config.DB_PATH = db.DB_PATH = "eval.db"
import bot  # noqa: E402
import consultant  # noqa: E402

# (вопрос, ожидаемые метки, слова, которых НЕ должно быть в ответе)
CASES = [
    ("Сколько стоит поменять передние колодки на Skoda Octavia?", set(), []),
    ("а диски вместе с ними?", set(), []),
    ("Можно приехать со своим маслом?", set(), []),
    ("Делаете покраску бампера?", set(), ["да, делаем", "делаем покраск", "покрасим"]),
    ("Ремонтируете Tesla Model 3?", set(), []),
    ("Сколько стоит замена турбины на Audi A6?", {"no"}, []),
    ("Хочу записаться на ТО на завтра", {"lead"}, []),
    ("Стучит подвеска спереди справа, что делать?", set(), []),
    ("Позовите живого мастера, пожалуйста", {"human"}, []),
    ("Какая погода завтра в Москве?", set(), []),
]


async def run(model: str) -> int:
    os.environ["GIGACHAT_MODEL"] = model
    consultant._llm = None
    ok = 0
    for i, (q, exp, banned) in enumerate(CASES):
        uid = 1 if i < 2 else 100 + i  # первые два вопроса — один диалог
        a = await consultant.ask(uid, q)
        got = {k for k, v in (("no", a.no_answer), ("lead", a.lead), ("human", a.human)) if v}
        bad = [w for w in banned if w in a.text.lower()]
        passed = exp <= got and ("no" not in got or "no" in exp) and not bad
        ok += passed
        print(f"{'✓' if passed else '✗'} {q}  метки={sorted(got)} ждали={sorted(exp)} {'ВЫДУМКА ' + str(bad) if bad else ''}")
        if not passed:
            print("    " + a.text[:300].replace("\n", " "))
    for uid in [1] + [100 + i for i in range(len(CASES))]:
        consultant.reset(uid)
    return ok


async def main():
    await db.init()
    await bot.seed_kb()
    for model in sys.argv[1:] or [os.getenv("GIGACHAT_MODEL", "GigaChat-2")]:
        print(f"\n===== {model} =====")
        print(f"итог {await run(model)}/{len(CASES)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        if os.path.exists("eval.db"):
            os.remove("eval.db")
