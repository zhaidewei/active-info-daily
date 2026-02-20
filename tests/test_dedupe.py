from active_info.dedupe import dedupe_items
from active_info.models import NewsItem


def test_dedupe_merges_similar_items() -> None:
    items = [
        NewsItem(
            title="NVIDIA launches new Blackwell inference stack",
            url="https://example.com/news?id=1",
            source="S1",
            category="ai",
            summary="brief",
        ),
        NewsItem(
            title="NVIDIA launches new Blackwell inference stack!",
            url="https://example.com/news?id=1&utm=feed",
            source="S2",
            category="ai",
            summary="this summary is longer and should be kept",
        ),
        NewsItem(
            title="Different story",
            url="https://example.com/other",
            source="S3",
            category="it",
            summary="other",
        ),
    ]

    unique, stats = dedupe_items(items)

    assert len(unique) == 2
    assert stats["duplicates_removed"] == 1
    assert "longer" in unique[0].summary
