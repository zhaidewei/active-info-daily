from types import SimpleNamespace

from active_info.models import NewsItem
from active_info.power_interpreter import PowerRadarInterpreter


def _settings_stub() -> SimpleNamespace:
    return SimpleNamespace(
        analysis_provider="heuristic",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )


def test_power_interpreter_heuristic_outputs_insight_fields() -> None:
    interpreter = PowerRadarInterpreter(_settings_stub())
    items = [
        NewsItem(
            title="Batch Study Job No. 1 for ERCOT Stakeholders",
            url="https://example.com/ercot",
            source="RTO Insider",
            category="power_trading",
            summary="ERCOT interconnection queue and congestion updates",
        )
    ]

    out = interpreter.interpret(items)
    assert len(out) == 1
    row = out[0]
    for key in ["event_one_liner", "core_signal", "trading_implication", "why_important", "suggested_action"]:
        assert row.get(key)
    assert row["suggested_action"] in {"跟踪", "忽略"}


def test_power_interpreter_parse_concatenated_json_objects() -> None:
    interpreter = PowerRadarInterpreter(_settings_stub())
    raw = """
{"id":1,"event_one_liner":"A","core_signal":"S1","trading_implication":"T1","why_important":"W1","suggested_action":"跟踪"}
{"id":2,"event_one_liner":"B","core_signal":"S2","trading_implication":"T2","why_important":"W2","suggested_action":"忽略"}
""".strip()

    rows = interpreter._parse_llm_payload(raw)
    assert len(rows) == 2
    assert rows[0]["event_one_liner"] == "A"
    assert rows[1]["event_one_liner"] == "B"
