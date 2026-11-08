from __future__ import annotations

import os

try:
    import keyring
except Exception:  # Keyring may be unavailable on a headless/local system.
    keyring = None

SERVICE = "Mas3edyPersonalAssistant"


def _env_name(name: str) -> str:
    return f"MAS3EDY_{name.upper()}"


def set_secret(name: str, value: str) -> str:
    if not value:
        delete_secret(name)
        return "removed"
    if keyring:
        try:
            keyring.set_password(SERVICE, name, value)
            # Do not let a stale fallback value shadow the newly stored key.
            os.environ.pop(_env_name(name), None)
            return "keyring"
        except Exception:
            pass
    # Deliberately do not write secrets to JSON. The fallback lasts only for
    # the lifetime of this application process.
    os.environ[_env_name(name)] = value
    return "session"


def get_secret(name: str) -> str | None:
    env = os.environ.get(_env_name(name))
    if env:
        return env
    if keyring:
        try:
            return keyring.get_password(SERVICE, name)
        except Exception:
            return None
    return None


def delete_secret(name: str) -> bool:
    os.environ.pop(_env_name(name), None)
    if not keyring:
        return True
    try:
        keyring.delete_password(SERVICE, name)
        return True
    except Exception:
        # Some keyring backends raise when the entry does not exist. Confirm
        # whether the secret remains before reporting a deletion failure.
        try:
            return keyring.get_password(SERVICE, name) is None
        except Exception:
            return False
