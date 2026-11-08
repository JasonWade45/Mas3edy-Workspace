from __future__ import annotations
import json
from providers import chat_completion, Provider
from filetools import list_files, read_file, make_proposal
from network import fetch_webpage

# قائمة النماذج المعروفة بدعم الأدوات في Groq (بناءً على توثيقهم)
GROQ_TOOL_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct-0905",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

def tool_schema(name, description, properties, required=None):
    return {"type":"function","function":{"name":name,"description":description,
            "parameters":{"type":"object","properties":properties,"required":required or [],"additionalProperties":False}}}

def build_tools(root):
    tools = [
        tool_schema("web_read", "قراءة صفحة ويب عامة عبر HTTPS", {"url":{"type":"string"}}, ["url"]),
    ]
    if root:
        tools += [
            tool_schema("list_files", "عرض الملفات النصية في المجلد المصرح به", {}, []),
            tool_schema("read_file", "قراءة ملف نصي داخل المجلد المصرح به", {"path":{"type":"string"}}, ["path"]),
            tool_schema("propose_write", "اقتراح إنشاء أو تعديل ملف؛ لا ينفذ قبل موافقة المستخدم", {"path":{"type":"string"},"content":{"type":"string"}}, ["path","content"]),
            tool_schema("propose_move", "اقتراح نقل أو إعادة تسمية ملف؛ لا ينفذ قبل الموافقة", {"source":{"type":"string"},"destination":{"type":"string"}}, ["source","destination"]),
        ]
    return tools

def dispatch(name, args, root, proposals, log):
    if name == "web_read":
        log.append("قراءة صفحة ويب")
        return fetch_webpage(args["url"])
    if name == "list_files" and root:
        log.append("استعراض ملفات المجلد")
        return "\n".join(list_files(root)) or "لا توجد ملفات نصية مدعومة."
    if name == "read_file" and root:
        log.append("قراءة ملف: " + args["path"])
        return read_file(root, args["path"])
    if name == "propose_write" and root:
        proposals.append(make_proposal(root, "write", args["path"], content=args["content"]))
        log.append("إنشاء مقترح تعديل: " + args["path"])
        return "تم إنشاء مقترح ينتظر موافقة المستخدم."
    if name == "propose_move" and root:
        proposals.append(make_proposal(root, "move", args["source"], destination=args["destination"]))
        log.append(f"إنشاء مقترح نقل: {args['source']} → {args['destination']}")
        return "تم إنشاء مقترح نقل ينتظر موافقة المستخدم."
    return "الأداة غير مفعلة أو غير معروفة."

def run_assistant(provider: Provider, history, system_prompt, root=None, max_rounds=6):
    # التحقق مما إذا كان الموديل يدعم الأدوات
    supports_tools = True
    if "groq" in provider.base_url.lower():
        if provider.model not in GROQ_TOOL_MODELS:
            supports_tools = False

    # إذا كان الموديل لا يدعم الأدوات، لا نرسلها
    tools = build_tools(root) if supports_tools else None
    
    messages = [{"role":"system","content":system_prompt}] + history[-24:]
    proposals, log = [], []
    
    for _ in range(max_rounds):
        # نرسل الأدوات فقط إذا كانت مدعومة
        response = chat_completion(provider, messages, tools=tools)
        msg = response.choices[0].message
        
        if not msg.tool_calls:
            return (msg.content or ""), proposals, log
            
        messages.append({"role":"assistant","content":msg.content or "",
                         "tool_calls":[{"id":t.id,"type":"function","function":{"name":t.function.name,"arguments":t.function.arguments}} for t in msg.tool_calls]})
        for call in msg.tool_calls:
            try:
                args = json.loads(call.function.arguments or "{}")
                if not isinstance(args, dict):
                    raise ValueError("وسائط الأداة يجب أن تكون كائن JSON.")
                result = dispatch(call.function.name, args, root, proposals, log)
            except Exception as exc:
                result = f"تعذر تنفيذ الأداة: {exc}"
            messages.append({"role":"tool","tool_call_id":call.id,"content":str(result)[:20000]})
    return "وصل المساعد إلى حد خطوات الأدوات. وضّح المهمة أو قسّمها.", proposals, log