from __future__ import annotations

import difflib
import hashlib
import os
import uuid
from pathlib import Path

from .security import IGNORED_DIRS, is_sensitive, is_text_path, resolve_inside
from .storage import DATA_DIR, audit

MAX_READ_BYTES = 1_000_000
MAX_WRITE_BYTES = 2_000_000
MAX_DIFF_SOURCE_BYTES = 2_000_000
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audit_best_effort(event: str, detail: str) -> str:
    try:
        audit(event, detail)
    except Exception:
        # The file operation has already completed; do not leave its proposal
        # pending and risk the user repeating a successful operation.
        return " تعذر تسجيل العملية في سجل النشاط."
    return ""


def list_files(root: str, limit: int = 500) -> list[str]:
    if limit <= 0:
        return []
    base = Path(root).resolve(strict=True)
    result: list[str] = []
    for current, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRS]
        for name in names:
            path = Path(current) / name
            try:
                relative = path.relative_to(base)
                if path.is_symlink() or is_sensitive(relative):
                    continue
                if is_text_path(relative):
                    result.append(str(relative))
                    if len(result) >= limit:
                        return result
            except (OSError, ValueError):
                continue
    return result


def read_file(root: str, relative: str) -> str:
    path = resolve_inside(root, relative, allow_missing=False)
    if not is_text_path(relative):
        raise ValueError("امتداد الملف غير مدعوم للقراءة النصية.")
    if not path.is_file():
        raise ValueError("المسار ليس ملفًا عاديًا.")

    # Read one byte over the limit so a file that grows after stat cannot cause
    # an unbounded allocation.
    with path.open("rb") as file:
        raw = file.read(MAX_READ_BYTES + 1)
    if len(raw) > MAX_READ_BYTES:
        raise ValueError("الملف أكبر من حد القراءة (1MB).")
    if b"\x00" in raw[:4096]:
        raise ValueError("يبدو أن الملف ثنائي وليس ملفًا نصيًا.")
    return raw.decode("utf-8", errors="replace")


def make_proposal(
    root: str, operation: str, source: str, content=None, destination=None
):
    if operation not in {"write", "move", "rename"}:
        raise ValueError("نوع العملية غير مدعوم.")

    root_path = Path(root).expanduser().resolve(strict=True)
    root_str = str(root_path)
    src = resolve_inside(root_path, source)

    if operation == "write":
        if not is_text_path(source):
            raise ValueError("الكتابة مسموحة فقط للامتدادات النصية المدعومة.")
        if content is None or not isinstance(content, str):
            raise ValueError("المحتوى لازم يكون نصًا.")
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ValueError("المحتوى أكبر من الحد المسموح (2MB).")

        old = None
        if src.exists():
            if not src.is_file():
                raise ValueError("المسار الحالي ليس ملفًا عاديًا.")
            if src.stat().st_size > MAX_DIFF_SOURCE_BYTES:
                raise ValueError("الملف الحالي أكبر من الحد المسموح لمراجعته (2MB).")
            old = src.read_bytes()
            if len(old) > MAX_DIFF_SOURCE_BYTES:
                raise ValueError("الملف الحالي أكبر من الحد المسموح لمراجعته (2MB).")
            if b"\x00" in old[:4096]:
                raise ValueError("لن يتم استبدال ملف يبدو ثنائيًا.")

        return {
            "id": str(uuid.uuid4()),
            "operation": operation,
            "source": source,
            "root": root_str,
            "content": content,
            "source_hash": sha256_bytes(old) if old is not None else None,
            "destination": None,
        }

    if not destination:
        raise ValueError("حدد مسار الوجهة.")
    dst = resolve_inside(root_path, destination)
    if not src.exists() or not src.is_file():
        raise ValueError("المصدر يجب أن يكون ملفًا موجودًا.")
    if dst.exists():
        raise FileExistsError("الوجهة موجودة بالفعل؛ لن يتم استبدالها.")

    return {
        "id": str(uuid.uuid4()),
        "operation": operation,
        "source": source,
        "root": root_str,
        "content": None,
        "source_hash": sha256_file(src),
        "destination": destination,
    }


def proposal_diff(root: str, proposal: dict) -> str:
    base_root = proposal.get("root") or root
    if proposal["operation"] != "write":
        return f"العملية: {proposal['operation']}\nمن: {proposal['source']}\nإلى: {proposal['destination']}"

    path = resolve_inside(base_root, proposal["source"])
    new_lines = proposal["content"].splitlines()
    if path.exists():
        if path.stat().st_size > MAX_DIFF_SOURCE_BYTES:
            raise ValueError("الملف الحالي أكبر من الحد المسموح لمراجعته (2MB).")
        with path.open("rb") as file:
            old_bytes = file.read(MAX_DIFF_SOURCE_BYTES + 1)
        if len(old_bytes) > MAX_DIFF_SOURCE_BYTES:
            raise ValueError("الملف الحالي أكبر من الحد المسموح لمراجعته (2MB).")
        old_lines = old_bytes.decode("utf-8", errors="replace").splitlines()
        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile="قبل", tofile="بعد", lineterm=""
        )
        return "\n".join(diff) or "لا يوجد اختلاف."
    return "ملف جديد:\n" + proposal["content"]


def approve_proposal(root: str, proposal: dict) -> str:
    proposal_root = proposal.get("root")
    resolved_root = str(Path(root).expanduser().resolve(strict=True))
    if proposal_root and resolved_root != proposal_root:
        raise RuntimeError(
            "المجلد المصرح به تغيّر بعد إنشاء المقترح. أعد إنشاء المقترح تحت المجلد الصحيح."
        )

    try:
        proposal_id = str(uuid.UUID(str(proposal["id"])))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError("معرّف المقترح غير صالح.") from exc

    operation = proposal.get("operation")
    if operation not in {"write", "move", "rename"}:
        raise ValueError("نوع العملية غير مدعوم.")

    src = resolve_inside(resolved_root, proposal["source"])
    if operation == "write":
        current = None
        if src.exists():
            if not src.is_file():
                raise ValueError("المسار ليس ملفًا عاديًا.")
            if src.stat().st_size > MAX_DIFF_SOURCE_BYTES:
                raise RuntimeError(
                    "الملف تجاوز حد المراجعة بعد إنشاء المقترح؛ أعد إنشاءه."
                )
            current = src.read_bytes()
            if len(current) > MAX_DIFF_SOURCE_BYTES:
                raise RuntimeError(
                    "الملف تجاوز حد المراجعة بعد إنشاء المقترح؛ أعد إنشاءه."
                )
        current_hash = sha256_bytes(current) if current is not None else None
        if current_hash != proposal.get("source_hash"):
            raise RuntimeError("الملف تغيّر بعد عرض المقترح. أعد إنشاء المقترح وراجعه.")
        if not isinstance(proposal.get("content"), str):
            raise ValueError("محتوى المقترح غير صالح.")
        content_bytes = proposal["content"].encode("utf-8")
        if len(content_bytes) > MAX_WRITE_BYTES:
            raise ValueError("المحتوى أكبر من الحد المسموح (2MB).")

        src.parent.mkdir(parents=True, exist_ok=True)
        if current is not None:
            backup = BACKUP_DIR / f"{proposal_id}.bak"
            backup.write_bytes(current)

        temp = src.with_name(src.name + f".{proposal_id}.tmp")
        try:
            with temp.open("xb") as file:
                file.write(content_bytes)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, src)
        finally:
            if temp.exists():
                temp.unlink()

        if sha256_file(src) != sha256_bytes(content_bytes):
            raise RuntimeError(
                "لم يتطابق الملف بعد الكتابة مع المقترح؛ راجع النسخة الاحتياطية قبل المتابعة."
            )

        audit_note = _audit_best_effort(
            "write", f"{proposal['source']} [{proposal_id}]"
        )
        if current is not None:
            return f"تم حفظ الملف. النسخة السابقة محفوظة في {BACKUP_DIR}.{audit_note}"
        return f"تم إنشاء الملف الجديد.{audit_note}"

    dst = resolve_inside(resolved_root, proposal["destination"])
    if (
        not src.exists()
        or not src.is_file()
        or sha256_file(src) != proposal.get("source_hash")
    ):
        raise RuntimeError("المصدر تغيّر بعد عرض المقترح.")
    if dst.exists():
        raise FileExistsError("الوجهة ظهرت بعد عرض المقترح؛ تم إلغاء العملية.")

    # Find the nearest existing ancestor before creating destination directories.
    probe = dst.parent
    while not probe.exists():
        if probe == probe.parent:
            raise RuntimeError("تعذر العثور على مجلد أب موجود.")
        probe = probe.parent
    if src.stat().st_dev != probe.stat().st_dev:
        raise ValueError("النقل بين أقراص مختلفة غير مدعوم في الإصدار الأول.")

    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    if (
        src.exists()
        or not dst.is_file()
        or sha256_file(dst) != proposal.get("source_hash")
    ):
        raise RuntimeError("تم النقل لكن تعذر التحقق من الملف في الوجهة.")
    audit_note = _audit_best_effort(
        operation, f"{proposal['source']} -> {proposal['destination']}"
    )
    return f"تم نقل/إعادة تسمية الملف بنجاح.{audit_note}"
