from __future__ import annotations
import os
try:
    import keyring
except Exception:
    keyring = None

SERVICE = "Mas3edyPersonalAssistant"

def set_secret(name: str, value: str) -> str:
    if not value:
        delete_secret(name)
        return "removed"
    if keyring:
        try:
            keyring.set_password(SERVICE, name, value)
            return "keyring"
        except Exception:
            pass
    # Deliberately do not write secrets to JSON. Session/env only fallback.
    os.environ[f"MAS3EDY_{name.upper()}"] = value
    return "session"

def get_secret(name: str) -> str | None:
    env = os.environ.get(f"MAS3EDY_{name.upper()}")
    if env:
        return env
    if keyring:
        try:
            return keyring.get_password(SERVICE, name)
        except Exception:
            return None
    return None

def delete_secret(name: str) -> None:
    os.environ.pop(f"MAS3EDY_{name.upper()}", None)
    if keyring:
        try:
            keyring.delete_password(SERVICE, name)
        except Exception:
            pass
