from types import SimpleNamespace

from active_info.innovation_curator import InnovationCurator
from active_info.models import AnalysisResult


def _settings_stub() -> SimpleNamespace:
    return SimpleNamespace(
        analysis_provider="heuristic",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )


def test_apply_prioritized_trends_prepends_and_dedupes() -> None:
    existing = ["A", "B", "C"]
    prioritized = ["B", "X", "Y"]
    out = InnovationCurator._apply_prioritized_trends(existing, prioritized, limit=8)
    assert out == ["B", "X", "Y", "A", "C"]


def test_curate_no_client_keeps_analysis_unchanged() -> None:
    curator = InnovationCurator(_settings_stub())
    analysis = AnalysisResult(
        overview="o",
        breakthroughs=[],
        investment_signals=[],
        overlooked_trends=["T1"],
        watchlist=["W1"],
    )
    out = curator.curate(analysis, [])
    assert out.overlooked_trends == ["T1"]
