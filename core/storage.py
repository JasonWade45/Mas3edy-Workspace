from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from platformdirs import user_data_dir

# Preserve the legacy data directory so existing chats, notes, and settings are not orphaned.
DATA_DIR = Path(user_data_dir("Mas3edy", "PersonalAssistant"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "assistant.sqlite3"
CONFIG_PATH = DATA_DIR / "config.json"


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
            """CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )"""
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
            "SELECT id,title FROM chats WHERE mode=? ORDER BY updated_at DESC LIMIT ?",
            (mode, max(0, limit)),
        ).fetchall()
    return [(row["id"], row["title"]) for row in rows]


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
    with db() as connection:
        connection.execute(
            "INSERT INTO audit(event,detail) VALUES(?,?)",
            (event[:100], detail[:2000]),
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
