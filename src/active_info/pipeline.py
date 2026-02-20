from __future__ import annotations

import json
from datetime import date, datetime
from typing import Dict, List, Optional, Union

from active_info.analysis import Analyzer
from active_info.config import Settings
from active_info.dedupe import dedupe_items
from active_info.fetchers.context import fetch_article_context
from active_info.fetchers.polymarket import fetch_polymarket_items
from active_info.fetchers.rss import fetch_rss_items
from active_info.fetchers.sec_filings import fetch_sec_filings
from active_info.innovation_curator import InnovationCurator
from active_info.models import NewsItem
from active_info.reporting import build_json_payload, build_markdown
from active_info.scoring import score_items
from active_info.source_loader import load_source_config
from active_info.storage import ReportStorage, build_report
from active_info.translation import ReportTranslator


def _serialize_item(item: NewsItem) -> Dict[str, Union[str, float, None]]:
    return {
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "category": item.category,
        "summary": item.summary,
        "score": item.score,
        "published_at": item.published_at.isoformat() if item.published_at else None,
    }


def _deserialize_item(row: dict) -> NewsItem:
    published_at = None
    raw_time = row.get("published_at")
    if raw_time:
        try:
            published_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except Exception:
            published_at = None

    score_val = row.get("score", 0.0)
    try:
        score = float(score_val)
    except Exception:
        score = 0.0

    return NewsItem(
        title=str(row.get("title", "")),
        url=str(row.get("url", "")),
        source=str(row.get("source", "")),
        category=str(row.get("category", "general")),
        summary=str(row.get("summary", "")),
        score=score,
        published_at=published_at,
    )


def _snapshot_path(settings: Settings, date_key: str):
    return settings.snapshot_dir / f"{date_key}.download.json"


def _collect_source_items(settings: Settings) -> List[NewsItem]:
    source_cfg = load_source_config(settings.source_config_path)
    rss_feeds = list(source_cfg.get("rss", [])) + list(source_cfg.get("twitter_rss", []))

    rss_items = fetch_rss_items(rss_feeds, max_items=settings.report_max_items)
    polymarket_items = fetch_polymarket_items(
        source_cfg.get("polymarket", {}),
        timeout=settings.request_timeout_sec,
    )
    sec_items = fetch_sec_filings(
        source_cfg.get("sec_filings", {}),
        timeout=settings.request_timeout_sec,
    )
    return rss_items + polymarket_items + sec_items


def _write_download_snapshot(settings: Settings, date_key: str, items: List[NewsItem]) -> str:
    snap_path = _snapshot_path(settings, date_key)
    payload = {
        "report_date": date_key,
        "fetched_at": datetime.utcnow().isoformat(),
        "total_downloaded": len(items),
        "items": [_serialize_item(item) for item in items],
    }
    snap_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(snap_path)


def _load_download_snapshot(settings: Settings, date_key: str) -> List[NewsItem]:
    snap_path = _snapshot_path(settings, date_key)
    if not snap_path.exists():
        raise ValueError(f"Download snapshot not found: {snap_path}")

    payload = json.loads(snap_path.read_text(encoding="utf-8"))
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise ValueError(f"Invalid snapshot format: {snap_path}")

    items: List[NewsItem] = []
    for row in rows:
        if isinstance(row, dict):
            items.append(_deserialize_item(row))
    return items


def _latest_snapshot_date_key(settings: Settings) -> str:
    snapshots = sorted(settings.snapshot_dir.glob("*.download.json"))
    if not snapshots:
        raise ValueError("No download snapshots found. Please run fetch-only first.")
    latest = snapshots[-1]
    name = latest.name.replace(".download.json", "")
    return name


def _shortlist_for_llm(settings: Settings, ranked_items: List[NewsItem]) -> List[NewsItem]:
    enrich_context = settings.analysis_provider.lower() in {"openai", "deepseek"}
    shortlist: List[NewsItem] = []
    for item in ranked_items[: settings.llm_input_items]:
        if enrich_context and settings.jina_reader_enabled and item.url.startswith("http"):
            context = fetch_article_context(item.url, timeout=settings.request_timeout_sec)
            if context:
                item.summary = (item.summary + "\n" + context).strip()[:1600]
        shortlist.append(item)
    return shortlist


def _cap_source_items(items: List[NewsItem], source_name: str, cap: int) -> List[NewsItem]:
    if cap < 0:
        return items
    kept: List[NewsItem] = []
    source_count = 0
    for item in items:
        if item.source == source_name:
            if source_count >= cap:
                continue
            source_count += 1
        kept.append(item)
    return kept


def _render_and_store(
    settings: Settings,
    report_storage: ReportStorage,
    date_key: str,
    all_items: List[NewsItem],
) -> Dict[str, Union[str, int]]:
    deduped_items, ingest_stats = dedupe_items(all_items)

    ranked = score_items(deduped_items, settings=settings)
    ranked = _cap_source_items(ranked, source_name="SEC Filing", cap=5)
    llm_items = _shortlist_for_llm(settings, ranked)

    analyzer = Analyzer(
        provider=settings.analysis_provider,
        openai_api_key=settings.openai_api_key,
        openai_model=settings.openai_model,
        deepseek_api_key=settings.deepseek_api_key,
        deepseek_model=settings.deepseek_model,
        deepseek_base_url=settings.deepseek_base_url,
        deepseek_strict_model=settings.deepseek_strict_model,
    )
    analysis = analyzer.analyze(date_key, llm_items)
    analysis.overview = str(analysis.overview).strip()
    analysis = InnovationCurator(settings).curate(analysis, llm_items)

    top_items = ranked[:15]
    power_focus = [item for item in ranked if item.category == "power_trading"][:8]

    markdown = build_markdown(
        date_key,
        analysis,
        top_items,
        all_items_for_refs=ranked,
        ingest_stats=ingest_stats,
    )
    translations = ReportTranslator(settings).translate_markdown(markdown)
    json_content = build_json_payload(
        date_key,
        analysis,
        top_items,
        analysis_input_items=llm_items,
        ingest_stats=ingest_stats,
        translations=translations,
        power_focus=power_focus,
        power_insights=[],
    )

    report = build_report(
        date_key=date_key,
        total_items=ingest_stats["unique_items"],
        markdown=markdown,
        json_content=json_content,
    )
    report_storage.upsert_report(report)

    md_path = settings.report_dir / f"{date_key}.md"
    json_path = settings.report_dir / f"{date_key}.json"
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json_content, encoding="utf-8")

    return {
        "report_date": date_key,
        "total_items": ingest_stats["unique_items"],
        "report_markdown": str(md_path),
        "report_json": str(json_path),
    }


def fetch_download_snapshot(settings: Settings, run_date: Optional[date] = None) -> Dict[str, Union[str, int]]:
    date_key = (run_date or date.today()).isoformat()
    all_items = _collect_source_items(settings)
    snapshot_path = _write_download_snapshot(settings, date_key, all_items)
    return {
        "report_date": date_key,
        "total_items": len(all_items),
        "snapshot_json": snapshot_path,
    }


def run_pipeline(
    settings: Settings, report_storage: ReportStorage, run_date: Optional[date] = None
) -> Dict[str, Union[str, int]]:
    date_key = (run_date or date.today()).isoformat()
    all_items = _collect_source_items(settings)
    _write_download_snapshot(settings, date_key, all_items)
    return _render_and_store(settings, report_storage, date_key, all_items)


def rerun_analysis_from_snapshot(
    settings: Settings, report_storage: ReportStorage, report_date: Optional[str] = None
) -> Dict[str, Union[str, int]]:
    date_key = report_date or _latest_snapshot_date_key(settings)
    all_items = _load_download_snapshot(settings, date_key)
    return _render_and_store(settings, report_storage, date_key, all_items)


def rerun_analysis_from_saved(
    settings: Settings, report_storage: ReportStorage, report_date: Optional[str] = None
) -> Dict[str, Union[str, int]]:
    # Backward-compatible alias. Current behavior prefers snapshot-based rerun.
    return rerun_analysis_from_snapshot(settings, report_storage, report_date=report_date)
