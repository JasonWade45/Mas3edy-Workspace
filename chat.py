from __future__ import annotations

from core.assistant_core import run_assistant
from core.personalization import compose_system_prompt
from core.providers import Provider
from core.secrets_store import get_secret
from core.storage import load_config


def main():
    cfg = load_config()
    providers = cfg.get("providers", [])
    if not providers:
        print("أضف مزودًا من واجهة التطبيق أولًا.")
        return
    name = cfg.get("active_provider") or providers[0]["name"]
    p = next(x for x in providers if x["name"] == name)
    provider = Provider(
        name, p["base_url"], get_secret("provider_" + name) or "", p["model"]
    )
    history = []
    system_prompt = compose_system_prompt(
        "أنت مساعد شخصي عملي. أجب بالعربية المصرية عند استخدام العربية. "
        "لا تدّع تنفيذ تغييرات الملفات.",
        cfg.get("assistant_instructions", "")
        if cfg.get("personalization_enabled", True)
        else "",
    )
    print("مساعدي - اكتب exit للخروج")
    while True:
        prompt = input("\nأنت: ").strip()
        if prompt.lower() in {"exit", "quit"}:
            break
        history.append({"role": "user", "content": prompt})
        answer, proposals, _log = run_assistant(
            provider,
            history,
            system_prompt,
            personalization_enabled=cfg.get("personalization_enabled", True),
        )
        print("\nمساعدي:", answer)
        if proposals:
            print("ملاحظة: مقترحات الملفات متاحة داخل واجهة Streamlit فقط.")
        history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
