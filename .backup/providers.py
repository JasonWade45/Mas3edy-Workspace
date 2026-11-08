from __future__ import annotations
from dataclasses import dataclass
from openai import OpenAI
from secrets_store import get_secret

PRESETS = {
    "Groq": "https://api.groq.com/openai/v1",
    "OpenAI": "https://api.openai.com/v1",
    "DeepSeek": "https://api.deepseek.com",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Custom OpenAI-compatible": ""
}

@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str

def make_client(provider: Provider):
    if not provider.api_key:
        raise ValueError("أضف مفتاح API لهذا المزود من الإعدادات.")
    if not provider.base_url.startswith("https://"):
        raise ValueError("عنوان المزود يجب أن يبدأ بـ HTTPS.")
    return OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=60, max_retries=1)

def chat_completion(provider: Provider, messages, tools=None, temperature=0.2):
    client = make_client(provider)
    kwargs = {"model": provider.model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)

def list_models(provider: Provider):
    client = make_client(provider)
    return sorted(x.id for x in client.models.list().data)
