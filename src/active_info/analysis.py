from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from openai import OpenAI

from active_info.models import AnalysisResult, NewsItem


class Analyzer:
    def __init__(
        self,
        provider: str,
        openai_api_key: Optional[str],
        openai_model: str,
        deepseek_api_key: Optional[str] = None,
        deepseek_model: str = "deepseek-chat",
        deepseek_base_url: str = "https://api.deepseek.com",
    ):
        self.provider = provider.lower()
        self.model = openai_model
        self.client = None

        if self.provider == "openai" and openai_api_key:
            self.model = openai_model
            self.client = OpenAI(api_key=openai_api_key)
        elif self.provider == "deepseek" and deepseek_api_key:
            self.model = deepseek_model
            self.client = OpenAI(api_key=deepseek_api_key, base_url=deepseek_base_url)

    def _model_candidates(self) -> list[str]:
        if self.provider == "deepseek":
            candidates = [self.model, "deepseek-chat", "deepseek-reasoner"]
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
            "You are an analyst for IT/AI/Web3/Power-Trading opportunities and positive investment signals. "
            "Return strict JSON with keys: overview, breakthroughs, investment_signals, "
            "overlooked_trends, watchlist. Each list item must be concise Chinese bullet text."
        )
        user_prompt = {
            "date": report_date,
            "goal": [
                "1) IT/AI/Web3/电力交易行业重大突破",
                "2) 具备股票投资价值的积极信息",
                "3) 被人忽视但有潜力的趋势信号（含Web3和电力交易）",
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

        return AnalysisResult(
            overview=overview_text,
            breakthroughs=[str(x) for x in parsed.get("breakthroughs", [])][:8],
            investment_signals=[str(x) for x in parsed.get("investment_signals", [])][:8],
            overlooked_trends=[str(x) for x in parsed.get("overlooked_trends", [])][:8],
            watchlist=[str(x) for x in parsed.get("watchlist", [])][:10],
        )

    def _analyze_heuristic(self, items: list[NewsItem]) -> AnalysisResult:
        breakthroughs: list[str] = []
        investments: list[str] = []
        trends: list[str] = []

        for item in items:
            text = f"{item.title} {item.summary}".lower()
            bullet = f"{item.title}（{item.source}）"
            if len(breakthroughs) < 6 and any(
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
            has_negative = any(
                k in text
                for k in ["fraud", "lawsuit", "probe", "investigation", "layoff", "bankruptcy", "recall", "downgrade"]
            )
            if len(investments) < 6 and any(
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
            ) and not has_negative:
                investments.append(bullet)
            if len(trends) < 6 and any(
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
            breakthroughs = [f"重点跟踪高分信息：{item.title}" for item in items[:3]]
        if not investments:
            investments = [f"可继续验证正向信号：{item.title}" for item in items[:3]]
        if not trends:
            trends = [f"潜在趋势线索：{item.title}" for item in items[:3]]

        def _cut(text: str, limit: int = 120) -> str:
            return text if len(text) <= limit else text[: limit - 1] + "…"

        return AnalysisResult(
            overview=f"{datetime.now().strftime('%Y-%m-%d')} 共扫描 {len(items)} 条信号，建议优先关注高分条目并做二次验证。",
            breakthroughs=breakthroughs,
            investment_signals=investments,
            overlooked_trends=trends,
            watchlist=[f"{_cut(item.title)} | {item.source} | score={item.score:.1f}" for item in items[:10]],
        )
