from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from active_info.models import AnalysisResult, NewsItem

TEXT_ALIAS_MAP: Dict[str, List[str]] = {
    "代币化": ["tokenization", "tokenized"],
    "英国": ["united kingdom", "uk", "britain"],
    "加密": ["crypto", "cryptocurrency", "digital asset"],
    "链上": ["onchain", "on-chain"],
    "电力交易": ["power market", "electricity market", "power trading"],
    "预测市场": ["prediction market", "polymarket", "kalshi"],
    "内容创作者": ["creator", "substack"],
    "监管": ["regulation", "sec", "policy", "compliance"],
}


def _strip_bullet_prefix(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[\-\*\u2022\u00b7]+\s*", "", cleaned)
    return cleaned.strip()


def _fmt_items(items: List[str]) -> str:
    normalized = [_strip_bullet_prefix(item) for item in items if _strip_bullet_prefix(item)]
    return "\n".join(f"- {item}" for item in normalized) if normalized else "- 暂无"


def _merge_followups(*groups: List[str]) -> List[str]:
    merged: List[str] = []
    seen: set[str] = set()
    for group in groups:
        for raw in group or []:
            cleaned = _strip_bullet_prefix(raw)
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            merged.append(cleaned)
    return merged


def _normalize_for_match(text: str) -> str:
    cleaned = _strip_bullet_prefix(text)
    cleaned = re.sub(r"（来源:\s*.*?\）", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", cleaned.lower())
    return cleaned.strip()


def _similar_line(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) >= 10 and shorter in longer:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.63


def _exclude_similar(items: List[str], anchors: List[str]) -> List[str]:
    normalized_anchors = [_normalize_for_match(x) for x in anchors]
    out: List[str] = []
    out_norm: List[str] = []
    for raw in items:
        cleaned = _strip_bullet_prefix(raw)
        key = _normalize_for_match(cleaned)
        if not key:
            continue
        if any(_similar_line(key, anchor) for anchor in normalized_anchors if anchor):
            continue
        if any(_similar_line(key, seen) for seen in out_norm):
            continue
        out.append(cleaned)
        out_norm.append(key)
    return out


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
    for zh_key, aliases in TEXT_ALIAS_MAP.items():
        if zh_key in cleaned:
            for alias in aliases:
                tokens.update(re.findall(r"[a-z0-9]{2,}", alias.lower()))
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


def _external_source_entries(items: List[NewsItem], blocked_urls: set[str]) -> List[Tuple[NewsItem, str]]:
    entries: List[Tuple[NewsItem, str]] = []
    seen: set[str] = set(blocked_urls)
    for item in items:
        url = (item.url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        blob = f"{item.title} {item.summary} {item.source} {item.category}".lower()
        entries.append((item, blob))
    return entries


def _find_external_source_ref(text: str, entries: List[Tuple[NewsItem, str]]) -> Optional[str]:
    cleaned = _strip_bullet_prefix(text)
    if not cleaned or not entries:
        return None
    lowered = cleaned.lower()
    tokens = set(re.findall(r"[a-z0-9]{2,}", lowered))
    for zh_key, aliases in TEXT_ALIAS_MAP.items():
        if zh_key in cleaned:
            for alias in aliases:
                tokens.update(re.findall(r"[a-z0-9]{2,}", alias.lower()))
    if "polymarket" in lowered or "substack" in lowered:
        tokens.update({"polymarket", "substack"})
    if "英国" in cleaned:
        tokens.update({"united", "kingdom", "uk"})

    best_url: Optional[str] = None
    best_score = 0.0
    for item, blob in entries:
        score = 0.0
        for token in tokens:
            if token in blob:
                score += 1.0
        if score > best_score:
            best_score = score
            best_url = item.url
    if best_score <= 0:
        return None
    return best_url


def _append_refs(
    items: List[str],
    sources: List[Tuple[int, NewsItem, str]],
    limit: int = 2,
    fallback_external_items: Optional[List[NewsItem]] = None,
    force_source: bool = False,
) -> List[str]:
    blocked = {item.url for _, item, _ in sources if item.url}
    external_entries = _external_source_entries(fallback_external_items or [], blocked_urls=blocked)
    out: List[str] = []
    for item in items:
        cleaned = _strip_bullet_prefix(item)
        if not cleaned:
            continue
        refs = _find_related_source_refs(cleaned, sources, limit=limit)
        suffix = _format_source_refs(refs)
        if not suffix and force_source:
            external_url = _find_external_source_ref(cleaned, external_entries)
            if external_url:
                suffix = f"（来源补充: [外部链接]({external_url})）"
        out.append(f"{cleaned}{suffix}")
    return out


def _opportunity_insight(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["sec", "监管", "政策", "牌照"]):
        return "监管边际放松或规则清晰化，常带来估值体系重定价。"
    if any(k in lowered for k in ["财报", "8-k", "10-k", "10-q", "业绩"]):
        return "财报与指引改善会形成预期差，推动市场对中期增长重新定价。"
    if any(k in lowered for k in ["电力", "电网", "ppa", "ercot", "储能"]):
        return "AI负荷增长与电力市场机制变化正在重塑能源资产和公用事业估值。"
    if any(k in lowered for k in ["ai", "模型", "算力", "芯片"]):
        return "技术迭代与成本下降会加快应用落地，扩大产业链收益面。"
    if any(k in lowered for k in ["web3", "加密", "比特币", "solana", "defi", "链上"]):
        return "链上合规化与机构化推进，可能带来新一轮资产与流量迁移。"
    return "需求增量或新商业模式，具备中期机会价值。"


def _opportunity_theme(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["web3", "加密", "比特币", "solana", "ethereum", "链上", "token", "defi"]):
        return "Web3 与链上金融"
    if any(k in lowered for k in ["电力", "电网", "ppa", "ercot", "pjm", "caiso", "储能", "并网"]):
        return "电力交易与能源基础设施"
    if any(k in lowered for k in ["ai", "模型", "芯片", "算力", "agent", "cloud", "infra"]):
        return "AI / IT 与新基础设施"
    if any(k in lowered for k in ["监管", "政策", "sec", "牌照", "合规"]):
        return "制度与监管红利"
    return "跨行业组合机会"


def _build_opportunity_outline(items: List[str], sources: List[Tuple[int, NewsItem, str]]) -> str:
    grouped: Dict[str, List[Tuple[str, str]]] = {}
    order: List[str] = []
    for raw in items:
        signal = _strip_bullet_prefix(raw)
        if not signal:
            continue
        refs = _find_related_source_refs(signal, sources, limit=2)
        line = f"{signal}{_format_source_refs(refs)}"
        theme = _opportunity_theme(signal)
        insight = _opportunity_insight(signal)
        if theme not in grouped:
            grouped[theme] = []
            order.append(theme)
        grouped[theme].append((line, insight))

    if not order:
        return "- 暂无"

    blocks: List[str] = []
    for theme in order:
        blocks.append(f"### {theme}")
        for line, insight in grouped.get(theme, []):
            blocks.append(f"- {line}")
            blocks.append(f"  - _-> {insight}_")
    return "\n".join(blocks)


def build_markdown(
    report_date: str,
    analysis: AnalysisResult,
    top_items: List[NewsItem],
    all_items_for_refs: Optional[List[NewsItem]] = None,
    ingest_stats: Optional[Dict[str, int]] = None,
) -> str:
    source_entries = _source_entries(top_items)
    sources = "\n".join(
        f"{idx}. [{item.title}]({item.url})（{item.source}, score={item.score:.1f}）"
        for idx, item, _ in source_entries
    )
    if not sources:
        sources = "1. 暂无可引用链接"

    factual_base = _merge_followups(analysis.breakthroughs, analysis.investment_signals)
    factual_items = _append_refs(
        factual_base,
        source_entries,
        limit=2,
        fallback_external_items=all_items_for_refs,
        force_source=True,
    )

    opportunity_candidates = _merge_followups(
        analysis.investment_signals,
        analysis.overlooked_trends,
        analysis.watchlist,
    )
    opportunity_items = _exclude_similar(opportunity_candidates, factual_base)
    opportunity_outline = _build_opportunity_outline(opportunity_items, source_entries)

    markdown = f"""# 乐观者的主动信息汇总 - {report_date}

## 1. 事实与新闻
{_fmt_items(factual_items)}

## 2. 可能的趋势与机会
{opportunity_outline}

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
