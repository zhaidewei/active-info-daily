from active_info.models import AnalysisResult, NewsItem
from active_info.pipeline import (
    _apply_repeat_penalty,
    _deprioritize_recent_urls,
    _suppress_cross_report_repeats,
)


def test_apply_repeat_penalty_reorders_repeated_items() -> None:
    items = [
        NewsItem(
            title="Repeat headline",
            url="https://example.com/repeat",
            source="A",
            category="web3",
            score=9.0,
        ),
        NewsItem(
            title="Fresh headline",
            url="https://example.com/fresh",
            source="B",
            category="ai",
            score=8.4,
        ),
    ]
    out = _apply_repeat_penalty(
        items,
        repeated_urls={"https://example.com/repeat"},
        repeated_titles={"repeatheadline"},
        penalty=1.2,
    )
    assert out[0].title == "Fresh headline"
    assert out[0].score > out[1].score


def test_suppress_cross_report_repeats_filters_analysis_lines() -> None:
    analysis = AnalysisResult(
        overview="o",
        breakthroughs=["同一事件A", "新增事件B"],
        investment_signals=["重复信号C", "新增信号D"],
        overlooked_trends=["重复趋势E", "新增趋势F"],
        watchlist=["重复跟踪G", "新增跟踪H"],
    )
    recent_lines = {"同一事件a", "重复信号c", "重复趋势e", "重复跟踪g"}

    out = _suppress_cross_report_repeats(analysis, recent_lines=recent_lines)
    assert "新增事件B" in out.breakthroughs
    assert "重复信号C" not in out.investment_signals
    assert "新增趋势F" in out.overlooked_trends
    assert "重复跟踪G" not in out.watchlist


def test_deprioritize_recent_urls_limits_reused_items_in_front() -> None:
    items = [
        NewsItem(title=f"Repeat {i}", url=f"https://example.com/r{i}", source="A", category="web3", score=10.0 - i)
        for i in range(4)
    ]
    items += [
        NewsItem(title=f"Fresh {i}", url=f"https://example.com/f{i}", source="B", category="ai", score=9.0 - i)
        for i in range(4)
    ]
    ranked = sorted(items, key=lambda x: x.score, reverse=True)
    out = _deprioritize_recent_urls(
        ranked,
        repeated_urls={f"https://example.com/r{i}" for i in range(4)},
        max_reused_in_front=2,
        front_size=6,
    )
    front = out[:6]
    reused = [item for item in front if item.url and item.url.startswith("https://example.com/r")]
    assert len(reused) <= 2
