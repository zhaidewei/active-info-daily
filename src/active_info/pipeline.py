from __future__ import annotations

import json
from datetime import date, datetime
import re
from difflib import SequenceMatcher
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
from active_info.models import AnalysisResult


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


def _normalize_text_signature(text: str) -> str:
    cleaned = (text or "").strip().lower()
    cleaned = re.sub(r"（来源[:：].*?）", "", cleaned)
    cleaned = re.sub(r"\(source:.*?\)", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", cleaned)
    return cleaned.strip()


def _collect_recent_signatures(
    report_storage: ReportStorage,
    date_key: str,
    lookback_reports: int,
) -> Dict[str, set[str]]:
    if lookback_reports <= 0:
        return {"urls": set(), "titles": set(), "analysis_lines": set()}

    rows = report_storage.list_reports(limit=max(20, lookback_reports * 6))
    picked = [row for row in rows if str(row.get("report_date", "")) < date_key][:lookback_reports]
    recent_urls: set[str] = set()
    recent_titles: set[str] = set()
    recent_lines: set[str] = set()

    for row in picked:
        report_date = str(row.get("report_date", ""))
        if not report_date:
            continue
        report = report_storage.get_report(report_date)
        if not report:
            continue
        try:
            payload = json.loads(str(report.get("json_content", "{}") or "{}"))
        except Exception:
            continue
        for item in payload.get("top_items", []) or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if url:
                recent_urls.add(url)
            if title:
                recent_titles.add(_normalize_text_signature(title))

        analysis = payload.get("analysis", {}) or {}
        for key in ("breakthroughs", "investment_signals", "overlooked_trends", "watchlist"):
            rows2 = analysis.get(key, []) or []
            if not isinstance(rows2, list):
                continue
            for raw in rows2:
                line = str(raw or "").strip()
                sig = _normalize_text_signature(line)
                if sig:
                    recent_lines.add(sig)

    return {"urls": recent_urls, "titles": recent_titles, "analysis_lines": recent_lines}


def _apply_repeat_penalty(
    ranked: List[NewsItem],
    repeated_urls: set[str],
    repeated_titles: set[str],
    penalty: float,
) -> List[NewsItem]:
    if penalty <= 0:
        return ranked
    out: List[NewsItem] = []
    for item in ranked:
        score = float(item.score)
        if item.url and item.url in repeated_urls:
            score -= penalty
        title_sig = _normalize_text_signature(item.title)
        if title_sig and title_sig in repeated_titles:
            score -= penalty * 0.7
        item.score = score
        out.append(item)
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def _deprioritize_recent_urls(
    ranked: List[NewsItem],
    repeated_urls: set[str],
    max_reused_in_front: int,
    front_size: int,
) -> List[NewsItem]:
    if not ranked or not repeated_urls:
        return ranked
    if max_reused_in_front < 0:
        return ranked

    front_target = max(1, front_size)
    front: List[NewsItem] = []
    overflow: List[NewsItem] = []
    reused_count = 0

    for item in ranked:
        is_reused = bool(item.url and item.url in repeated_urls)
        if len(front) < front_target:
            if is_reused and reused_count >= max_reused_in_front:
                overflow.append(item)
                continue
            front.append(item)
            if is_reused:
                reused_count += 1
            continue
        overflow.append(item)

    # If there are not enough fresh items, fill remaining slots from overflow.
    if len(front) < front_target and overflow:
        refill: List[NewsItem] = []
        for item in overflow:
            if len(front) < front_target:
                front.append(item)
            else:
                refill.append(item)
        overflow = refill

    return front + overflow


def _line_is_repeated(sig: str, history: set[str]) -> bool:
    if not sig:
        return False
    if sig in history:
        return True
    for old in history:
        if not old:
            continue
        if len(sig) >= 12 and sig in old:
            return True
        if len(old) >= 12 and old in sig:
            return True
        if SequenceMatcher(None, sig, old).ratio() >= 0.82:
            return True
    return False


def _filter_repeated_lines(lines: List[str], history: set[str], keep_fallback: int = 1) -> List[str]:
    out: List[str] = []
    for raw in lines or []:
        line = str(raw or "").strip()
        sig = _normalize_text_signature(line)
        if not line or _line_is_repeated(sig, history):
            continue
        out.append(line)
    if out:
        return out
    return [str(x) for x in (lines or [])[:keep_fallback]]


def _suppress_cross_report_repeats(analysis: AnalysisResult, recent_lines: set[str]) -> AnalysisResult:
    if not recent_lines:
        return analysis
    analysis.breakthroughs = _filter_repeated_lines(analysis.breakthroughs, recent_lines, keep_fallback=2)
    analysis.investment_signals = _filter_repeated_lines(analysis.investment_signals, recent_lines, keep_fallback=2)
    analysis.overlooked_trends = _filter_repeated_lines(analysis.overlooked_trends, recent_lines, keep_fallback=2)
    analysis.watchlist = _filter_repeated_lines(analysis.watchlist, recent_lines, keep_fallback=2)
    return analysis


def _render_and_store(
    settings: Settings,
    report_storage: ReportStorage,
    date_key: str,
    all_items: List[NewsItem],
) -> Dict[str, Union[str, int]]:
    deduped_items, ingest_stats = dedupe_items(all_items)
    recent = _collect_recent_signatures(
        report_storage,
        date_key=date_key,
        lookback_reports=settings.novelty_lookback_reports,
    )

    ranked = score_items(deduped_items, settings=settings)
    ranked = _apply_repeat_penalty(
        ranked,
        repeated_urls=recent["urls"],
        repeated_titles=recent["titles"],
        penalty=settings.novelty_repeat_penalty,
    )
    ranked = _deprioritize_recent_urls(
        ranked,
        repeated_urls=recent["urls"],
        max_reused_in_front=settings.novelty_max_reused_items_in_front,
        front_size=max(15, settings.llm_input_items),
    )
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
    analysis = _suppress_cross_report_repeats(analysis, recent_lines=recent["analysis_lines"])

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
