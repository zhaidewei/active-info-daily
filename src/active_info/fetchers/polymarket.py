from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
from dateutil import parser as date_parser

from active_info.models import NewsItem

POLYMARKET_API = "https://gamma-api.polymarket.com/markets"


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def fetch_polymarket_items(config: dict[str, Any], timeout: int = 15) -> list[NewsItem]:
    if not config.get("enabled", False):
        return []

    limit = int(config.get("limit", 40))
    min_volume = float(config.get("min_volume", 20000))
    params = {"limit": limit, "closed": "false"}

    try:
        response = requests.get(POLYMARKET_API, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    items: list[NewsItem] = []
    for market in payload:
        volume = _to_float(market.get("volume") or market.get("volumeNum"))
        if volume < min_volume:
            continue

        question = str(market.get("question") or "Polymarket signal")
        slug = str(market.get("slug") or "")
        link = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com"
        end_date = market.get("endDate") or market.get("end_date_iso")
        parsed_end = None
        if end_date:
            try:
                parsed_end = date_parser.parse(str(end_date))
            except (ValueError, TypeError, OverflowError):
                parsed_end = None

        summary = (
            f"Market volume: {volume:.0f}. "
            f"Liquidity: {_to_float(market.get('liquidity') or market.get('liquidityNum')):.0f}."
        )

        items.append(
            NewsItem(
                title=question,
                url=link,
                source="Polymarket",
                category="prediction_market",
                summary=summary,
                published_at=parsed_end or datetime.utcnow(),
            )
        )

    return items
