from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlsplit

# These paths commonly contain credentials or private keys. Keep this check in
# resolve_inside so it applies to reads, writes, moves, and renames alike.
SENSITIVE_NAMES = {
    ".env",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".config",
    ".git",
    ".kube",
    ".docker",
    ".npmrc",
    ".pypirc",
    ".netrc",
    ".git-credentials",
    ".pgpass",
    ".my.cnf",
}
SENSITIVE_FILES = {
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "credentials",
    "secrets.json",
    "secret.json",
    "token",
    "tokens.json",
    "auth.json",
    "authorized_keys",
    "cookies.txt",
    "cookies.sqlite",
}
SENSITIVE_PREFIXES = (
    "credentials.",
    "credential.",
    "secret.",
    "secrets.",
    "token.",
    "client_secret.",
    "service-account.",
    "service_account.",
    "private_key.",
)
PRIVATE_KEY_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".p8", ".jks"}

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
}
TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".json",
    ".md",
    ".mdx",
    ".txt",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".cs",
    ".php",
    ".go",
    ".rs",
    ".sql",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".bat",
    ".sh",
    ".xml",
    ".gs",
    ".log",
    ".csv",
    ".ipynb",
    ".rst",
    ".svg",
}
TEXT_FILE_NAMES = {"dockerfile", "makefile", "justfile", "procfile", "license"}


def is_sensitive(path: str | Path) -> bool:
    path = Path(path)
    parts = [part.casefold() for part in path.parts]

    for part in parts:
        # Example templates are intentionally allowed; real .env variants are not.
        if part == ".env.example":
            continue
        if part in SENSITIVE_NAMES or part.startswith(".env"):
            return True

    name = path.name.casefold()
    if name in SENSITIVE_FILES or name.startswith(SENSITIVE_PREFIXES):
        return True
    return Path(name).suffix in PRIVATE_KEY_SUFFIXES


def is_text_path(path: str | Path) -> bool:
    path = Path(path)
    name = path.name.casefold()
    return (
        name == ".env.example"
        or name in TEXT_FILE_NAMES
        or path.suffix.casefold() in TEXT_EXTENSIONS
    )


def resolve_inside(
    root: str | Path, relative: str, *, allow_missing: bool = True
) -> Path:
    base = Path(root).expanduser().resolve(strict=True)
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        raise ValueError("المسار لازم يكون نسبي داخل المجلد المصرّح به.")

    rel = Path(relative)
    if rel.is_absolute():
        raise ValueError("المسار لازم يكون نسبي داخل المجلد المصرّح به.")

    candidate = base / rel
    # Resolve existing ancestors and reject escapes before touching the file.
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError("ممنوع الوصول خارج المجلد المصرّح به.") from exc

    current = base
    for part in rel.parts:
        if part in ("..", "."):
            raise ValueError("المسار غير صالح.")
        current = current / part
        if current.is_symlink():
            raise ValueError("التعامل مع الروابط الرمزية غير مسموح.")

    if is_sensitive(rel):
        raise PermissionError("الوصول إلى ملفات أو مجلدات حساسة ممنوع.")
    if not allow_missing and not resolved.exists():
        raise FileNotFoundError(relative)
    return resolved


def validate_provider_base_url(url: str) -> str:
    """Validate a provider endpoint before an API key can be sent to it."""
    try:
        parsed = urlsplit(url)
        # Accessing .port also validates malformed port values.
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("عنوان المزود غير صالح.") from exc

    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "عنوان المزود يجب أن يكون HTTPS صالحًا ومن دون بيانات دخول أو query/fragment."
        )
    return url.rstrip("/")


def validate_public_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port or 443
    except (TypeError, ValueError) as exc:
        raise ValueError("رابط الموقع غير صالح.") from exc

    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("مسموح بروابط HTTPS فقط، ومن غير بيانات دخول داخل الرابط.")

    host = parsed.hostname
    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise ValueError(f"تعذر حل اسم الموقع: {exc}") from exc

    if not addresses:
        raise ValueError("لم يتم العثور على عنوان للموقع.")
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise ValueError("تم رفض الموقع لأنه يحل إلى عنوان شبكة محلية أو غير عام.")
    return host
