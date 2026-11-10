from __future__ import annotations

import json
import logging
import uuid
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo

from platformdirs import user_data_dir

# Preserve the legacy data directory so existing chats, notes, and settings are not orphaned.
DATA_DIR = Path(user_data_dir("Mas3edy", "PersonalAssistant"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "assistant.sqlite3"
CONFIG_PATH = DATA_DIR / "config.json"
BACKUP_DIR = DATA_DIR / "backups"
LOCAL_TZ = ZoneInfo("Africa/Cairo")

_LOGGER: logging.Logger | None = None


def _local_logger() -> logging.Logger:
    """Rotating structured log next to the database (max ~3MB total)."""
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logs_dir = DATA_DIR / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            logs_dir / "activity.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger = logging.getLogger("nova.activity")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False
        _LOGGER = logger
    except OSError:
        _LOGGER = logging.getLogger("nova.activity.fallback")
        _LOGGER.addHandler(logging.NullHandler())
    return _LOGGER


def backup_database(keep: int = 7) -> Path | None:
    """Copy the SQLite DB + config into backups/ once per day; keep the newest N."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d")
        target = BACKUP_DIR / f"backup-{stamp}"
        marker = target / "BACKUP_OK"
        if marker.exists():
            return target
        target.mkdir(parents=True, exist_ok=True)
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, target / "assistant.sqlite3")
        if CONFIG_PATH.exists():
            shutil.copy2(CONFIG_PATH, target / "config.json")
        marker.write_text(datetime.now(LOCAL_TZ).isoformat(), encoding="utf-8")
        # Prune old backups, oldest first.
        backups = sorted(
            (p for p in BACKUP_DIR.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for old in backups[max(1, keep):]:
            shutil.rmtree(old, ignore_errors=True)
        return target
    except OSError:
        return None


@contextmanager
def db():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS chats(
                id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                title TEXT NOT NULL,
                messages TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS tasks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_updated ON chats(updated_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_done ON tasks(done, created_at DESC)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS assistant_notes(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL CHECK(kind IN ('memory', 'knowledge', 'example')),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT
            )"""
        )
        note_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(assistant_notes)"
            ).fetchall()
        }
        if "expires_at" not in note_columns:
            connection.execute("ALTER TABLE assistant_notes ADD COLUMN expires_at TEXT")
        chat_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(chats)").fetchall()
        }
        if "pinned" not in chat_columns:
            connection.execute(
                "ALTER TABLE chats ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_notes_kind_expires ON assistant_notes(kind, expires_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chats_pinned ON chats(pinned DESC, updated_at DESC)"
        )
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {
            "granted_roots": [],
            "providers": [],
            "active_provider": "",
            "active_model": "",
            "language": "ar",
        }


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def save_chat(chat_id: str, mode: str, messages: list[dict]) -> None:
    first = next(
        (m.get("content", "") for m in messages if m.get("role") == "user"), "محادثة"
    )
    title = str(first).replace("\n", " ")[:60]
    with db() as connection:
        connection.execute(
            """INSERT INTO chats(id,mode,title,messages,updated_at)
            VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET
            mode=excluded.mode,title=excluded.title,messages=excluded.messages,
            updated_at=CURRENT_TIMESTAMP""",
            (chat_id, mode, title, json.dumps(messages, ensure_ascii=False)),
        )


def list_chats(mode: str, limit: int = 30) -> list[tuple[str, str]]:
    with db() as connection:
        rows = connection.execute(
            "SELECT id,title FROM chats WHERE mode=? ORDER BY pinned DESC, updated_at DESC LIMIT ?",
            (mode, max(0, limit)),
        ).fetchall()
    return [(row["id"], row["title"]) for row in rows]


def list_chats_detailed(mode: str, limit: int = 30) -> list[dict]:
    """Saved chats with timestamps (Cairo time) and pin state, pinned first."""
    with db() as connection:
        rows = connection.execute(
            """SELECT id,title,mode,updated_at,pinned FROM chats
            WHERE mode=? ORDER BY pinned DESC, updated_at DESC LIMIT ?""",
            (mode, max(0, limit)),
        ).fetchall()
    chats = []
    for row in rows:
        try:
            updated = datetime.strptime(row["updated_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            ).astimezone(LOCAL_TZ)
            iso = updated.isoformat()
        except (TypeError, ValueError):
            iso = str(row["updated_at"] or "")
        chats.append(
            {
                "id": row["id"],
                "title": row["title"],
                "mode": row["mode"],
                "updated_at": iso,
                "pinned": bool(row["pinned"]),
            }
        )
    return chats


def toggle_pin_chat(chat_id: str) -> bool:
    with db() as connection:
        row = connection.execute(
            "SELECT pinned FROM chats WHERE id=?", (chat_id,)
        ).fetchone()
        if not row:
            return False
        new_value = 0 if row["pinned"] else 1
        connection.execute(
            "UPDATE chats SET pinned=? WHERE id=?", (new_value, chat_id)
        )
    return bool(new_value)


def count_chats(mode: str | None = None) -> int:
    with db() as connection:
        if mode is None:
            row = connection.execute("SELECT COUNT(*) AS count FROM chats").fetchone()
        else:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM chats WHERE mode=?", (mode,)
            ).fetchone()
    return int(row["count"])


def load_chat(chat_id: str) -> list[dict]:
    with db() as connection:
        row = connection.execute(
            "SELECT messages FROM chats WHERE id=?", (chat_id,)
        ).fetchone()
    if not row:
        return []
    try:
        messages = json.loads(row["messages"])
    except json.JSONDecodeError:
        return []
    return messages if isinstance(messages, list) else []


def delete_chat(chat_id: str) -> None:
    with db() as connection:
        connection.execute("DELETE FROM chats WHERE id=?", (chat_id,))


def audit(event: str, detail: str) -> None:
    event_text, detail_text = event[:100], detail[:2000]
    try:
        _local_logger().info("%s | %s", event_text, detail_text)
    except Exception:
        pass
    with db() as connection:
        connection.execute(
            "INSERT INTO audit(event,detail) VALUES(?,?)",
            (event_text, detail_text),
        )


def list_audit(limit: int = 30) -> list[tuple[str, str, str]]:
    with db() as connection:
        rows = connection.execute(
            "SELECT event,detail,created_at FROM audit ORDER BY id DESC LIMIT ?",
            (max(0, limit),),
        ).fetchall()
    return [(row["event"], row["detail"], row["created_at"]) for row in rows]


NOTE_KINDS = {"memory", "knowledge", "example"}
MAX_NOTE_TITLE_CHARS = 160
MAX_NOTE_CONTENT_CHARS = 10_000


def add_note(
    kind: str, title: str, content: str, expires_in_days: int | None = None
) -> int:
    if kind not in NOTE_KINDS:
        raise ValueError("نوع المعلومة غير مدعوم.")
    if not isinstance(title, str) or not isinstance(content, str):
        raise TypeError("العنوان والمحتوى لازم يكونوا نصًا.")
    if expires_in_days is not None and (
        not isinstance(expires_in_days, int)
        or isinstance(expires_in_days, bool)
        or not 1 <= expires_in_days <= 3650
    ):
        raise ValueError("مدة الاحتفاظ لازم تكون من يوم إلى 10 سنوات.")
    title = " ".join(title.split())[:MAX_NOTE_TITLE_CHARS]
    content = content.strip()
    if not title or not content:
        raise ValueError("اكتب عنوانًا ومحتوى قبل الحفظ.")
    if len(content) > MAX_NOTE_CONTENT_CHARS:
        raise ValueError("المحتوى أطول من الحد المسموح (10,000 حرف).")

    expires_at = None
    if expires_in_days is not None:
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        ).strftime("%Y-%m-%d %H:%M:%S")

    with db() as connection:
        existing = connection.execute(
            """SELECT id FROM assistant_notes
            WHERE kind=? AND title=? AND content=? AND expires_at IS ? LIMIT 1""",
            (kind, title, content, expires_at),
        ).fetchone()
        if existing:
            return int(existing["id"])
        cursor = connection.execute(
            """INSERT INTO assistant_notes(kind,title,content,expires_at)
            VALUES(?,?,?,?)""",
            (kind, title, content, expires_at),
        )
        return int(cursor.lastrowid)


def list_notes(
    kind: str, limit: int = 100, include_expired: bool = False
) -> list[dict]:
    if kind not in NOTE_KINDS:
        raise ValueError("نوع المعلومة غير مدعوم.")
    expiry_filter = (
        ""
        if include_expired
        else "AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)"
    )
    with db() as connection:
        rows = connection.execute(
            f"""SELECT id,kind,title,content,created_at,expires_at FROM assistant_notes
            WHERE kind=? {expiry_filter} ORDER BY id DESC LIMIT ?""",
            (kind, max(0, limit)),
        ).fetchall()
    columns = ("id", "kind", "title", "content", "created_at", "expires_at")
    return [{column: row[column] for column in columns} for row in rows]


def delete_note(note_id: int, kind: str | None = None) -> bool:
    with db() as connection:
        if kind is None:
            cursor = connection.execute(
                "DELETE FROM assistant_notes WHERE id=?", (note_id,)
            )
        elif kind in NOTE_KINDS:
            cursor = connection.execute(
                "DELETE FROM assistant_notes WHERE id=? AND kind=?", (note_id, kind)
            )
        else:
            raise ValueError("نوع المعلومة غير مدعوم.")
    return cursor.rowcount > 0


# --- المهام (Tasks) — قائمة مهام محلية بسيطة بدل صفحة "قيد التطوير" ---

MAX_TASK_TITLE_CHARS = 300


def add_task(title: str, source: str = "manual") -> int:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("اكتب المهمة أولًا.")
    clean = " ".join(title.split())[:MAX_TASK_TITLE_CHARS]
    with db() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks(title, source) VALUES(?,?)",
            (clean, str(source or "manual")[:20]),
        )
        return int(cursor.lastrowid)


def list_tasks(status: str = "open", limit: int = 200) -> list[dict]:
    if status not in {"open", "done", "all"}:
        raise ValueError("حالة المهام غير معروفة.")
    where = {"open": "WHERE done=0", "done": "WHERE done=1", "all": ""}[status]
    order = "completed_at DESC" if status == "done" else "created_at DESC"
    with db() as connection:
        rows = connection.execute(
            f"""SELECT id,title,done,source,created_at,completed_at FROM tasks
            {where} ORDER BY {order} LIMIT ?""",
            (max(0, limit),),
        ).fetchall()
    return [dict(row) for row in rows]


def set_task_done(task_id: int, done: bool) -> None:
    with db() as connection:
        if done:
            connection.execute(
                "UPDATE tasks SET done=1, completed_at=CURRENT_TIMESTAMP WHERE id=?",
                (int(task_id),),
            )
        else:
            connection.execute(
                "UPDATE tasks SET done=0, completed_at=NULL WHERE id=?", (int(task_id),)
            )


def delete_task(task_id: int) -> None:
    with db() as connection:
        connection.execute("DELETE FROM tasks WHERE id=?", (int(task_id),))


def count_tasks_done_since(days: int = 7) -> int:
    with db() as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS count FROM tasks
            WHERE done=1 AND completed_at >= datetime('now', ?)""",
            (f"-{max(0, int(days))} days",),
        ).fetchone()
    return int(row["count"])


def count_open_tasks() -> int:
    with db() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE done=0"
        ).fetchone()
    return int(row["count"])


def seed_demo_data() -> int:
    """Insert a small, clearly-labelled demo workspace (chat, tasks, notes).

    Returns the number of items created. Idempotency is not attempted — the
    user triggers this explicitly from Settings, and each run adds a fresh
    demo batch.
    """
    created = 0
    demo_chat_id = "demo-" + uuid.uuid4().hex[:12]
    save_chat(
        demo_chat_id,
        "chat",
        [
            {
                "role": "user",
                "content": "مثال: ما هي أفضل طريقة للتفاوض على سعر عقار؟",
            },
            {
                "role": "assistant",
                "content": (
                    "ابدأ بجمع بيانات قابلة للمقارنة (٣ وحدات مشابهة على الأقل)، "
                    "ثم اطرح عرضك بدليل، واهتم بسرعة الإغلاق كمزايا للبائع. "
                    "لا ترفع الرقم دون سبب موثق، وحدد سقفك قبل الجلسة."
                ),
            },
        ],
    )
    created += 1
    add_task("متابعة عرض الدقي مع المالك", source="manual")
    add_task("تجهيز ملف الصفقة للمراجعة القانونية", source="manual")
    created += 2
    add_note(
        "example",
        "مثال — رسالة متابعة عميل",
        "الأستاذ أحمد، متابع مع حضرتك بخصوص وحدة مدينة نصر. "
        "السعر الحالي ٨.٥ مليون والفرصة محدودة لوجود عرض آخر على الطاولة. "
        "أقدر أرتب معاينة نهار الخميس الساعة ١١؟",
    )
    created += 1
    add_note(
        "knowledge",
        "قاعدة VIC لتحديد الطلب",
        "اسأل عن الدافع، الميزانية، والإطار الزمني قبل عرض أي وحدات.",
    )
    created += 1
    add_note(
        "memory",
        "سياسة عرض الوحدات",
        "لا تعرض أكثر من ٣ وحدات في الجولة الأولى؛ الاختيار الزائد يقتل القرار.",
    )
    created += 1
    return created


def audit_counts_since(days: int = 7) -> list[tuple[str, int]]:
    """Return (event, count) pairs recorded in the last `days` days, most frequent first."""
    if not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")
    with db() as connection:
        rows = connection.execute(
            """SELECT event, COUNT(*) AS total FROM audit
            WHERE datetime(created_at) >= datetime('now', ?)
            GROUP BY event ORDER BY total DESC, event ASC""",
            (f"-{days} days",),
        ).fetchall()
    return [(row["event"], row["total"]) for row in rows]
