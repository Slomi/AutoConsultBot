# Контекст проекта

Демо-бот №2 для портфолио фрилансера: AI-консультант автосервиса «Поршень». Демо №1 (запись в барбершоп) лежит в `../1`.

## Устройство
Python 3.11, aiogram 3, SQLite, GigaChat.
- `consultant.py` — промпт, отбор разделов базы, разбор меток `[NO_ANSWER] [LEAD] [HUMAN]` в ответе LLM, история диалога (в памяти)
- `llm.py` — провайдеры: `gigachat` (SDK, ключ из `GIGACHAT_*` в `.env`) и `openai` (любой OpenAI-совместимый)
- `handlers/client.py` — вопросы к AI, заявка (FSM), «позвать мастера» (режим human на 30 мин)
- `handlers/admin.py` — ответ клиенту через Reply на уведомление, `/admin`: статистика, без ответа, заявки, редактор базы
- `kb_seed.md` — стартовая база, грузится, если таблица `kb` пустая
- `certs/` — корневой сертификат Минцифры для TLS до GigaChat (TLS-проверку не отключаем)

## Статус
- [x] Код, офлайн-тесты логики с фейковой LLM
- [x] Живой тест: @AutoConsult_tBot, GigaChat-2-Pro, eval 10/10 (`eval_questions.py`)
- [x] Демо-видео: `media/autoconsult_demo.mp4` (Remotion, см. ниже)
- [x] GitHub: github.com/Slomi/AutoConsultBot (публичный)

## Демо-ролик (`video/`)
Без записи экрана и второго аккаунта:
1. `.venv\Scripts\python video\gen_script.py` — прогоняет сценарий через настоящие обработчики бота (транспорт Telegram подменён), пишет `video/src/data/script.json`
2. `cd video && npx remotion render AutoConsultDemo out/autoconsult_demo.mp4` — таймлайн и длительность считаются из сценария
Подписи к шагам — `CAPTION_RULES` в `video/src/timeline.ts`. Node: `C:\Program Files
odejs` (в PATH сессии его может не быть).
