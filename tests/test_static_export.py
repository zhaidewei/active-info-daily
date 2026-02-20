import json
from types import SimpleNamespace

from active_info.static_export import export_static_site


def test_export_static_site_writes_index_and_report(tmp_path) -> None:
    report_dir = tmp_path / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "translations": {
            "zh_markdown": "# 乐观者的主动信息汇总 - 2026-02-20\n\n## A\n- 条目",
            "en_markdown": "# Active Info Daily - 2026-02-20\n\n## A\n- item",
        },
        "ingest_stats": {"raw_items": 10, "unique_items": 8, "duplicates_removed": 2},
    }
    (report_dir / "2026-02-20.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings_stub = SimpleNamespace(report_dir=report_dir)
    out_dir = tmp_path / "site"
    result = export_static_site(settings_stub, out_dir, site_url="https://demo.example.com")

    assert result["reports"] == "1"
    assert (out_dir / "index.html").exists()
    report_html = out_dir / "reports" / "2026-02-20" / "index.html"
    assert report_html.exists()
    text = report_html.read_text(encoding="utf-8")
    assert "数据来源·（原始抓取 10，去重后 8，重复移除 2）·" in text
    assert "乐观者的主动信息汇总 - 2026-02-20" in text
    assert "被动刷流量放大焦虑" in text

    rss_path = out_dir / "rss.xml"
    assert rss_path.exists()
    rss_text = rss_path.read_text(encoding="utf-8")
    assert "<title>乐观者的主动信息汇总</title>" in rss_text
    assert "<link>https://demo.example.com/reports/2026-02-20</link>" in rss_text
    assert result["rss"].endswith("rss.xml")
