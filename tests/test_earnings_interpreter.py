from types import SimpleNamespace

from active_info.earnings_interpreter import EarningsRadarInterpreter
from active_info.models import NewsItem


def _settings_stub() -> SimpleNamespace:
    return SimpleNamespace(
        analysis_provider="heuristic",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )


def test_earnings_interpreter_heuristic_outputs_required_fields() -> None:
    interpreter = EarningsRadarInterpreter(_settings_stub())
    items = [
        NewsItem(
            title="MSFT filed 10-Q (2026-01-28)",
            url="https://example.com/10q",
            source="SEC Filing",
            category="earnings",
            summary="record growth with strong guidance raise",
        )
    ]

    out = interpreter.interpret(items)
    assert len(out) == 1
    row = out[0]
    for key in [
        "event_one_liner",
        "sentiment",
        "impact_target",
        "why_important",
        "suggested_action",
    ]:
        assert key in row and row[key]
    assert row["suggested_action"] in {"跟踪", "忽略"}
