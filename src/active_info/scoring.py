from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from active_info.models import NewsItem

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency at runtime
    OpenAI = None  # type: ignore[misc,assignment]

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


def _heuristic_score(item: NewsItem) -> float:
    blob = f"{item.title} {item.summary} {item.category}".lower()
    ai_score = _count_keywords(blob, AI_BREAKTHROUGH) * 1.5
    web3_score = _count_keywords(blob, WEB3_SIGNAL) * 1.35
    power_score = _count_keywords(blob, POWER_TRADING_SIGNAL) * 1.3
    invest_score = _count_keywords(blob, INVESTMENT_POSITIVE) * 1.4
    trend_score = _count_keywords(blob, OVERLOOKED_SIGNAL) * 1.2
    risk_penalty = _count_keywords(blob, NEGATIVE_SIGNAL) * 1.8
    base = 1.0 if item.category in {"ai", "it", "web3", "power_trading", "earnings", "prediction_market"} else 0.0
    return ai_score + web3_score + power_score + invest_score + trend_score + base - risk_penalty


def _model_candidates(provider: str, model: str, deepseek_strict_model: bool = True) -> List[str]:
    if provider == "deepseek":
        if deepseek_strict_model:
            return [model] if model else ["deepseek-reasoner"]
        picks = [model, "deepseek-reasoner", "deepseek-chat"]
        unique: List[str] = []
        for x in picks:
            if x and x not in unique:
                unique.append(x)
        return unique
    return [model] if model else []


def _parse_json_object(raw: str) -> Dict[str, object]:
    text = (raw or "").strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _clamp(num: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, num))


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _llm_score_items(items: List[NewsItem], settings: object) -> Optional[List[NewsItem]]:
    provider = str(getattr(settings, "analysis_provider", "heuristic")).lower()
    deepseek_strict_model = bool(getattr(settings, "deepseek_strict_model", True))
    if not bool(getattr(settings, "llm_scoring_enabled", True)):
        return None
    if provider not in {"openai", "deepseek"}:
        return None
    if OpenAI is None:
        return None

    client = None
    model = ""
    if provider == "openai":
        key = str(getattr(settings, "openai_api_key", "") or "").strip()
        if not key:
            return None
        model = str(getattr(settings, "openai_model", "gpt-4o-mini"))
        client = OpenAI(api_key=key)
    else:
        key = str(getattr(settings, "deepseek_api_key", "") or "").strip()
        if not key:
            return None
        model = str(getattr(settings, "deepseek_model", "deepseek-reasoner"))
        base_url = str(getattr(settings, "deepseek_base_url", "https://api.deepseek.com"))
        client = OpenAI(api_key=key, base_url=base_url)

    if not items or client is None:
        return None

    max_items = int(getattr(settings, "llm_scoring_max_items", 80) or 80)
    max_items = max(10, min(max_items, len(items)))

    indexed = list(enumerate(items, start=1))
    if len(indexed) > max_items:
        indexed = sorted(indexed, key=lambda x: _heuristic_score(x[1]), reverse=True)[:max_items]
        indexed.sort(key=lambda x: x[0])

    payload = [
        {
            "id": idx,
            "title": item.title,
            "summary": item.summary[:800],
            "source": item.source,
            "category": item.category,
            "url": item.url,
        }
        for idx, item in indexed
    ]

    system_prompt = (
        "你是信息信号评分器。只关注 IT/AI/Web3/电力交易。"
        "按下面规则给每条信号打分，返回严格JSON："
        '{"scores":[{"id":1,"positive":1.5,"incremental":1.2,"innovation":2.4,'
        '"investability":1.1,"verifiability":0.8,"total":7.0,"keep":true,'
        '"reason":"中文一句"}]}.'
        "前置过滤：负面主导/高风险主导/不可验证/领域无关 -> keep=false。"
        "维度范围：positive(0-2), incremental(0-2), innovation(0-3), "
        "investability(0-2), verifiability(0-1), total(0-10)。"
    )
    user_prompt = {
        "task": "根据用户偏好进行机会评分排序",
        "user_preference": "只聚焦好消息、乐观消息、有增量、有创新的消息",
        "rules": [
            "innovation 优先，特别是现有元素重组形成新模式",
            "只保留正向机会，不保留风险主导叙事",
            "total建议等于5个维度加总，可有轻微修正",
        ],
        "items": payload,
    }

    completion = None
    last_error: Optional[Exception] = None
    for candidate_model in _model_candidates(provider, model, deepseek_strict_model=deepseek_strict_model):
        try:
            completion = client.chat.completions.create(
                model=candidate_model,
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                ],
            )
            break
        except Exception as exc:
            last_error = exc
            if "Model Not Exist" in str(exc):
                continue
            raise

    if completion is None:
        raise RuntimeError(f"LLM scoring failed: {last_error}")

    raw = completion.choices[0].message.content or "{}"
    parsed = _parse_json_object(raw)
    rows = parsed.get("scores")
    if not isinstance(rows, list):
        return None

    llm_score_by_id: Dict[int, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            row_id = int(row.get("id", 0))
        except Exception:
            continue
        if row_id <= 0:
            continue
        keep = bool(row.get("keep", True))
        positive = _clamp(_safe_float(row.get("positive", 0.0)), 0.0, 2.0)
        incremental = _clamp(_safe_float(row.get("incremental", 0.0)), 0.0, 2.0)
        innovation = _clamp(_safe_float(row.get("innovation", 0.0)), 0.0, 3.0)
        investability = _clamp(_safe_float(row.get("investability", 0.0)), 0.0, 2.0)
        verifiability = _clamp(_safe_float(row.get("verifiability", 0.0)), 0.0, 1.0)
        summed = positive + incremental + innovation + investability + verifiability
        model_total = _clamp(_safe_float(row.get("total", summed), default=summed), 0.0, 10.0)
        total = (summed * 0.8 + model_total * 0.2) if keep else 0.0
        llm_score_by_id[row_id] = round(total, 3)

    scored: List[NewsItem] = []
    for idx, item in enumerate(items, start=1):
        if idx in llm_score_by_id:
            item.score = llm_score_by_id[idx]
        else:
            item.score = _heuristic_score(item)
        scored.append(item)

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def score_items(items: list[NewsItem], settings: Optional[object] = None) -> list[NewsItem]:
    if settings is not None:
        try:
            llm_ranked = _llm_score_items(items, settings)
            if llm_ranked:
                return llm_ranked
        except Exception:
            pass

    scored: list[NewsItem] = []
    for item in items:
        item.score = _heuristic_score(item)
        scored.append(item)

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
