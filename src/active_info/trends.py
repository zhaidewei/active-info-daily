from __future__ import annotations

from typing import Dict, List, Set, Tuple

from active_info.models import NewsItem

THEME_KEYWORDS = {
    "ai_agent": ["agent", "agentic", "copilot", "autonomous"],
    "model_breakthrough": ["model", "reasoning", "sota", "breakthrough", "inference"],
    "compute_chip": ["chip", "gpu", "semiconductor", "blackwell", "cuda"],
    "enterprise_adoption": ["enterprise", "adoption", "contract", "partnership", "deployment"],
    "earnings_quality": ["revenue", "profit", "margin", "guidance", "buyback"],
    "policy_regulation": ["policy", "regulation", "compliance", "sec", "standard"],
    "infra_buildout": ["datacenter", "infrastructure", "cloud", "power", "network"],
    "web3_infra": ["web3", "blockchain", "layer 2", "rollup", "mainnet", "onchain"],
    "digital_assets": ["bitcoin", "ethereum", "solana", "token", "stablecoin", "defi", "wallet", "etf"],
    "power_market": ["power market", "electricity market", "lmp", "capacity market", "ancillary services", "ppa"],
    "grid_constraints": ["grid", "transmission", "congestion", "curtailment", "interconnection", "demand response"],
}

THEME_CN = {
    "ai_agent": "AI智能体",
    "model_breakthrough": "模型突破",
    "compute_chip": "算力芯片",
    "enterprise_adoption": "企业落地",
    "earnings_quality": "盈利质量",
    "policy_regulation": "政策监管",
    "infra_buildout": "基础设施",
    "web3_infra": "Web3基础设施",
    "digital_assets": "数字资产生态",
    "power_market": "电力市场交易",
    "grid_constraints": "电网约束信号",
}


def _extract_themes(item: NewsItem) -> Set[str]:
    blob = f"{item.title} {item.summary} {item.category}".lower()
    tags: Set[str] = set()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(key in blob for key in keywords):
            tags.add(theme)
    return tags


def apply_trend_resonance(items: List[NewsItem]) -> Tuple[List[NewsItem], List[str]]:
    theme_count: Dict[str, int] = {}
    theme_sources: Dict[str, Set[str]] = {}
    item_themes: List[Set[str]] = []

    for item in items:
        tags = _extract_themes(item)
        item_themes.append(tags)
        for tag in tags:
            theme_count[tag] = theme_count.get(tag, 0) + 1
            if tag not in theme_sources:
                theme_sources[tag] = set()
            theme_sources[tag].add(item.source)

    for item, tags in zip(items, item_themes):
        if not tags:
            continue
        best_bonus = 0.0
        for tag in tags:
            frequency = theme_count.get(tag, 0)
            source_diversity = len(theme_sources.get(tag, set()))
            resonance = frequency * 0.22 + source_diversity * 0.35
            best_bonus = max(best_bonus, resonance)
        item.score += min(2.8, best_bonus)

    items.sort(key=lambda x: x.score, reverse=True)

    trend_rows: List[str] = []
    ranked_themes = sorted(theme_count.items(), key=lambda kv: (kv[1], len(theme_sources.get(kv[0], set()))), reverse=True)
    for theme, count in ranked_themes[:8]:
        if count < 2:
            continue
        trend_rows.append(
            f"{THEME_CN.get(theme, theme)}：出现 {count} 次，跨 {len(theme_sources.get(theme, set()))} 个来源"
        )

    return items, trend_rows
