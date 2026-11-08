from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from .security import validate_provider_base_url

PRESETS = {
    "Groq": "https://api.groq.com/openai/v1",
    "OpenAI": "https://api.openai.com/v1",
    "DeepSeek": "https://api.deepseek.com",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Custom OpenAI-compatible": "",
}
MAX_MODELS_RESPONSE_BYTES = 2_000_000


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str


def make_client(provider: Provider):
    if not provider.api_key:
        raise ValueError("أضف مفتاح API لهذا المزود من الإعدادات.")
    base_url = validate_provider_base_url(provider.base_url)

    # Import lazily so local utilities and security tests do not require the SDK
    # unless an actual chat completion is requested.
    from openai import OpenAI

    return OpenAI(
        api_key=provider.api_key, base_url=base_url, timeout=60, max_retries=1
    )


def chat_completion(provider: Provider, messages, tools=None, temperature=0.2):
    client = make_client(provider)
    kwargs = {"model": provider.model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def list_models(provider: Provider) -> list[str]:
    if not provider.api_key:
        raise ValueError("أضف مفتاح API لهذا المزود من الإعدادات.")

    # Validate before constructing the request: never transmit an API key to an
    # HTTP endpoint, a URL containing credentials, or a URL with hidden params.
    base_url = validate_provider_base_url(provider.base_url)
    url = f"{base_url}/models"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Accept": "application/json",
    }

    try:
        with requests.get(
            url,
            headers=headers,
            timeout=(5, 15),
            allow_redirects=False,
            stream=True,
        ) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("تم رفض إعادة توجيه المزود؛ تحقق من عنوان Base URL.")
            if response.status_code != 200:
                # Avoid displaying arbitrary response bodies in the UI/logs.
                raise ValueError(f"السيرفر رد بكود HTTP {response.status_code}.")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_MODELS_RESPONSE_BYTES:
                    raise ValueError("قائمة الموديلات أكبر من الحد المسموح.")
                chunks.append(chunk)
    except requests.RequestException as exc:
        raise ValueError(f"تعذر الاتصال بمزود الموديلات: {exc}") from exc

    try:
        data = json.loads(b"".join(chunks))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("استجابة قائمة الموديلات ليست JSON صالحًا.") from exc

    items = data.get("data", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        raise ValueError("تنسيق قائمة الموديلات غير صالح.")
    return sorted(
        {
            item["id"]
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
        }
    )
