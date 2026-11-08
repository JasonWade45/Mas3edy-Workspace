from __future__ import annotations
from dataclasses import dataclass
import requests
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
    if not provider.api_key:
        raise ValueError("أضف مفتاح API لهذا المزود من الإعدادات.")
    
    base_url = provider.base_url.rstrip('/')
    url = f"{base_url}/models"
    
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Accept": "application/json"
    }
    
    response = requests.get(url, headers=headers, timeout=15)
    
    if response.status_code != 200:
        raise ValueError(f"السيرفر رد بكود {response.status_code}: {response.text}")
        
    data = response.json()
    
    # استخراج الموديلات
    models = [m["id"] for m in data.get("data", []) if "id" in m]
    
    if len(models) <= 1:
        print(f"DEBUG: API returned {len(models)} models. Raw response: {data}")
        
    return sorted(models)