from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from .security import validate_public_url

MAX_RESPONSE_BYTES = 2_000_000


def fetch_webpage(url: str, max_chars: int = 18_000) -> str:
    validate_public_url(url)

    # Stream the response and enforce the limit while reading. Checking
    # response.content after requests.get() would already have buffered the
    # entire body in memory. Redirects remain disabled to avoid redirect SSRF.
    with requests.get(
        url,
        timeout=(5, 15),
        allow_redirects=False,
        stream=True,
        headers={"User-Agent": "NOVA-AI/1.0"},
    ) as response:
        if 300 <= response.status_code < 400:
            raise ValueError(
                "تم إيقاف إعادة التوجيه لأسباب أمنية. افتح الرابط النهائي مباشرة."
            )
        response.raise_for_status()

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise ValueError("الصفحة أكبر من الحد المسموح (2MB).")
            chunks.append(chunk)

    soup = BeautifulSoup(b"".join(chunks), "html.parser")
    for tag in soup(("script", "style", "noscript", "svg")):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())[: max(0, max_chars)]
