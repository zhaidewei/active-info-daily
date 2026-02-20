from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from openai import OpenAI

from active_info.models import AnalysisResult, NewsItem


NEGATIVE_HINTS = [
    "fraud",
    "lawsuit",
    "probe",
    "investigation",
    "layoff",
    "bankruptcy",
    "recall",
    "downgrade",
    "hack",
    "exploit",
    "sanction",
    "penalty",
    "decline",
    "drop",
    "bearish",
    "暴跌",
    "下滑",
    "裁员",
    "诉讼",
    "调查",
    "处罚",
    "亏损",
]

POSITIVE_HINTS = [
    "breakthrough",
    "launch",
    "adoption",
    "partnership",
    "growth",
    "upgrade",
    "approval",
    "guidance raised",
    "record",
    "expansion",
    "unlock",
    "increase",
    "first",
    "new",
    "突破",
    "创新",
    "增长",
    "上调",
    "落地",
    "扩张",
    "合作",
    "提速",
    "首次",
    "新增",
    "升级",
]

INNOVATION_HINTS = [
    "agent",
    "tokenization",
    "mainnet",
    "infrastructure",
    "standard",
    "rollup",
    "defi",
    "onchain",
    "cross-border",
    "ai-native",
    "power market",
    "battery storage",
    "demand response",
    "transmission",
    "recombination",
    "business model",
    "protocol",
    "创新",
    "重组",
    "新模式",
    "新范式",
    "基础设施",
    "代币化",
    "链上",
    "电力交易",
    "并网",
    "储能",
]


def _contains_any(text: str, hints: list[str]) -> bool:
    lowered = (text or "").lower()
    return any(h in lowered for h in hints)


def _is_negative_signal(text: str) -> bool:
    return _contains_any(text, NEGATIVE_HINTS)


def _is_positive_or_innovative(text: str, require_innovation: bool = False) -> bool:
    positive_hit = _contains_any(text, POSITIVE_HINTS)
    innovation_hit = _contains_any(text, INNOVATION_HINTS)
    return innovation_hit if require_innovation else (positive_hit or innovation_hit)


def _clean_lines(
    rows: object,
    limit: int,
    require_innovation: bool = False,
) -> list[str]:
    if not isinstance(rows, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in rows:
        line = str(raw or "").strip()
        if not line:
            continue
        key = line.lower()
        if key in seen:
            continue
        if _is_negative_signal(line):
            continue
        if not _is_positive_or_innovative(line, require_innovation=require_innovation):
            continue
        seen.add(key)
        out.append(line)
        if len(out) >= limit:
            break
    return out


class Analyzer:
    def __init__(
        self,
        provider: str,
        openai_api_key: Optional[str],
        openai_model: str,
        deepseek_api_key: Optional[str] = None,
        deepseek_model: str = "deepseek-reasoner",
        deepseek_base_url: str = "https://api.deepseek.com",
        deepseek_strict_model: bool = True,
    ):
        self.provider = provider.lower()
        self.model = openai_model
        self.deepseek_strict_model = deepseek_strict_model
        self.client = None

        if self.provider == "openai" and openai_api_key:
            self.model = openai_model
            self.client = OpenAI(api_key=openai_api_key)
        elif self.provider == "deepseek" and deepseek_api_key:
            self.model = deepseek_model
            self.client = OpenAI(api_key=deepseek_api_key, base_url=deepseek_base_url)

    def _model_candidates(self) -> list[str]:
        if self.provider == "deepseek":
            if self.deepseek_strict_model:
                return [self.model] if self.model else ["deepseek-reasoner"]
            candidates = [self.model, "deepseek-reasoner", "deepseek-chat"]
            unique: list[str] = []
            for model in candidates:
                if model and model not in unique:
                    unique.append(model)
            return unique
        return [self.model]

    def analyze(self, report_date: str, items: list[NewsItem]) -> AnalysisResult:
        if self.provider in {"openai", "deepseek"} and self.client:
            try:
                return self._analyze_with_openai(report_date, items)
            except Exception:
                return self._analyze_heuristic(items)
        return self._analyze_heuristic(items)

    def _analyze_with_openai(self, report_date: str, items: list[NewsItem]) -> AnalysisResult:
        serialized_items = []
        for idx, item in enumerate(items, start=1):
            serialized_items.append(
                {
                    "id": idx,
                    "title": item.title,
                    "source": item.source,
                    "category": item.category,
                    "score": round(item.score, 2),
                    "url": item.url,
                    "summary": item.summary[:450],
                }
            )

        system_prompt = (
            "You are an analyst for IT/AI/Web3/Power-Trading opportunities. "
            "Return strict JSON with keys: overview, breakthroughs, investment_signals, "
            "overlooked_trends, watchlist. Each list item must be concise Chinese bullet text. "
            "Only keep positive, optimistic, incremental and innovative signals. "
            "Exclude negative/risk-heavy items."
        )
        user_prompt = {
            "date": report_date,
            "goal": [
                "1) 已发生且可验证的正向事实/新闻（重大突破或积极进展）",
                "2) 可能的趋势与机会（乐观、有增量、有创新，尤其是现有元素重组）",
                "3) 不输出负面或高风险主导叙事",
            ],
            "items": serialized_items,
        }

        completion = None
        last_error: Optional[Exception] = None
        for model in self._model_candidates():
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    temperature=0.2,
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
            raise RuntimeError(f"LLM completion failed: {last_error}")
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        overview_value = parsed.get("overview", "")
        if isinstance(overview_value, list):
            overview_text = "\n".join(str(x).strip() for x in overview_value if str(x).strip())
        else:
            overview_text = str(overview_value)

        breakthroughs = _clean_lines(parsed.get("breakthroughs", []), limit=10)
        investment_signals = _clean_lines(parsed.get("investment_signals", []), limit=10)
        overlooked_trends = _clean_lines(parsed.get("overlooked_trends", []), limit=10, require_innovation=True)
        watchlist = _clean_lines(parsed.get("watchlist", []), limit=12, require_innovation=True)

        if not breakthroughs:
            breakthroughs = [f"积极进展：{item.title}" for item in items[:3] if not _is_negative_signal(item.title)]
        if not investment_signals:
            investment_signals = [f"增量机会：{item.title}" for item in items[:4] if not _is_negative_signal(item.title)]
        if not overlooked_trends:
            overlooked_trends = investment_signals[:6]

        return AnalysisResult(
            overview=overview_text,
            breakthroughs=breakthroughs[:8],
            investment_signals=investment_signals[:8],
            overlooked_trends=overlooked_trends[:8],
            watchlist=watchlist[:10],
        )

    def _analyze_heuristic(self, items: list[NewsItem]) -> AnalysisResult:
        breakthroughs: list[str] = []
        investments: list[str] = []
        trends: list[str] = []

        for item in items:
            text = f"{item.title} {item.summary}".lower()
            if _is_negative_signal(text):
                continue
            bullet = f"{item.title}（{item.source}）"
            if len(breakthroughs) < 6 and _is_positive_or_innovative(text) and any(
                k in text
                for k in [
                    "model",
                    "agent",
                    "chip",
                    "breakthrough",
                    "ai",
                    "llm",
                    "web3",
                    "blockchain",
                    "ethereum",
                    "solana",
                    "bitcoin",
                    "layer 2",
                    "power market",
                    "electricity market",
                    "grid",
                    "battery storage",
                    "demand response",
                    "transmission",
                ]
            ):
                breakthroughs.append(bullet)
            if len(investments) < 8 and _is_positive_or_innovative(text) and any(
                k in text
                for k in [
                    "revenue",
                    "profit",
                    "partnership",
                    "adoption",
                    "guidance",
                    "contract",
                    "10-q",
                    "10-k",
                    "8-k",
                    "filed",
                    "etf",
                    "mainnet",
                    "tvl",
                    "onchain",
                    "institutional",
                    "ppa",
                    "capacity market",
                    "ancillary services",
                    "lmp",
                    "interconnection",
                ]
            ):
                investments.append(bullet)
            if len(trends) < 8 and _is_positive_or_innovative(text, require_innovation=True) and any(
                k in text
                for k in [
                    "policy",
                    "infrastructure",
                    "regulation",
                    "supply chain",
                    "standard",
                    "wallet",
                    "defi",
                    "stablecoin",
                    "tokenization",
                    "onchain",
                    "rollup",
                    "transmission queue",
                    "congestion",
                    "curtailment",
                    "grid bottleneck",
                    "ercot",
                    "pjm",
                    "caiso",
                ]
            ):
                trends.append(bullet)
            if len(breakthroughs) >= 6 and len(investments) >= 6 and len(trends) >= 6:
                break

        if not breakthroughs:
            breakthroughs = [f"积极进展：{item.title}" for item in items[:3] if not _is_negative_signal(item.title)]
        if not investments:
            investments = [f"增量机会：{item.title}" for item in items[:4] if not _is_negative_signal(item.title)]
        if not trends:
            trends = [f"创新趋势：{item.title}" for item in items[:4] if not _is_negative_signal(item.title)]

        def _cut(text: str, limit: int = 120) -> str:
            return text if len(text) <= limit else text[: limit - 1] + "…"

        watchlist: list[str] = []
        for item in items:
            blob = f"{item.title} {item.summary}".lower()
            if _is_negative_signal(blob):
                continue
            if not _is_positive_or_innovative(blob, require_innovation=True):
                continue
            watchlist.append(f"{_cut(item.title)} | {item.source} | score={item.score:.1f}")
            if len(watchlist) >= 10:
                break

        return AnalysisResult(
            overview=f"{datetime.now().strftime('%Y-%m-%d')} 共扫描 {len(items)} 条信号，建议优先关注高分条目并做二次验证。",
            breakthroughs=breakthroughs,
            investment_signals=investments,
            overlooked_trends=trends,
            watchlist=watchlist,
        )
