"""Тонкий слой над LLM: провайдер переключается переменной LLM_PROVIDER в .env."""
import httpx
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

import config

_ROLES = {"system": MessagesRole.SYSTEM, "user": MessagesRole.USER, "assistant": MessagesRole.ASSISTANT}


class LLMError(Exception):
    pass


class GigaChatLLM:
    def __init__(self):
        self._client = GigaChat()  # ключ, scope, модель и сертификат — из GIGACHAT_* в .env

    async def complete(self, messages: list[dict]) -> str:
        chat = Chat(
            messages=[Messages(role=_ROLES[m["role"]], content=m["content"]) for m in messages],
            temperature=0.2,
            max_tokens=700,
        )
        try:
            resp = await self._client.achat(chat)
        except Exception as e:
            raise LLMError(str(e)) from e
        return resp.choices[0].message.content


class OpenAICompatLLM:
    def __init__(self):
        self._http = httpx.AsyncClient(
            base_url=config.OPENAI_BASE_URL,
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            timeout=60,
        )

    async def complete(self, messages: list[dict]) -> str:
        try:
            r = await self._http.post("/chat/completions", json={
                "model": config.OPENAI_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 700,
            })
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise LLMError(str(e)) from e


def make_llm():
    if config.LLM_PROVIDER == "gigachat":
        return GigaChatLLM()
    if config.LLM_PROVIDER == "openai":
        return OpenAICompatLLM()
    raise SystemExit(f"Неизвестный LLM_PROVIDER: {config.LLM_PROVIDER}")
