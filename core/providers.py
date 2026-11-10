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
# نماذج موصى بها مبدئيًا لكل مزود شائع (تُعطى علامة ★ إن وُجدت في القائمة).
PRESET_RECOMMENDED = {
    "Groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "OpenAI": ["gpt-4o-mini", "gpt-4o"],
    "DeepSeek": ["deepseek-chat"],
    "OpenRouter": [],
}
MAX_MODELS_RESPONSE_BYTES = 2_000_000
AUTO_MODEL_OPTION = "تلقائي حسب المهمة"


def recommended_for_provider(provider_name: str) -> list[str]:
    return PRESET_RECOMMENDED.get(provider_name, [])


def context_window_for_model(model: str) -> int:
    """Conservative context-window estimate; used for the usage meter only."""
    name = (model or "").casefold()
    table = (
        ("gpt-4o", 128_000),
        ("gpt-3.5", 16_000),
        ("deepseek", 64_000),
        ("llama-3.1", 128_000),
        ("llama-3.3", 128_000),
        ("kimi", 128_000),
        ("qwen3", 32_000),
        ("allam", 8_000),
    )
    for hint, window in table:
        if hint in name:
            return window
    return 16_000


def model_badge(model: str) -> str:
    """Heuristic quality tiers shown next to model IDs (purely informational)."""
    name = (model or "").casefold()
    badges = []
    if any(hint in name for hint in ("instant", "flash", "mini", "8b", "haiku", "small")):
        badges.append("سريع")
    if any(hint in name for hint in ("70b", "120b", "pro", "opus", "sonnet", "large")):
        badges.append("قوي")
    if name.endswith(":free") or "/free" in name:
        badges.append("مجاني")
    if any(hint in name for hint in ("coder", "code", "devstral")):
        badges.append("كود")
    return " · ".join(badges)


def select_model_for_task(models, prompt, mode="chat", default_model=""):
    """Choose a saved model by role-like name hints; fall back to the user's default."""
    candidates = list(
        dict.fromkeys(model for model in models if isinstance(model, str) and model)
    )
    if not candidates:
        return default_model or ""

    query = str(prompt or "").casefold()
    code_task = mode == "code" or any(
        word in query
        for word in ("code", "python", "debug", "bug", "كود", "برمج", "خطأ", "تصحيح")
    )
    complex_task = len(query) > 700 or any(
        word in query
        for word in ("analyze", "compare", "reason", "حلل", "قارن", "خطة", "استراتيجية")
    )

    if code_task:
        role_hints = ("coder", "coding", "code", "codestral", "devstral")
    elif complex_task:
        role_hints = ("reason", "thinking", "70b", "120b", "pro", "opus", "sonnet")
    else:
        role_hints = ("instant", "flash", "mini", "8b", "haiku", "small")

    selected = next(
        (
            model
            for model in candidates
            if any(hint in model.casefold() for hint in role_hints)
        ),
        None,
    )
    if selected:
        return selected
    return default_model if default_model in candidates else candidates[0]


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    supports_tools: bool | None = None


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
