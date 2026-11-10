"""Local PII redaction applied to the *outgoing* provider payload only.

Displayed history and saved chats keep the original text; the redacted copy is
what leaves the machine. Covers emails, Egyptian/international phone numbers,
credit/debit card numbers (with Luhn check) and long digit runs.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Egyptian mobiles (010/011/012/015 + 8 digits) and E.164-ish international numbers.
PHONE_RE = re.compile(r"(?<!\d)(?:\+?20|0020)?[-\s]?01[0125][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")
INTL_PHONE_RE = re.compile(r"(?<!\d)\+\d{1,3}[-\s]?\d{2,4}[-\s]?\d{3,4}[-\s]?\d{3,4}(?!\d)")
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
LONG_DIGITS_RE = re.compile(r"(?<!\d)\d{9,}(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _redact_card(match: re.Match) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    if 13 <= len(digits) <= 19 and _luhn_ok(digits):
        return "[CARD]"
    return match.group(0)


def redact_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text or ""
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PHONE_RE.sub("[PHONE]", text)
    text = INTL_PHONE_RE.sub("[PHONE]", text)
    text = CARD_RE.sub(_redact_card, text)
    text = LONG_DIGITS_RE.sub("[NUMBER]", text)
    return text


def redact_messages(messages: list[dict]) -> list[dict]:
    """Return a redacted deep-enough copy of OpenAI-style messages."""
    redacted = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        item = dict(message)
        content = item.get("content")
        if isinstance(content, str):
            item["content"] = redact_text(content)
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append({**part, "text": redact_text(part.get("text", ""))})
                else:
                    parts.append(part)
            item["content"] = parts
        redacted.append(item)
    return redacted
