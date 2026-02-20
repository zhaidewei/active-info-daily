from active_info.models import NewsItem
from active_info.pipeline import _cap_source_items


def _item(title: str, source: str, score: float) -> NewsItem:
    return NewsItem(title=title, url="https://example.com", source=source, category="earnings", score=score)


def test_cap_source_items_limits_sec_filing_to_5() -> None:
    items = [
        _item("SEC-1", "SEC Filing", 9.0),
        _item("SEC-2", "SEC Filing", 8.0),
        _item("O-1", "Cointelegraph", 7.9),
        _item("SEC-3", "SEC Filing", 7.8),
        _item("SEC-4", "SEC Filing", 7.7),
        _item("SEC-5", "SEC Filing", 7.6),
        _item("SEC-6", "SEC Filing", 7.5),
        _item("O-2", "Bankless", 7.4),
    ]

    out = _cap_source_items(items, source_name="SEC Filing", cap=5)
    sec_count = sum(1 for x in out if x.source == "SEC Filing")
    titles = [x.title for x in out]

    assert sec_count == 5
    assert "SEC-6" not in titles
    assert "O-1" in titles and "O-2" in titles
