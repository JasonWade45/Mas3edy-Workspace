from __future__ import annotations

import json

from .filetools import list_files, make_proposal, read_file
from .network import fetch_webpage
from .personalization import retrieve_personal_context
from .providers import Provider, chat_completion
from .storage import audit

# قائمة النماذج المعروفة بدعم الأدوات في Groq (بناءً على توثيقهم)
GROQ_TOOL_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct-0905",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


def tool_schema(name, description, properties, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def build_tools(root):
    tools = [
        tool_schema(
            "web_read",
            "قراءة صفحة ويب عامة عبر HTTPS",
            {"url": {"type": "string"}},
            ["url"],
        ),
    ]
    if root:
        tools += [
            tool_schema("list_files", "عرض الملفات النصية في المجلد المصرح به", {}, []),
            tool_schema(
                "read_file",
                "قراءة ملف نصي داخل المجلد المصرح به",
                {"path": {"type": "string"}},
                ["path"],
            ),
            tool_schema(
                "propose_write",
                "اقتراح إنشاء أو تعديل ملف؛ لا ينفذ قبل موافقة المستخدم",
                {"path": {"type": "string"}, "content": {"type": "string"}},
                ["path", "content"],
            ),
            tool_schema(
                "propose_move",
                "اقتراح نقل أو إعادة تسمية ملف؛ لا ينفذ قبل الموافقة",
                {"source": {"type": "string"}, "destination": {"type": "string"}},
                ["source", "destination"],
            ),
        ]
    return tools


MAX_HISTORY_MESSAGES = 24
MAX_HISTORY_CHARS = 48_000


def _bounded_history(
    history, max_messages=MAX_HISTORY_MESSAGES, max_chars=MAX_HISTORY_CHARS
):
    """Keep the newest valid turns within a predictable prompt-size budget."""
    if max_messages <= 0 or max_chars <= 0:
        return []
    messages = [
        {**message, "content": str(message.get("content", ""))}
        for message in history
        if isinstance(message, dict) and message.get("role") in {"user", "assistant"}
    ][-max_messages:]

    selected = []
    used_chars = 0
    for message in reversed(messages):
        content = message["content"]
        if used_chars + len(content) <= max_chars:
            selected.append(message)
            used_chars += len(content)
            continue
        if not selected:
            marker = "\n[اقتُطع جزء من الرسالة لضبط طول السياق]"
            clipped_content = (
                content[:max_chars]
                if max_chars <= len(marker)
                else content[: max_chars - len(marker)] + marker
            )
            selected.append({**message, "content": clipped_content[:max_chars]})
        break
    return list(reversed(selected))


def dispatch(name, args, root, proposals, log):
    if name == "web_read":
        result = fetch_webpage(args["url"])
        log.append("قراءة صفحة ويب")
        audit("web_read", "قراءة صفحة ويب عامة")
        return result
    if name == "list_files" and root:
        result = "\n".join(list_files(root)) or "لا توجد ملفات نصية مدعومة."
        log.append("استعراض ملفات المجلد")
        audit("list_files", "استعراض مجلد مصرح به")
        return result
    if name == "read_file" and root:
        result = read_file(root, args["path"])
        log.append("قراءة ملف: " + args["path"])
        audit("read_file", args["path"])
        return result
    if name == "propose_write" and root:
        proposals.append(
            make_proposal(root, "write", args["path"], content=args["content"])
        )
        log.append("إنشاء مقترح تعديل: " + args["path"])
        audit("propose_write", args["path"])
        return "تم إنشاء مقترح ينتظر موافقة المستخدم."
    if name == "propose_move" and root:
        proposals.append(
            make_proposal(root, "move", args["source"], destination=args["destination"])
        )
        log.append(f"إنشاء مقترح نقل: {args['source']} → {args['destination']}")
        audit("propose_move", f"{args['source']} -> {args['destination']}")
        return "تم إنشاء مقترح نقل ينتظر موافقة المستخدم."
    return "الأداة غير مفعلة أو غير معروفة."


def run_assistant(
    provider: Provider,
    history,
    system_prompt,
    root=None,
    max_rounds=6,
    personalization_enabled=True,
):
    proposals, log = [], []
    if personalization_enabled:
        last_user_message = next(
            (
                message.get("content", "")
                for message in reversed(history)
                if message.get("role") == "user"
            ),
            "",
        )
        try:
            personal_context = retrieve_personal_context(last_user_message)
            if personal_context:
                system_prompt = f"{system_prompt}\n\n{personal_context}"
        except Exception as exc:
            # Personalization is optional; a database issue should not block chat.
            log.append(f"تعذر تحميل الذاكرة المحلية: {type(exc).__name__}")

    # التحقق مما إذا كان الموديل يدعم الأدوات
    supports_tools = provider.supports_tools
    if supports_tools is None:
        supports_tools = not (
            "groq" in provider.base_url.lower()
            and provider.model not in GROQ_TOOL_MODELS
        )

    # إذا كان الموديل لا يدعم الأدوات، لا نرسلها
    tools = build_tools(root) if supports_tools else None

    messages = [{"role": "system", "content": system_prompt}] + _bounded_history(
        history
    )

    for _ in range(max_rounds):
        # نرسل الأدوات فقط إذا كانت مدعومة
        response = chat_completion(provider, messages, tools=tools)
        msg = response.choices[0].message

        if not msg.tool_calls:
            return (msg.content or ""), proposals, log

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": t.id,
                        "type": "function",
                        "function": {
                            "name": t.function.name,
                            "arguments": t.function.arguments,
                        },
                    }
                    for t in msg.tool_calls
                ],
            }
        )
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise TypeError("وسائط الأداة يجب أن تكون كائن JSON.")
                result = dispatch(call.function.name, args, root, proposals, log)
            except Exception as exc:
                result = f"تعذر تنفيذ الأداة: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": str(result)[:20000],
                }
            )
    return "وصل المساعد إلى حد خطوات الأدوات. وضّح المهمة أو قسّمها.", proposals, log
