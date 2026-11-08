from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from security import validate_public_url

def fetch_webpage(url: str, max_chars=18000):
    validate_public_url(url)
    # Redirects are disabled so a public URL cannot redirect into a private network.
    response = requests.get(url, timeout=(5, 15), allow_redirects=False,
                            headers={"User-Agent": "Mas3edyAssistant/1.0"})
    if 300 <= response.status_code < 400:
        raise ValueError("تم إيقاف إعادة التوجيه لأسباب أمنية. افتح الرابط النهائي مباشرة.")
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("الصفحة أكبر من الحد المسموح.")
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())[:max_chars]
