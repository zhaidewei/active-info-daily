from active_info.models import NewsItem
from active_info.trends import apply_trend_resonance


def test_trend_resonance_adds_bonus_and_generates_rows() -> None:
    items = [
        NewsItem(
            title="AI agent deployment expands in enterprise",
            url="https://example.com/1",
            source="SourceA",
            category="ai",
            summary="agent and enterprise adoption",
            score=1.0,
        ),
        NewsItem(
            title="Another enterprise adopts autonomous agent workflow",
            url="https://example.com/2",
            source="SourceB",
            category="it",
            summary="autonomous copilot contract",
            score=1.0,
        ),
    ]

    ranked, trend_rows = apply_trend_resonance(items)

    assert ranked[0].score > 1.0
    assert trend_rows
    assert any("AI智能体" in row or "企业落地" in row for row in trend_rows)
