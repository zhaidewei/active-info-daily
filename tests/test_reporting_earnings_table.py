from active_info.models import AnalysisResult
from active_info.models import NewsItem
from active_info.reporting import build_markdown


def test_followups_merge_overlooked_and_watchlist() -> None:
    analysis = AnalysisResult(
        overview="overview",
        breakthroughs=["a"],
        investment_signals=["b"],
        overlooked_trends=["共同条目", "趋势A"],
        watchlist=["共同条目", "跟踪B"],
    )

    md = build_markdown(
        report_date="2026-02-20",
        analysis=analysis,
        top_items=[],
    )

    assert "## 1. 事实与新闻" in md
    assert "## 2. 可能的趋势与机会" in md
    assert "### 跨行业组合机会" in md
    assert "- 趋势A" in md
    assert "- 跟踪B" in md
    assert "_->" in md
    assert md.count("共同条目") == 1
    assert "## 3)" not in md
    assert "| --- |" not in md


def test_factual_items_force_external_source_when_top15_miss() -> None:
    analysis = AnalysisResult(
        overview="overview",
        breakthroughs=["预测市场平台Polymarket与Substack合作，为内容创作者提供数据工具和赞助机会。"],
        investment_signals=[],
        overlooked_trends=[],
        watchlist=[],
    )

    top_items = [
        NewsItem(
            title="Unrelated top item",
            url="https://example.com/top",
            source="Top",
            category="it",
            summary="nothing relevant",
            score=9.0,
        )
    ]
    all_items = [
        NewsItem(
            title="Substack updates partnership with Polymarket",
            url="https://example.com/poly-substack",
            source="Substack",
            category="prediction_market",
            summary="native tools for creators",
            score=3.0,
        )
    ]

    md = build_markdown(
        report_date="2026-02-20",
        analysis=analysis,
        top_items=top_items,
        all_items_for_refs=all_items,
    )

    assert "来源补充" in md
    assert "https://example.com/poly-substack" in md
