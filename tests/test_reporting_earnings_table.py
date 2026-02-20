from active_info.models import AnalysisResult
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

    assert "## 3) 机会跟踪清单（趋势 + Watchlist）" in md
    assert "| 趋势A |" in md
    assert "| 跟踪B |" in md
    # merged section should dedupe repeated items
    assert md.count("共同条目") == 1
    assert "财报雷达" not in md
    assert "## Watchlist" not in md
