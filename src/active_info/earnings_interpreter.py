from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from openai import OpenAI

from active_info.config import Settings
from active_info.models import NewsItem


class EarningsRadarInterpreter:
    def __init__(self, settings: Settings):
        self.provider = settings.analysis_provider.lower()
        self.deepseek_strict_model = bool(getattr(settings, "deepseek_strict_model", True))
        self.client = None
        self.model = ""
        self.max_items = 8

        if self.provider == "deepseek" and settings.deepseek_api_key:
            self.client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
            self.model = settings.deepseek_model
        elif self.provider == "openai" and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_model

    def _model_candidates(self) -> List[str]:
        if self.provider == "deepseek":
            if self.deepseek_strict_model:
                return [self.model] if self.model else ["deepseek-reasoner"]
            candidates = [self.model, "deepseek-reasoner", "deepseek-chat"]
            unique: List[str] = []
            for model in candidates:
                if model and model not in unique:
                    unique.append(model)
            return unique
        return [self.model] if self.model else []

    def interpret(self, items: List[NewsItem]) -> List[Dict[str, str]]:
        if not items:
            return []

        focus = items[: self.max_items]
        if self.client and self._model_candidates():
            try:
                return self._interpret_with_llm(focus)
            except Exception:
                pass
        return self._interpret_heuristic(focus)

    def _interpret_with_llm(self, items: List[NewsItem]) -> List[Dict[str, str]]:
        payload = [
            {
                "id": idx + 1,
                "title": item.title,
                "source": item.source,
                "url": item.url,
                "summary": item.summary[:500],
            }
            for idx, item in enumerate(items)
        ]

        system_prompt = (
            "你是资深财报与监管解读分析师。"
            "对每条输入输出结构化解读，严格JSON，字段："
            "id,event_one_liner,sentiment,impact_target,why_important,suggested_action。"
            "sentiment 只能是 利好/中性/利空。"
            "suggested_action 只能是 跟踪/忽略。"
        )
        user_prompt = {
            "task": "逐条生成财报雷达解释",
            "items": payload,
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
            raise RuntimeError(f"earnings interpreter failed: {last_error}")

        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        insights = parsed.get("insights", [])
        if not isinstance(insights, list):
            return self._interpret_heuristic(items)

        mapped: Dict[int, Dict[str, str]] = {}
        for row in insights:
            try:
                idx = int(row.get("id"))
            except Exception:
                continue
            sentiment = str(row.get("sentiment", "中性"))
            if sentiment not in {"利好", "中性", "利空"}:
                sentiment = "中性"
            action = str(row.get("suggested_action", "跟踪"))
            if action not in {"跟踪", "忽略"}:
                action = "跟踪" if sentiment != "利空" else "忽略"

            mapped[idx] = {
                "event_one_liner": str(row.get("event_one_liner", "")).strip(),
                "sentiment": sentiment,
                "impact_target": str(row.get("impact_target", "")).strip(),
                "why_important": str(row.get("why_important", "")).strip(),
                "suggested_action": action,
            }

        result: List[Dict[str, str]] = []
        for idx, item in enumerate(items, start=1):
            row = mapped.get(idx)
            if not row:
                row = self._heuristic_single(item)
            result.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    **row,
                }
            )
        return result

    def _extract_target(self, item: NewsItem) -> str:
        title = item.title.strip()
        m = re.match(r"^([A-Z]{2,6})\s+filed\s+", title)
        if m:
            return m.group(1)

        lower = f"{item.title} {item.summary}".lower()
        if "sec" in lower:
            return "美国监管/资本市场"
        if "etf" in lower:
            return "ETF与资产管理行业"
        if "crypto" in lower or "token" in lower:
            return "数字资产相关公司"
        return "相关公司与行业"

    def _heuristic_single(self, item: NewsItem) -> Dict[str, str]:
        text = f"{item.title} {item.summary}".lower()
        pos_hits = sum(1 for k in ["record", "growth", "beat", "raise", "approval", "partnership", "adoption"] if k in text)
        neg_hits = sum(1 for k in ["fraud", "lawsuit", "probe", "investigation", "miss", "down", "cut"] if k in text)

        if neg_hits >= 1 and neg_hits >= pos_hits:
            sentiment = "利空"
            action = "忽略"
        elif pos_hits >= 1 and pos_hits > neg_hits:
            sentiment = "利好"
            action = "跟踪"
        else:
            sentiment = "中性"
            action = "跟踪"

        target = self._extract_target(item)
        event = item.title.strip()
        if len(event) > 90:
            event = event[:89] + "…"

        if sentiment == "利好":
            why = "可能带来业绩弹性或估值提升，值得继续跟踪后续确认数据。"
        elif sentiment == "利空":
            why = "该事件偏风险暴露，短期对估值与情绪可能形成压制。"
        else:
            why = "事件重要但方向尚不明确，需要等待后续披露或经营数据验证。"

        return {
            "event_one_liner": event,
            "sentiment": sentiment,
            "impact_target": target,
            "why_important": why,
            "suggested_action": action,
        }

    def _interpret_heuristic(self, items: List[NewsItem]) -> List[Dict[str, str]]:
        return [
            {
                "title": item.title,
                "url": item.url,
                "source": item.source,
                **self._heuristic_single(item),
            }
            for item in items
        ]
