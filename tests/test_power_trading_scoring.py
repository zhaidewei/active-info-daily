from active_info.models import NewsItem
from active_info.scoring import score_items


def test_power_trading_keywords_get_higher_score() -> None:
    items = [
        NewsItem(
            title="ERCOT power market sees LMP spike amid transmission congestion",
            url="https://example.com/power",
            source="PowerFeed",
            category="power_trading",
            summary="capacity market and battery storage improve ancillary services",
        ),
        NewsItem(
            title="General company update",
            url="https://example.com/general",
            source="GeneralFeed",
            category="general",
            summary="routine operations",
        ),
    ]

    ranked = score_items(items)
    assert ranked[0].category == "power_trading"
    assert ranked[0].score > ranked[1].score
