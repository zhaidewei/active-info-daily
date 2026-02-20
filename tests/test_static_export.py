import json
from types import SimpleNamespace

from active_info.static_export import export_static_site


def test_export_static_site_writes_index_and_report(tmp_path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "translations": {
            "zh_markdown": "# 主动信息汇总日报 - 2026-02-20\n\n## A\n- 条目",
            "en_markdown": "# Active Info Daily - 2026-02-20\n\n## A\n- item",
        },
        "ingest_stats": {"raw_items": 10, "unique_items": 8, "duplicates_removed": 2},
    }
    (report_dir / "2026-02-20.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings_stub = SimpleNamespace(report_dir=report_dir)
    out_dir = tmp_path / "site"
    result = export_static_site(settings_stub, out_dir)

    assert result["reports"] == "1"
    assert (out_dir / "index.html").exists()
    report_html = out_dir / "reports" / "2026-02-20" / "index.html"
    assert report_html.exists()
    text = report_html.read_text(encoding="utf-8")
    assert "数据来源·（原始抓取 10，去重后 8，重复移除 2）·" in text
    assert "主动信息汇总日报 - 2026-02-20" in text
