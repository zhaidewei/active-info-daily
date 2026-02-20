from __future__ import annotations

import json
import re
from pathlib import Path

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from active_info.config import Settings
from active_info.storage import ReportStorage


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Active Info Aggregator")
    storage = ReportStorage(settings.db_path)
    template_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(template_dir))

    def _strip_leading_h1(md_text: str) -> str:
        lines = (md_text or "").splitlines()
        if not lines:
            return md_text
        first_non_empty_idx = None
        for idx, line in enumerate(lines):
            if line.strip():
                first_non_empty_idx = idx
                break
        if first_non_empty_idx is None:
            return md_text
        if lines[first_non_empty_idx].lstrip().startswith("# "):
            del lines[first_non_empty_idx]
            if first_non_empty_idx < len(lines) and not lines[first_non_empty_idx].strip():
                del lines[first_non_empty_idx]
        return "\n".join(lines).strip()

    def _md_to_html(md_text: str) -> str:
        html = markdown.markdown(md_text, extensions=["fenced_code", "tables", "sane_lists"])
        # Safety net: avoid duplicated page title + first markdown H1.
        html = re.sub(r"^\s*<h1>.*?</h1>\s*", "", html, count=1, flags=re.DOTALL)
        return html

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        reports = storage.list_reports(limit=120)
        latest = storage.latest_report()
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "reports": reports,
                "latest": latest,
            },
        )

    @app.get("/reports/{report_date}", response_class=HTMLResponse)
    def report_detail(request: Request, report_date: str):
        report = storage.get_report(report_date)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        payload = json.loads(report["json_content"]) if report.get("json_content") else {}
        translations = payload.get("translations", {}) if isinstance(payload, dict) else {}
        ingest_stats = payload.get("ingest_stats", {}) if isinstance(payload, dict) else {}
        zh_markdown = _strip_leading_h1(str(translations.get("zh_markdown") or report.get("markdown") or ""))
        en_markdown = _strip_leading_h1(str(translations.get("en_markdown") or ""))
        source_subtitle = ""
        if isinstance(ingest_stats, dict):
            raw = ingest_stats.get("raw_items")
            uniq = ingest_stats.get("unique_items")
            dup = ingest_stats.get("duplicates_removed")
            if raw is not None and uniq is not None and dup is not None:
                source_subtitle = f"数据来源·（原始抓取 {raw}，去重后 {uniq}，重复移除 {dup}）·"

        return templates.TemplateResponse(
            "report.html",
            {
                "request": request,
                "report": report,
                "source_subtitle": source_subtitle,
                "zh_html": _md_to_html(zh_markdown),
                "en_html": _md_to_html(en_markdown) if en_markdown else "",
                "has_en": bool(en_markdown.strip()),
            },
        )

    @app.get("/api/reports/latest", response_class=JSONResponse)
    def latest_report_api():
        report = storage.latest_report()
        if not report:
            return JSONResponse({"message": "No report yet"}, status_code=404)
        return JSONResponse(
            {
                "report_date": report["report_date"],
                "created_at": report["created_at"],
                "total_items": report["total_items"],
                "analysis": json.loads(report["json_content"]),
            }
        )

    return app
