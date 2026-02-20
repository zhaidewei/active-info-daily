from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from openai import OpenAI

from active_info.config import Settings
from active_info.models import NewsItem


class PowerRadarInterpreter:
    def __init__(self, settings: Settings):
        self.provider = settings.analysis_provider.lower()
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
            candidates = [self.model, "deepseek-chat", "deepseek-reasoner"]
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
                "summary": item.summary[:450],
            }
            for idx, item in enumerate(items)
        ]

        system_prompt = (
            "你是电力现货/容量/辅助服务市场研究员。"
            "请为每条新闻输出交易可执行洞察，全部用中文，并仅返回JSON对象："
            '{"insights":[{"id":1,"event_one_liner":"","core_signal":"","trading_implication":"","why_important":"","suggested_action":"跟踪"}]}。'
            "字段要求："
            "event_one_liner必须包含具体事实（数字/地区/项目）；"
            "core_signal是简短信号标签；"
            "trading_implication采用“短期：... 中期：...”格式；"
            "suggested_action仅允许“跟踪”或“忽略”。"
        )
        user_prompt = {
            "task": "输出电力交易雷达结构化洞察",
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
            raise RuntimeError(f"power interpreter failed: {last_error}")

        raw = completion.choices[0].message.content or "{}"
        insights = self._parse_llm_payload(raw)
        if not insights:
            return self._interpret_heuristic(items)

        mapped: Dict[int, Dict[str, str]] = {}
        queue_without_id: List[Dict[str, str]] = []
        for row in insights:
            try:
                idx = int(row.get("id"))
            except Exception:
                idx = -1
            action = str(row.get("suggested_action", "跟踪")).strip()
            if action not in {"跟踪", "忽略"}:
                action = "跟踪"
            normalized = {
                "event_one_liner": str(row.get("event_one_liner", "")).strip(),
                "core_signal": str(row.get("core_signal", "")).strip(),
                "trading_implication": str(row.get("trading_implication", "")).strip(),
                "why_important": str(row.get("why_important", "")).strip(),
                "suggested_action": action,
            }
            if idx > 0:
                mapped[idx] = normalized
            else:
                queue_without_id.append(normalized)

        out: List[Dict[str, str]] = []
        for idx, item in enumerate(items, start=1):
            row = mapped.get(idx)
            if not row and queue_without_id:
                row = queue_without_id.pop(0)
            row = row or self._heuristic_single(item)
            out.append(
                {
                    "title": item.title,
                    "url": item.url,
                    "source": item.source,
                    **row,
                }
            )
        return out

    def _parse_llm_payload(self, raw: str) -> List[Dict[str, object]]:
        text = self._strip_code_fence(raw or "")
        if not text:
            return []

        # 1) Standard JSON object/list
        try:
            parsed = json.loads(text)
            rows = self._coerce_insight_rows(parsed)
            if rows:
                return rows
        except json.JSONDecodeError:
            pass

        # 2) DeepSeek occasionally returns multiple JSON objects concatenated.
        decoder = json.JSONDecoder()
        idx = 0
        rows: List[Dict[str, object]] = []
        while idx < len(text):
            while idx < len(text) and text[idx] in " \n\r\t,":
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end = decoder.raw_decode(text, idx)
                rows.extend(self._coerce_insight_rows(obj))
                idx = end
            except json.JSONDecodeError:
                next_obj = text.find("{", idx + 1)
                next_arr = text.find("[", idx + 1)
                candidates = [pos for pos in [next_obj, next_arr] if pos != -1]
                if not candidates:
                    break
                idx = min(candidates)
        return rows

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        cleaned = (text or "").strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return cleaned

    def _coerce_insight_rows(self, parsed: object) -> List[Dict[str, object]]:
        if isinstance(parsed, list):
            return [row for row in parsed if isinstance(row, dict)]
        if not isinstance(parsed, dict):
            return []

        for key in ("insights", "items", "rows", "data"):
            value = parsed.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        if {"id", "event_one_liner", "core_signal", "trading_implication", "why_important", "suggested_action"} & set(
            parsed.keys()
        ):
            return [parsed]
        return []

    def _heuristic_single(self, item: NewsItem) -> Dict[str, str]:
        text = f"{item.title} {item.summary}".lower()
        metric = self._extract_metric(item.title + " " + item.summary)

        if any(k in text for k in ["congestion", "lmp", "interconnection", "queue", "curtailment", "ercot", "pjm", "caiso"]):
            event = f"并网队列与拥塞约束抬升，节点价差交易窗口扩大{metric}"
            signal = "电网瓶颈/价差信号"
            implication = "短期：高负荷时段LMP波动与节点价差上行。中期：并网节奏决定价差是否常态化。"
            why = "拥塞会先传导到现货与节点价差，直接影响套利与套保效率。"
            action = "跟踪"
        elif any(k in text for k in ["ferc", "standard", "rule", "approval", "policy"]):
            event = f"电力市场规则更新，容量与辅助服务定价框架重估{metric}"
            signal = "监管催化"
            implication = "短期：合规与设备改造预期上修。中期：市场准入与成本曲线变化将触发资产重定价。"
            why = "规则变化直接作用于市场机制和合规成本，是估值锚点变化而非单次新闻。"
            action = "跟踪"
        elif any(k in text for k in ["battery", "bess", "storage", "4-hour"]):
            event = f"储能项目推进，峰谷套利与辅助服务收益结构重排{metric}"
            signal = "储能扩张"
            implication = "短期：并网阶段带来局部波动机会。中期：储能扩容压缩极端价差、提升系统灵活性。"
            why = "储能决定系统调峰能力，直接影响现货尖峰价格与辅助服务供需。"
            action = "跟踪"
        elif any(k in text for k in ["ppa", "corporate ppa", "offtake", "renewable"]):
            event = f"企业PPA结构变化，长期锁价需求向AI负荷迁移{metric}"
            signal = "远期合约重定价"
            implication = "短期：新增PPA议价权向大负荷客户倾斜。中期：项目融资门槛上移，资产分化加剧。"
            why = "PPA是发电项目融资锚，签约结构变化会传导到新增装机与现金流稳定性。"
            action = "跟踪"
        elif any(k in text for k in ["gas", "thermal", "combined cycle"]):
            event = f"大规模气电项目推进，基荷与调峰供给预期上修{metric}"
            signal = "气电供给扩张"
            implication = "短期：容量预期抬升压制远月电价。中期：燃料成本与利用小时决定盈利弹性。"
            why = "气电项目通常改变区域容量紧张度，并影响电价与燃料联动关系。"
            action = "跟踪"
        elif any(k in text for k in ["wind", "solar", "generation", "capacity", "plant"]):
            event = f"新增电源建设推进，供给侧节奏影响电价中枢{metric}"
            signal = "供给扩张"
            implication = "短期：审批与并网节奏影响局部供需。中期：新增容量抬升，电价中枢下行压力增大。"
            why = "新增装机决定未来供需平衡，是公用事业与新能源估值的核心变量。"
            action = "跟踪"
        else:
            event = "电力市场一般更新，暂未形成明确交易方向"
            signal = "一般市场更新"
            implication = "短期：暂无可执行信号。中期：等待价格、负荷或政策数据二次验证。"
            why = "当前信息偏事件披露，尚不足以单独驱动价格。"
            action = "忽略"

        return {
            "event_one_liner": event,
            "core_signal": signal,
            "trading_implication": implication,
            "why_important": why,
            "suggested_action": action,
        }

    @staticmethod
    def _extract_metric(text: str) -> str:
        raw = (text or "").replace("‑", "-")
        for pattern in (
            r"\b\d+(?:\.\d+)?\s?%",
            r"\b\d+(?:\.\d+)?\s?(?:gw|mw|gwh|mwh)\b",
            r"\$\s?\d+(?:\.\d+)?\s?(?:b|bn|billion|m|million)\b",
        ):
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                return f"（关键信息：{match.group(0)}）"
        return ""

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
