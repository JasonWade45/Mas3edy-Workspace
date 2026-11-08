from __future__ import annotations

import argparse

from core.providers import Provider, list_models
from core.secrets_store import get_secret
from core.storage import load_config


def main():
    parser = argparse.ArgumentParser(description="عرض موديلات مزود محفوظ في N.O.V.A AI")
    parser.add_argument("--provider", help="اسم المزود المحفوظ")
    args = parser.parse_args()
    cfg = load_config()
    providers = cfg.get("providers", [])
    if not providers:
        print("لا يوجد مزود محفوظ. افتح التطبيق ثم الإعدادات.")
        return
    name = args.provider or cfg.get("active_provider") or providers[0]["name"]
    item = next((p for p in providers if p["name"] == name), None)
    if not item:
        raise SystemExit("المزود غير موجود.")
    provider = Provider(
        name, item["base_url"], get_secret("provider_" + name) or "", item["model"]
    )
    for model in list_models(provider):
        print(model)


if __name__ == "__main__":
    main()
