from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import feedparser
from dateutil import parser as date_parser

from active_info.models import NewsItem


def _parse_date(entry: Any) -> Optional[datetime]:
    for key in ("published", "updated", "created"):
        raw = getattr(entry, key, None)
        if raw:
            try:
                return date_parser.parse(raw)
            except (ValueError, TypeError, OverflowError):
                continue
    return None


def _normalize_text(text: str, max_len: int = 220) -> str:
    compact = " ".join(text.split()).strip()
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 1].rstrip() + "…"


def fetch_rss_items(feeds: list[dict[str, Any]], max_items: int) -> list[NewsItem]:
    per_feed_items: list[list[NewsItem]] = []
    per_feed_cap = max(4, min(18, (max_items // max(1, len(feeds))) + 6))

    for feed in feeds:
        url = feed.get("url")
        if not url:
            continue
        parsed = feedparser.parse(url)
        source_name = feed.get("name") or url
        category = feed.get("category", "general")

        current_feed_items: list[NewsItem] = []
        for entry in parsed.entries[:per_feed_cap]:
            title = getattr(entry, "title", "(untitled)")
            link = getattr(entry, "link", "")
            summary = getattr(entry, "summary", "")
            current_feed_items.append(
                NewsItem(
                    title=_normalize_text(title),
                    url=link.strip(),
                    source=source_name,
                    category=category,
                    summary=_normalize_text(summary, max_len=500),
                    published_at=_parse_date(entry),
                )
            )
        if current_feed_items:
            per_feed_items.append(current_feed_items)

    # Round-robin merge to avoid early feeds taking all slots.
    merged: list[NewsItem] = []
    while len(merged) < max_items:
        progressed = False
        for bucket in per_feed_items:
            if bucket:
                merged.append(bucket.pop(0))
                progressed = True
                if len(merged) >= max_items:
                    break
        if not progressed:
            break

    return merged
