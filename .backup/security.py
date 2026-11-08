from __future__ import annotations
import ipaddress, socket
from pathlib import Path
from urllib.parse import urlparse

SENSITIVE_NAMES = {".env", ".ssh", ".gnupg", ".aws", ".azure", ".config"}
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md", ".txt",
    ".java", ".c", ".cpp", ".h", ".cs", ".php", ".go", ".rs", ".sql", ".yml",
    ".yaml", ".toml", ".ini", ".bat", ".sh", ".xml", ".gs", ".env.example",
    ".log", ".csv", ".ipynb"
}

def is_sensitive(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return any(p in SENSITIVE_NAMES or p.startswith(".env") for p in parts) or path.name.lower() in {
        "id_rsa", "id_ed25519", "credentials", "secrets.json"
    }

def resolve_inside(root: str | Path, relative: str, *, allow_missing=True) -> Path:
    base = Path(root).expanduser().resolve(strict=True)
    rel = Path(relative)
    if rel.is_absolute() or not relative or "\x00" in relative:
        raise ValueError("المسار لازم يكون نسبي داخل المجلد المصرّح به.")
    candidate = base / rel
    # Resolve existing ancestors; reject symlinks/junction-like escapes.
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(base)
    except ValueError:
        raise ValueError("ممنوع الوصول خارج المجلد المصرّح به.")
    current = base
    for part in rel.parts:
        if part in ("..", "."):
            raise ValueError("المسار غير صالح.")
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError("التعامل مع الروابط الرمزية غير مسموح.")
    if not allow_missing and not resolved.exists():
        raise FileNotFoundError(relative)
    if is_sensitive(rel):
        raise PermissionError("الوصول إلى ملفات أو مجلدات حساسة ممنوع.")
    return resolved

def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("مسموح بروابط HTTPS فقط، ومن غير بيانات دخول داخل الرابط.")
    host = parsed.hostname
    try:
        addresses = {x[4][0] for x in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError(f"تعذر حل اسم الموقع: {exc}")
    if not addresses:
        raise ValueError("لم يتم العثور على عنوان للموقع.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("تم رفض الموقع لأنه يحل إلى عنوان شبكة محلية أو غير عام.")
    return host
