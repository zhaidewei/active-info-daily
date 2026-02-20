from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from openai import OpenAI

from active_info.config import Settings
from active_info.models import AnalysisResult, NewsItem


class InnovationCurator:
    def __init__(self, settings: Settings):
        self.provider = settings.analysis_provider.lower()
        self.client = None
        self.model = ""
        self.max_candidates = 20

        if self.provider == "deepseek" and settings.deepseek_api_key:
            self.client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
            self.model = settings.deepseek_model
        elif self.provider == "openai" and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_model

    def _model_candidates(self) -> List[str]:
        if self.provider == "deepseek":
            candidates = [self.model, "deepseek-chat", "deepseek-reasoner"]
            unique: List[str] = []
            for model in candidates:
                if model and model not in unique:
                    unique.append(model)
            return unique
        return [self.model] if self.model else []

    def curate(self, analysis: AnalysisResult, items: List[NewsItem]) -> AnalysisResult:
        if not items or not self.client or not self._model_candidates():
            return analysis
        try:
            priority_lines = self._rank_with_llm(analysis, items[: self.max_candidates])
        except Exception:
            return analysis
        if not priority_lines:
            return analysis
        analysis.overlooked_trends = self._apply_prioritized_trends(analysis.overlooked_trends, priority_lines)
        return analysis

    def _rank_with_llm(self, analysis: AnalysisResult, items: List[NewsItem]) -> List[str]:
        existing = [*(analysis.overlooked_trends or []), *(analysis.watchlist or [])]
        payload = [
            {
                "id": idx + 1,
                "title": item.title,
                "source": item.source,
                "category": item.category,
                "score": round(float(item.score), 2),
                "url": item.url,
                "summary": item.summary[:420],
            }
            for idx, item in enumerate(items)
        ]

        system_prompt = (
            "你是趋势研究员。请对候选信号按“创新度”排序，强调："
            "1) 新技术/新制度；"
            "2) 现有元素重组形成新分发或新商业模式；"
            "3) 对市场结构或叙事有中期影响。"
            "仅返回JSON对象，格式："
            '{"priority_trends":[{"line":"中文一句话","innovation_score":8.5}]}.'
            "line必须是中文；innovation_score范围0~10。"
        )
        user_prompt = {
            "task": "从候选信号中选择创新度最高的趋势线索",
            "existing_followups": existing,
            "candidate_items": payload,
            "rules": [
                "优先保留创新度>=7.5的信号",
                "尽量覆盖不同主题，最多返回4条",
                "line必须是可直接放入机会跟踪清单的一句话",
            ],
        }

        completion = None
        last_error: Optional[Exception] = None
        for model in self._model_candidates():
            try:
                completion = self.client.chat.completions.create(
                    model=model,
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
            raise RuntimeError(f"innovation curator failed: {last_error}")

        raw = completion.choices[0].message.content or "{}"
        parsed = self._parse_payload(raw)
        rows = parsed.get("priority_trends", [])
        if not isinstance(rows, list):
            return []

        selected: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            line = str(row.get("line", "")).strip()
            try:
                innovation_score = float(row.get("innovation_score", 0.0))
            except Exception:
                innovation_score = 0.0
            if not line or innovation_score < 7.5:
                continue
            selected.append(line)
            if len(selected) >= 4:
                break
        return selected

    @staticmethod
    def _parse_payload(raw: str) -> Dict[str, object]:
        text = (raw or "").strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            text = match.group(1).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}

    @staticmethod
    def _apply_prioritized_trends(existing: List[str], prioritized: List[str], limit: int = 8) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()
        for raw in [*(prioritized or []), *(existing or [])]:
            line = str(raw or "").strip()
            key = line.lower()
            if not line or key in seen:
                continue
            seen.add(key)
            merged.append(line)
            if len(merged) >= limit:
                break
        return merged
