"""Import conversations exported from ChatGPT / Claude into local chats.

Both exports use a top-level ``conversations.json`` array. ChatGPT exports store
a ``mapping`` tree of nodes; Claude exports store flat ``chat_messages`` lists.
Parsing is tolerant: unrecognized shapes are skipped, not fatal.
"""

from __future__ import annotations

import json

MAX_IMPORT_CONVERSATIONS = 100
MAX_MESSAGE_CHARS = 50_000


def _clip(text, limit=MAX_MESSAGE_CHARS) -> str:
    return str(text or "")[:limit]


def _chatgpt_messages(conversation: dict) -> list[dict]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return []
    nodes = []
    for node_id, node in mapping.items():
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue
        author = message.get("author") or {}
        role = author.get("role") if isinstance(author, dict) else None
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        if isinstance(parts, list):
            text = "\n".join(str(part) for part in parts if isinstance(part, str))
        else:
            text = str(content.get("text", "")) if isinstance(content, dict) else ""
        if not text.strip():
            continue
        created = message.get("create_time") or 0
        nodes.append((created, {"role": role, "content": _clip(text)}))
    nodes.sort(key=lambda item: item[0] or 0)
    return [message for _, message in nodes]


def _claude_messages(conversation: dict) -> list[dict]:
    messages = conversation.get("chat_messages")
    if not isinstance(messages, list):
        return []
    parsed = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        sender = str(message.get("sender", "")).lower()
        role = "user" if sender == "human" else "assistant" if sender == "assistant" else None
        if role is None:
            continue
        text = message.get("text")
        if not isinstance(text, str) or not text.strip():
            # Claude sometimes stores structured content blocks.
            content = message.get("content")
            if isinstance(content, list):
                text = "\n".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict)
                )
        if not str(text or "").strip():
            continue
        parsed.append({"role": role, "content": _clip(text)})
    return parsed


def parse_conversations(raw_bytes: bytes) -> list[dict]:
    """Parse an export file into ``[{title, messages}]``. Skips bad entries."""
    try:
        data = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("ملف الاستيراد ليس JSON صالحًا.") from exc

    # Some exports wrap everything in {"conversations": [...]}
    if isinstance(data, dict):
        data = data.get("conversations") or data.get("chats") or [data]
    if not isinstance(data, list):
        raise ValueError("صيغة ملف الاستيراد غير معروفة.")

    parsed = []
    for conversation in data[:MAX_IMPORT_CONVERSATIONS]:
        if not isinstance(conversation, dict):
            continue
        messages = _chatgpt_messages(conversation) or _claude_messages(conversation)
        if not messages:
            continue
        title = str(
            conversation.get("title")
            or conversation.get("name")
            or "محادثة مستوردة"
        )
        parsed.append({"title": title[:80], "messages": messages})
    return parsed
