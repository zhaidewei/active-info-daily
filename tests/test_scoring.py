from active_info.models import NewsItem
from active_info.scoring import score_items


def test_score_items_prioritizes_keyword_rich_items() -> None:
    items = [
        NewsItem(
            title="Company posts record revenue and profit after AI contract",
            url="https://example.com/a",
            source="A",
            category="earnings",
            summary="guidance raise and partnership",
        ),
        NewsItem(
            title="Generic update",
            url="https://example.com/b",
            source="B",
            category="general",
            summary="minor event",
        ),
    ]

    ranked = score_items(items)
    assert ranked[0].title.startswith("Company posts")
    assert ranked[0].score > ranked[1].score
