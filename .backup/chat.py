from __future__ import annotations
from storage import load_config
from secrets_store import get_secret
from providers import Provider
from assistant_core import run_assistant

def main():
    cfg = load_config()
    providers = cfg.get("providers", [])
    if not providers:
        print("أضف مزودًا من واجهة التطبيق أولًا.")
        return
    name = cfg.get("active_provider") or providers[0]["name"]
    p = next(x for x in providers if x["name"] == name)
    provider = Provider(name, p["base_url"], get_secret("provider_"+name) or "", p["model"])
    history = []
    print("مساعدي - اكتب exit للخروج")
    while True:
        prompt = input("\nأنت: ").strip()
        if prompt.lower() in {"exit","quit"}: break
        history.append({"role":"user","content":prompt})
        answer, proposals, log = run_assistant(provider, history,
            "أنت مساعد شخصي عملي. أجب بالعربية المصرية عند استخدام العربية. لا تدّع تنفيذ تغييرات الملفات.")
        print("\nمساعدي:", answer)
        if proposals: print("ملاحظة: مقترحات الملفات متاحة داخل واجهة Streamlit فقط.")
        history.append({"role":"assistant","content":answer})

if __name__ == "__main__":
    main()
