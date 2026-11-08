from __future__ import annotations
import json, sqlite3
from pathlib import Path
from platformdirs import user_data_dir

DATA_DIR = Path(user_data_dir("Mas3edy", "PersonalAssistant"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "assistant.sqlite3"
CONFIG_PATH = DATA_DIR / "config.json"

def db():
    con = sqlite3.connect(DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""CREATE TABLE IF NOT EXISTS chats(
        id TEXT PRIMARY KEY, mode TEXT NOT NULL, title TEXT NOT NULL,
        messages TEXT NOT NULL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.execute("""CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, event TEXT NOT NULL,
        detail TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    con.commit()
    return con

def load_config():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {"granted_roots": [], "providers": [], "active_provider": "", "active_model": ""}

def save_config(cfg):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)

def save_chat(chat_id, mode, messages):
    first = next((m.get("content", "") for m in messages if m.get("role") == "user"), "محادثة")
    with db() as con:
        con.execute("""INSERT INTO chats(id,mode,title,messages,updated_at)
        VALUES(?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET
        mode=excluded.mode,title=excluded.title,messages=excluded.messages,updated_at=CURRENT_TIMESTAMP""",
        (chat_id, mode, first.replace("\n", " ")[:60], json.dumps(messages, ensure_ascii=False)))

def list_chats(mode, limit=30):
    with db() as con:
        rows = con.execute("SELECT id,title FROM chats WHERE mode=? ORDER BY updated_at DESC LIMIT ?", (mode, limit)).fetchall()
        return [(r["id"], r["title"]) for r in rows]

def load_chat(chat_id):
    with db() as con:
        row = con.execute("SELECT messages FROM chats WHERE id=?", (chat_id,)).fetchone()
        return json.loads(row["messages"]) if row else []

def delete_chat(chat_id):
    with db() as con:
        con.execute("DELETE FROM chats WHERE id=?", (chat_id,))

def audit(event, detail):
    with db() as con:
        con.execute("INSERT INTO audit(event,detail) VALUES(?,?)", (event, detail[:2000]))
