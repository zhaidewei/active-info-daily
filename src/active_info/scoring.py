from __future__ import annotations

from active_info.models import NewsItem

AI_BREAKTHROUGH = {
    "breakthrough",
    "state-of-the-art",
    "sota",
    "foundation model",
    "agent",
    "reasoning",
    "inference",
    "chip",
    "semiconductor",
    "open source model",
}

WEB3_SIGNAL = {
    "web3",
    "blockchain",
    "crypto",
    "bitcoin",
    "ethereum",
    "solana",
    "layer 2",
    "rollup",
    "defi",
    "tokenization",
    "stablecoin",
    "staking",
    "onchain",
    "wallet",
}

POWER_TRADING_SIGNAL = {
    "power trading",
    "electricity market",
    "power market",
    "grid",
    "transmission",
    "congestion",
    "lmp",
    "locational marginal price",
    "capacity market",
    "ancillary services",
    "demand response",
    "curtailment",
    "interconnection",
    "ppa",
    "battery storage",
    "ercot",
    "pjm",
    "caiso",
}

INVESTMENT_POSITIVE = {
    "profit",
    "guidance raise",
    "beat estimates",
    "record revenue",
    "approval",
    "contract win",
    "partnership",
    "backlog",
    "buyback",
    "expansion",
    "adoption",
    "10-q",
    "10-k",
    "8-k",
    "filed",
    "etf",
    "mainnet",
    "tvl",
    "institutional adoption",
    "onchain volume",
    "ppa",
    "capacity auction",
    "ancillary services",
    "interconnection approval",
}

OVERLOOKED_SIGNAL = {
    "policy",
    "infrastructure",
    "regulation",
    "supply chain",
    "talent",
    "hiring",
    "pilot",
    "standard",
    "benchmark",
    "grid bottleneck",
    "transmission queue",
    "curtailment",
    "congestion",
}

NEGATIVE_SIGNAL = {
    "fraud",
    "lawsuit",
    "probe",
    "investigation",
    "layoff",
    "cuts jobs",
    "miss estimates",
    "downgrade",
    "bankruptcy",
    "recall",
}


def _count_keywords(text: str, keywords: set[str]) -> int:
    lowered = text.lower()
    return sum(1 for key in keywords if key in lowered)


def score_items(items: list[NewsItem]) -> list[NewsItem]:
    scored: list[NewsItem] = []
    for item in items:
        blob = f"{item.title} {item.summary} {item.category}".lower()
        ai_score = _count_keywords(blob, AI_BREAKTHROUGH) * 1.5
        web3_score = _count_keywords(blob, WEB3_SIGNAL) * 1.35
        power_score = _count_keywords(blob, POWER_TRADING_SIGNAL) * 1.3
        invest_score = _count_keywords(blob, INVESTMENT_POSITIVE) * 1.4
        trend_score = _count_keywords(blob, OVERLOOKED_SIGNAL) * 1.2
        risk_penalty = _count_keywords(blob, NEGATIVE_SIGNAL) * 1.8
        base = 1.0 if item.category in {"ai", "it", "web3", "power_trading", "earnings", "prediction_market"} else 0.0
        item.score = ai_score + web3_score + power_score + invest_score + trend_score + base - risk_penalty
        scored.append(item)

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
