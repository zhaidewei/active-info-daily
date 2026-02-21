from types import SimpleNamespace

from active_info.translation import ReportTranslator


def _settings_stub() -> SimpleNamespace:
    return SimpleNamespace(
        translation_enabled=True,
        analysis_provider="deepseek",
        translation_max_chars=9000,
        deepseek_api_key="test-key",
        deepseek_model="deepseek-reasoner",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_strict_model=True,
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )


def test_translate_source_link_labels_for_zh(monkeypatch) -> None:
    translator = ReportTranslator(_settings_stub())
    translator.client = object()
    translator.model = "deepseek-reasoner"

    def fake_translate_lines(lines, target_language):  # type: ignore[no-untyped-def]
        assert target_language == "Simplified Chinese"
        return ["今日加密市场回顾", "Matrixdock将XAUm引入Solana"]

    monkeypatch.setattr(translator, "_translate_lines", fake_translate_lines)

    md = (
        "# 乐观者的主动信息汇总 - 2026-02-20\n\n"
        "## 重点原始链接\n"
        "1. [Here’s what happened in crypto today](https://example.com/a)\n"
        "2. [Matrixdock Brings XAUm to Solana](https://example.com/b)\n"
    )
    out = translator._translate_source_link_labels(md, target_language="Simplified Chinese")
    assert "[今日加密市场回顾](https://example.com/a)" in out
    assert "[Matrixdock将XAUm引入Solana](https://example.com/b)" in out
