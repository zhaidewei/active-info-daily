from __future__ import annotations

import json
import re
from typing import Dict

from openai import OpenAI

from active_info.config import Settings


class ReportTranslator:
    def __init__(self, settings: Settings):
        self.enabled = settings.translation_enabled
        self.provider = settings.analysis_provider.lower()
        self.deepseek_strict_model = bool(getattr(settings, "deepseek_strict_model", True))
        self.max_chars = settings.translation_max_chars
        self.client = None
        self.model = ""

        if self.provider == "deepseek" and settings.deepseek_api_key:
            self.client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
            self.model = settings.deepseek_model
        elif self.provider == "openai" and settings.openai_api_key:
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = settings.openai_model

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

    def _clean_markdown_reply(self, text: str) -> str:
        content = (text or "").strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        # Remove double-bullet artifacts like "- • text" from model output.
        content = re.sub(r"(?m)^(\s*-\s*)[\u2022\u00b7\*]+\s+", r"\1", content)
        return content

    def _translate(self, markdown_text: str, target_language: str) -> str:
        prompt = (
            f"Translate this markdown report into {target_language}. "
            "Translate all readable text content; keep URLs unchanged. "
            "Preserve heading levels, bullet structure, tables, and links. "
            "Do not output explanations, only markdown.\n\n"
            f"{markdown_text}"
        )
        completion = None
        last_error = None
        for model in self._model_candidates():
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": "You are a professional bilingual analyst editor."},
                        {"role": "user", "content": prompt},
                    ],
                )
                break
            except Exception as exc:
                last_error = exc
                if "Model Not Exist" in str(exc):
                    continue
                raise
        if completion is None:
            raise RuntimeError(f"translation failed: {last_error}")
        text = completion.choices[0].message.content or ""
        return self._clean_markdown_reply(text)

    def _translate_with_retry(self, candidates: list[str], target_language: str, min_len: int = 220) -> str:
        for candidate in candidates:
            try:
                translated = self._translate(candidate, target_language)
                if translated and len(translated) >= min_len:
                    return translated
            except Exception:
                continue
        return ""

    def _translate_lines(self, lines: list[str], target_language: str) -> list[str]:
        if not lines:
            return []

        user_payload = {
            "target_language": target_language,
            "rule": "Keep markdown syntax and URLs unchanged. Return JSON with key lines.",
            "lines": lines,
        }
        completion = None
        last_error = None
        for model in self._model_candidates():
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a precise translation engine. "
                                "Translate each line to the target language while preserving markdown markers and URLs."
                            ),
                        },
                        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                    ],
                )
                break
            except Exception as exc:
                last_error = exc
                if "Model Not Exist" in str(exc):
                    continue
                raise
        if completion is None:
            raise RuntimeError(f"line translation failed: {last_error}")
        raw = completion.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        translated = parsed.get("lines", [])
        if not isinstance(translated, list):
            return []
        out = [str(x).strip() for x in translated]
        if len(out) != len(lines):
            return []
        return out

    def _chinese_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        return cn_chars / max(1, len(text))

    def _split_markdown_chunks(self, text: str, chunk_size: int = 2200, max_chunks: int = 6) -> list[str]:
        blocks = text.split("\n\n")
        chunks: list[str] = []
        current = ""
        for block in blocks:
            candidate = (current + "\n\n" + block).strip() if current else block
            if len(candidate) > chunk_size and current:
                chunks.append(current)
                current = block
            else:
                current = candidate
        if current.strip():
            chunks.append(current.strip())

        if len(chunks) <= max_chunks:
            return chunks

        # Merge tail chunks to keep call count bounded.
        head = chunks[: max_chunks - 1]
        tail = "\n\n".join(chunks[max_chunks - 1 :])
        head.append(tail)
        return head

    def _translate_in_chunks(self, text: str, target_language: str) -> str:
        chunks = self._split_markdown_chunks(text)
        translated_chunks: list[str] = []
        for chunk in chunks:
            translated = self._translate_with_retry(
                [chunk, chunk[: max(900, len(chunk) // 2)]],
                target_language=target_language,
                min_len=80,
            )
            if not translated:
                return ""
            translated_chunks.append(translated)
        return "\n\n".join(translated_chunks).strip()

    def _translate_by_lines_fallback(self, text: str, target_language: str) -> str:
        lines = text.splitlines()
        if not lines:
            return text

        def needs_translation(line: str) -> bool:
            stripped = line.strip()
            if not stripped:
                return False
            if stripped.startswith("http://") or stripped.startswith("https://"):
                return False
            if target_language == "Simplified Chinese":
                return bool(re.search(r"[A-Za-z]", line))
            return bool(re.search(r"[\u4e00-\u9fff]", line))

        indices = [idx for idx, line in enumerate(lines) if needs_translation(line)]
        if not indices:
            return text

        batch_size = 24
        for start in range(0, len(indices), batch_size):
            batch_indices = indices[start : start + batch_size]
            batch_lines = [lines[i] for i in batch_indices]
            try:
                batch_translated = self._translate_lines(batch_lines, target_language=target_language)
            except Exception:
                continue
            if len(batch_translated) != len(batch_lines):
                continue
            for i, new_line in zip(batch_indices, batch_translated):
                if new_line.strip():
                    lines[i] = new_line

        return "\n".join(lines)

    def translate_markdown(self, markdown_text: str) -> Dict[str, str]:
        source = markdown_text[: self.max_chars]
        result = {"zh_markdown": "", "en_markdown": ""}

        if not self.enabled:
            result["zh_markdown"] = source
            result["en_markdown"] = source
            return result

        if not self.client or not self.model:
            result["zh_markdown"] = source
            result["en_markdown"] = "Translation unavailable: missing API configuration."
            return result

        candidates = [source, source[: max(2400, self.max_chars // 2)]]
        zh_markdown = self._translate_with_retry(candidates, "Simplified Chinese")
        en_markdown = self._translate_with_retry(candidates, "English")

        if not zh_markdown or self._chinese_ratio(zh_markdown) < 0.10:
            chunked_zh = self._translate_in_chunks(source, "Simplified Chinese")
            if chunked_zh and self._chinese_ratio(chunked_zh) > self._chinese_ratio(zh_markdown):
                zh_markdown = chunked_zh
        if not zh_markdown or self._chinese_ratio(zh_markdown) < 0.10:
            line_zh = self._translate_by_lines_fallback(source, "Simplified Chinese")
            if line_zh and self._chinese_ratio(line_zh) > self._chinese_ratio(zh_markdown):
                zh_markdown = line_zh

        if not en_markdown or en_markdown == source or self._chinese_ratio(en_markdown) > 0.03:
            line_en = self._translate_by_lines_fallback(source, "English")
            if line_en:
                en_markdown = line_en

        result["zh_markdown"] = zh_markdown or source
        result["en_markdown"] = en_markdown or source
        return result
