import os

from dotenv import load_dotenv

load_dotenv()  # заодно отдаёт GIGACHAT_* в окружение — их читает SDK GigaChat

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
DB_PATH = os.getenv("DB_PATH", "consultant.db")
PROXY = os.getenv("PROXY", "").strip()

# LLM: gigachat | openai (любой OpenAI-совместимый API: OpenRouter, YandexGPT, локальная модель...)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gigachat").strip().lower()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")

MAX_KB_CHARS = 12000        # если база больше — в промпт идут только подходящие разделы
HISTORY_MESSAGES = 12       # сколько последних реплик диалога помнит консультант
HUMAN_MODE_MIN = 30         # сколько минут после «позвать мастера» сообщения идут человеку

# --- Всё, что ниже, меняется под конкретного клиента ---

BUSINESS_NAME = "Поршень"
BUSINESS_KIND = "автосервис"
ADDRESS = "г. Москва, ул. Моторная, 7"
PHONE = "+7 (900) 000-00-00"
HOURS = "ежедневно 9:00–21:00"
MAP_URL = "https://yandex.ru/maps/"
KB_SEED_FILE = "kb_seed.md"  # стартовая база знаний, грузится при первом запуске
