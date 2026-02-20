from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from active_info.models import NewsItem


def _normalize_title(title: str) -> str:
    lowered = title.lower()
    lowered = re.sub(r"https?://\S+", " ", lowered)
    lowered = re.sub(r"[^\w\s]", " ", lowered)
    return " ".join(lowered.split())


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/")
    return f"{parsed.netloc.lower()}{path.lower()}"


def _is_duplicate(a: NewsItem, b: NewsItem) -> bool:
    a_url = _canonical_url(a.url)
    b_url = _canonical_url(b.url)
    if a_url and b_url and a_url == b_url:
        return True

    a_title = _normalize_title(a.title)
    b_title = _normalize_title(b.title)
    if not a_title or not b_title:
        return False
    if a_title == b_title:
        return True

    similarity = SequenceMatcher(None, a_title, b_title).ratio()
    return similarity >= 0.93


def dedupe_items(items: List[NewsItem]) -> Tuple[List[NewsItem], Dict[str, int]]:
    unique: List[NewsItem] = []
    duplicates_removed = 0

    for item in items:
        dup_index = -1
        for idx, seen in enumerate(unique):
            if _is_duplicate(item, seen):
                dup_index = idx
                break

        if dup_index == -1:
            unique.append(item)
            continue

        duplicates_removed += 1
        existing = unique[dup_index]
        if len(item.summary) > len(existing.summary):
            existing.summary = item.summary
        if not existing.url and item.url:
            existing.url = item.url
        if item.published_at and (not existing.published_at or item.published_at > existing.published_at):
            existing.published_at = item.published_at

    stats = {
        "raw_items": len(items),
        "unique_items": len(unique),
        "duplicates_removed": duplicates_removed,
    }
    return unique, stats
