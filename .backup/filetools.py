from __future__ import annotations
import difflib, hashlib, os, shutil, uuid
from pathlib import Path
from security import resolve_inside, is_sensitive, TEXT_EXTENSIONS
from storage import DATA_DIR, audit

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 2_000_000
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def list_files(root: str, limit=500):
    base = Path(root).resolve(strict=True)
    result = []
    for current, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {".git","node_modules","__pycache__",".venv","venv","dist","build"}]
        for name in names:
            p = Path(current) / name
            try:
                rel = p.relative_to(base)
                if is_sensitive(rel) or p.is_symlink():
                    continue
                if p.suffix.lower() in TEXT_EXTENSIONS:
                    result.append(str(rel))
                    if len(result) >= limit:
                        return result
            except Exception:
                continue
    return result

def read_file(root: str, relative: str):
    p = resolve_inside(root, relative, allow_missing=False)
    if not p.is_file() or p.stat().st_size > MAX_READ_BYTES:
        raise ValueError("الملف غير موجود أو أكبر من حد القراءة (1MB).")
    raw = p.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError("يبدو أن الملف ثنائي وليس ملفًا نصيًا.")
    return raw.decode("utf-8", errors="replace")

def make_proposal(root: str, operation: str, source: str, content=None, destination=None):
    if operation not in {"write", "move", "rename"}:
        raise ValueError("نوع العملية غير مدعوم.")
    src = resolve_inside(root, source)
    if operation == "write":
        if content is None or len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ValueError("المحتوى فارغ أو أكبر من 2MB.")
        old = src.read_bytes() if src.exists() and src.is_file() else None
        if src.exists() and not src.is_file():
            raise ValueError("المسار الحالي ليس ملفًا عاديًا.")
        return {
            "id": str(uuid.uuid4()), "operation": operation, "source": source,
            "content": content, "source_hash": sha256_bytes(old) if old is not None else None,
            "destination": None
        }
    if not destination:
        raise ValueError("حدد مسار الوجهة.")
    dst = resolve_inside(root, destination)
    if not src.exists() or not src.is_file():
        raise ValueError("المصدر يجب أن يكون ملفًا موجودًا.")
    if dst.exists():
        raise FileExistsError("الوجهة موجودة بالفعل؛ لن يتم استبدالها.")
    return {
        "id": str(uuid.uuid4()), "operation": operation, "source": source,
        "content": None, "source_hash": sha256_bytes(src.read_bytes()), "destination": destination
    }

def proposal_diff(root, proposal):
    if proposal["operation"] != "write":
        return f"العملية: {proposal['operation']}\nمن: {proposal['source']}\nإلى: {proposal['destination']}"
    p = resolve_inside(root, proposal["source"])
    new = proposal["content"].splitlines()
    if p.exists():
        old = p.read_text(encoding="utf-8", errors="replace").splitlines()
        diff = difflib.unified_diff(old, new, fromfile="قبل", tofile="بعد", lineterm="")
        return "\n".join(diff)[:20000] or "لا يوجد اختلاف."
    return "ملف جديد:\n" + proposal["content"][:10000]

def approve_proposal(root: str, proposal: dict):
    # Revalidate paths and source hash immediately before mutation.
    src = resolve_inside(root, proposal["source"])
    if proposal["operation"] == "write":
        current = src.read_bytes() if src.exists() and src.is_file() else None
        current_hash = sha256_bytes(current) if current is not None else None
        if current_hash != proposal["source_hash"]:
            raise RuntimeError("الملف تغيّر بعد عرض المقترح. أعد إنشاء المقترح وراجعه.")
        if src.exists() and not src.is_file():
            raise ValueError("المسار ليس ملفًا عاديًا.")
        src.parent.mkdir(parents=False, exist_ok=True) if not src.parent.exists() else None
        if current is not None:
            backup = BACKUP_DIR / f"{proposal['id']}.bak"
            backup.write_bytes(current)
        temp = src.with_name(src.name + f".{proposal['id']}.tmp")
        try:
            with open(temp, "xb") as f:
                f.write(proposal["content"].encode("utf-8"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, src)
        finally:
            if temp.exists():
                temp.unlink()
        audit("write", f"{proposal['source']} [{proposal['id']}]")
        return "تم حفظ الملف. " + (f"النسخة السابقة محفوظة في {BACKUP_DIR}" if current is not None else "تم إنشاء ملف جديد.")
    dst = resolve_inside(root, proposal["destination"])
    if not src.exists() or sha256_bytes(src.read_bytes()) != proposal["source_hash"]:
        raise RuntimeError("المصدر تغيّر بعد عرض المقترح.")
    if dst.exists():
        raise FileExistsError("الوجهة ظهرت بعد عرض المقترح؛ تم إلغاء العملية.")
    if src.stat().st_dev != dst.parent.stat().st_dev:
        raise ValueError("النقل بين أقراص مختلفة غير مدعوم في الإصدار الأول.")
    dst.parent.mkdir(parents=False, exist_ok=True) if not dst.parent.exists() else None
    src.rename(dst)
    audit(proposal["operation"], f"{proposal['source']} -> {proposal['destination']}")
    return "تم نقل/إعادة تسمية الملف بنجاح."
