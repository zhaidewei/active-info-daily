from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from active_info.models import AnalysisResult, NewsItem


def _strip_bullet_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[\-\*\u2022\u00b7]+\s*", "", cleaned)
    return cleaned.strip()


def _fmt_items(items: List[str]) -> str:
    normalized = [_strip_bullet_prefix(item) for item in items if _strip_bullet_prefix(item)]
    return "\n".join(f"- {item}" for item in normalized) if normalized else "- 暂无"


def _md_cell(text: str) -> str:
    cleaned = _strip_bullet_prefix(str(text or ""))
    cleaned = cleaned.replace("\n", "<br>")
    return cleaned.replace("|", "\\|").strip()


def _merge_followups(overlooked_trends: List[str], watchlist: List[str]) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for raw in [*(overlooked_trends or []), *(watchlist or [])]:
        cleaned = _strip_bullet_prefix(raw)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        merged.append(cleaned)
    return merged


def _source_entries(top_items: List[NewsItem]) -> List[Tuple[int, NewsItem, str]]:
    entries: List[Tuple[int, NewsItem, str]] = []
    idx = 1
    for item in top_items:
        if not item.url:
            continue
        blob = f"{item.title} {item.summary} {item.source} {item.category}".lower()
        entries.append((idx, item, blob))
        idx += 1
    return entries


def _category_hint(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(k in lowered for k in ["财报", "8-k", "10-k", "10-q", "业绩", "guidance", "earnings"]):
        return "earnings"
    if any(k in lowered for k in ["电力", "电网", "ppa", "ercot", "pjm", "caiso", "容量", "储能"]):
        return "power_trading"
    if any(k in lowered for k in ["web3", "加密", "比特币", "以太坊", "solana", "链上", "token", "defi"]):
        return "web3"
    if any(k in lowered for k in ["ai", "模型", "算力", "芯片", "agent"]):
        return "ai"
    return None


def _find_related_source_refs(text: str, sources: List[Tuple[int, NewsItem, str]], limit: int = 2) -> List[Tuple[int, str]]:
    cleaned = _strip_bullet_prefix(text)
    if not cleaned:
        return []

    lowered = cleaned.lower()
    tokens = set(re.findall(r"[a-z0-9]{2,}", lowered))
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "are",
        "was",
        "will",
        "into",
        "about",
        "2026",
        "2025",
    }
    tokens = {x for x in tokens if x not in stopwords}
    ticker_like = set(re.findall(r"\b[A-Z]{2,6}\b", cleaned))
    hint = _category_hint(cleaned)

    scored: List[Tuple[float, int, str]] = []
    for idx, item, blob in sources:
        score = 0.0
        for token in tokens:
            if token in blob:
                score += 1.0
        for tk in ticker_like:
            if tk.lower() in blob:
                score += 2.0
        if hint and (item.category == hint or (hint == "ai" and item.category == "it")):
            score += 1.5
        if score > 0:
            scored.append((score, idx, item.url))

    scored.sort(key=lambda x: (-x[0], x[1]))
    refs: List[Tuple[int, str]] = []
    for _, idx, url in scored[:limit]:
        refs.append((idx, url))
    return refs


def _format_source_refs(refs: List[Tuple[int, str]]) -> str:
    if not refs:
        return ""
    joined = ", ".join(f"[#{idx}]({url})" for idx, url in refs)
    return f"（来源: {joined}）"


def _append_refs(items: List[str], sources: List[Tuple[int, NewsItem, str]], limit: int = 2) -> List[str]:
    out: List[str] = []
    for item in items:
        cleaned = _strip_bullet_prefix(item)
        if not cleaned:
            continue
        refs = _find_related_source_refs(cleaned, sources, limit=limit)
        out.append(f"{cleaned}{_format_source_refs(refs)}")
    return out


def _followup_detail(text: str) -> Tuple[str, str]:
    lowered = text.lower()
    if any(k in lowered for k in ["sec", "监管", "政策", "牌照"]):
        return "监管边际变化会改变估值锚与风险溢价。", "政策落地时间、适用范围与首批受益标的。"
    if any(k in lowered for k in ["财报", "8-k", "10-k", "10-q", "业绩"]):
        return "财报与指引变化通常先于市场预期修正。", "指引上修/下修与资本开支节奏。"
    if any(k in lowered for k in ["电力", "电网", "ppa", "ercot", "储能"]):
        return "电力供需与并网约束会传导到现货价格和公用事业估值。", "区域负荷、并网进度与容量价格变化。"
    if any(k in lowered for k in ["ai", "模型", "算力", "芯片"]):
        return "AI基础设施投入决定中期收入弹性与利润率拐点。", "算力资本开支、云需求和推理成本变化。"
    if any(k in lowered for k in ["web3", "加密", "比特币", "solana", "defi", "链上"]):
        return "链上活动与合规进度是Web3估值的重要先行指标。", "链上交易量、机构采用和监管进展。"
    return "该信号可能影响中期预期差。", "下一次公告或数据更新。"


def _build_opportunity_table(items: List[str], sources: List[Tuple[int, NewsItem, str]]) -> str:
    header = "| 机会信号 | 为什么重要 | 关注目标 | 关联原始链接 |\n| --- | --- | --- | --- |"
    rows: List[str] = []
    for raw in items:
        signal = _strip_bullet_prefix(raw)
        if not signal:
            continue
        why, action = _followup_detail(signal)
        refs = _find_related_source_refs(signal, sources, limit=3)
        ref_cell = ", ".join(f"[#{idx}]({url})" for idx, url in refs) if refs else "-"
        rows.append(
            "| "
            + " | ".join([_md_cell(signal), _md_cell(why), _md_cell(action), ref_cell])
            + " |"
        )
    if not rows:
        return header + "\n| 暂无 | - | - | - |"
    return header + "\n" + "\n".join(rows)


def build_markdown(
    report_date: str,
    analysis: AnalysisResult,
    top_items: List[NewsItem],
    ingest_stats: Optional[Dict[str, int]] = None,
) -> str:
    source_entries = _source_entries(top_items)
    sources = "\n".join(
        f"{idx}. [{item.title}]({item.url})（{item.source}, score={item.score:.1f}）"
        for idx, item, _ in source_entries
    )
    if not sources:
        sources = "1. 暂无可引用链接"

    breakthroughs = _append_refs(analysis.breakthroughs, source_entries, limit=2)
    investment_signals = _append_refs(analysis.investment_signals, source_entries, limit=2)
    followups = _merge_followups(analysis.overlooked_trends, analysis.watchlist)
    followup_table = _build_opportunity_table(followups, source_entries)

    markdown = f"""# 主动信息汇总日报 - {report_date}

## 1) IT / AI / Web3 / 电力交易 行业重大突破
{_fmt_items(breakthroughs)}

## 2) 股票投资价值积极信号
{_fmt_items(investment_signals)}

## 3) 机会跟踪清单（趋势 + Watchlist）
{followup_table}

## 重点原始链接
{sources}
"""
    return markdown.strip() + "\n"


def build_json_payload(
    report_date: str,
    analysis: AnalysisResult,
    top_items: List[NewsItem],
    analysis_input_items: Optional[List[NewsItem]] = None,
    ingest_stats: Optional[Dict[str, int]] = None,
    translations: Optional[Dict[str, str]] = None,
    power_focus: Optional[List[NewsItem]] = None,
    power_insights: Optional[List[Dict[str, str]]] = None,
) -> str:
    payload = {
        "report_date": report_date,
        "analysis": asdict(analysis),
        "ingest_stats": ingest_stats or {},
        "translations": translations or {},
        "power_focus": [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "category": item.category,
                "score": item.score,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in (power_focus or [])
        ],
        "power_insights": power_insights or [],
        "top_items": [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "category": item.category,
                "summary": item.summary,
                "score": item.score,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in top_items
        ],
        "analysis_input_items": [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                "category": item.category,
                "summary": item.summary,
                "score": item.score,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in (analysis_input_items or [])
        ],
        "generated_at": datetime.utcnow().isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
