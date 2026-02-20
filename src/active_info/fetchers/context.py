from __future__ import annotations

from urllib.parse import urlparse

import requests


def _build_jina_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return ""
    path = parsed.path or ""
    query = f"?{parsed.query}" if parsed.query else ""
    return f"https://r.jina.ai/http://{parsed.netloc}{path}{query}"


def fetch_article_context(url: str, timeout: int = 15, max_chars: int = 2500) -> str:
    jina_url = _build_jina_url(url)
    if not jina_url:
        return ""

    try:
        resp = requests.get(jina_url, timeout=timeout)
        resp.raise_for_status()
        text = resp.text.replace("\x00", " ").strip()
        return text[:max_chars]
    except requests.RequestException:
        return ""
