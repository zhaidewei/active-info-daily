from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
from xml.sax.saxutils import escape

import markdown

from active_info.config import Settings

REPORT_BRAND_TITLE_ZH = "乐观者的主动信息汇总"
REPORT_BRAND_TITLE_EN = "Optimists' Active Intelligence Brief"
REPORT_SLOGAN_ZH = "悲观者常常更早看见风险，乐观者更可能把握结果；被动刷流量放大焦虑，主动抓取与筛选才能沉淀机会。"
REPORT_SLOGAN_EN = (
    "Pessimists may spot risks first, but optimists capture outcomes; "
    "passive feeds monetize anxiety, while active sourcing and filtering turns information into opportunity."
)


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
    return re.sub(r"^\s*<h1>.*?</h1>\s*", "", html, count=1, flags=re.DOTALL)


def _rss_excerpt(md_text: str, max_chars: int = 260) -> str:
    raw = _strip_leading_h1(md_text or "")
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    chunks: List[str] = []
    for line in lines:
        if line.startswith("## "):
            continue
        clean = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
        clean = re.sub(r"^[\-\*\d\.\)\s]+", "", clean)
        clean = clean.replace("`", "").strip()
        if not clean:
            continue
        chunks.append(clean)
        if len(" ".join(chunks)) >= max_chars:
            break
    text = " ".join(chunks).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text or "每日主动信息汇总更新。"


def _build_rss_xml(
    reports: List[Dict[str, str]],
    site_url: str,
    generated_at: datetime,
    max_items: int = 30,
) -> str:
    base = (site_url or "").strip() or "https://example.com"
    base = base.rstrip("/")
    items_xml: List[str] = []

    for row in reports[:max_items]:
        date_key = row["report_date"]
        title = row["title"]
        summary = row["summary"]
        link = f"{base}/reports/{date_key}"
        try:
            pub_dt = datetime.fromisoformat(date_key).replace(tzinfo=timezone.utc)
        except Exception:
            pub_dt = generated_at

        items_xml.append(
            "\n".join(
                [
                    "    <item>",
                    f"      <title>{escape(title)}</title>",
                    f"      <link>{escape(link)}</link>",
                    f"      <guid isPermaLink=\"true\">{escape(link)}</guid>",
                    f"      <pubDate>{format_datetime(pub_dt)}</pubDate>",
                    f"      <description>{escape(summary)}</description>",
                    "    </item>",
                ]
            )
        )

    channel_link = base + "/"
    rss_body = "\n".join(items_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{escape(REPORT_BRAND_TITLE_ZH)}</title>
    <link>{escape(channel_link)}</link>
    <description>聚焦正向、乐观、有增量、有创新的主动信息汇总。</description>
    <language>zh-CN</language>
    <lastBuildDate>{format_datetime(generated_at)}</lastBuildDate>
{rss_body}
  </channel>
</rss>
"""


def _render_report_page(
    report_date: str,
    source_subtitle_zh: str,
    source_subtitle_en: str,
    zh_html: str,
    en_html: str,
    has_en: bool,
) -> str:
    title_zh = f"{REPORT_BRAND_TITLE_ZH} - {report_date}"
    title_en = f"{REPORT_BRAND_TITLE_EN} - {report_date}"
    en_btn = '<button id="btn-en" class="btn" onclick="switchLang(\'en\')">English</button>' if has_en else ""
    en_panel = f'<article id="panel-en" class="panel">{en_html}</article>' if has_en else ""
    subtitle_html = ""
    if source_subtitle_zh or source_subtitle_en:
        subtitle_html = (
            f'<div id="source-subtitle" class="subtitle" data-zh="{source_subtitle_zh}" '
            f'data-en="{source_subtitle_en}">{source_subtitle_zh}</div>'
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title_zh}</title>
  <style>
    body {{ font-family: "Avenir Next", "PingFang SC", sans-serif; margin: 24px; background: #f4f7ff; color: #1f2430; }}
    .container {{ max-width: 980px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.08); }}
    .page-title {{ margin: 14px 0 6px; line-height: 1.2; }}
    .slogan {{ margin: 4px 0 12px; color: #3d4f70; font-style: italic; line-height: 1.6; }}
    .subtitle {{ font-size: 13px; color: #5e6e88; margin-bottom: 10px; }}
    .toolbar {{ display: flex; gap: 10px; margin: 14px 0 20px; }}
    .btn {{ border: 1px solid #ccd6ea; background: #f8fbff; color: #173b6f; padding: 7px 12px; border-radius: 8px; cursor: pointer; font-weight: 600; }}
    .btn.active {{ background: #173b6f; color: #fff; border-color: #173b6f; }}
    .panel {{ display: none; line-height: 1.7; }}
    .panel.active {{ display: block; }}
    a {{ color: #0d4f9f; }}
    h1, h2, h3 {{ line-height: 1.3; }}
    code {{ background: #f3f5f8; padding: 1px 4px; border-radius: 4px; }}
    pre code {{ display: block; padding: 12px; overflow-x: auto; }}
    blockquote {{ border-left: 4px solid #d3deef; margin: 0; padding-left: 12px; color: #4d5f7d; }}
  </style>
</head>
<body>
  <div class="container">
    <a id="back-link" href="/" data-zh="返回列表" data-en="Back to List">返回列表</a>
    <h1 id="page-title" class="page-title" data-zh="{title_zh}" data-en="{title_en}">{title_zh}</h1>
    <div id="page-slogan" class="slogan" data-zh="{REPORT_SLOGAN_ZH}" data-en="{REPORT_SLOGAN_EN}">{REPORT_SLOGAN_ZH}</div>
    {subtitle_html}

    <div class="toolbar">
      <button id="btn-zh" class="btn active" onclick="switchLang('zh')">中文</button>
      {en_btn}
      <button
        id="btn-shot"
        class="btn"
        onclick="exportScreenshot()"
        data-zh="一键导出长图"
        data-en="Export Screenshot"
        data-loading-zh="导出中..."
        data-loading-en="Exporting..."
      >一键导出长图</button>
    </div>

    <article id="panel-zh" class="panel active">{zh_html}</article>
    {en_panel}
  </div>

  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
  <script>
    function applyLangText(lang) {{
      const key = lang === 'en' ? 'en' : 'zh';
      const elems = [
        document.getElementById('back-link'),
        document.getElementById('page-title'),
        document.getElementById('page-slogan'),
        document.getElementById('source-subtitle'),
      ];
      for (const el of elems) {{
        if (el && el.dataset && el.dataset[key]) {{
          el.textContent = el.dataset[key];
        }}
      }}
      const shotBtn = document.getElementById('btn-shot');
      if (shotBtn && !shotBtn.disabled && shotBtn.dataset && shotBtn.dataset[key]) {{
        shotBtn.textContent = shotBtn.dataset[key];
      }}
    }}

    function switchLang(lang) {{
      const zhPanel = document.getElementById('panel-zh');
      const enPanel = document.getElementById('panel-en');
      const zhBtn = document.getElementById('btn-zh');
      const enBtn = document.getElementById('btn-en');

      if (lang === 'zh') {{
        zhPanel.classList.add('active');
        if (enPanel) enPanel.classList.remove('active');
        zhBtn.classList.add('active');
        if (enBtn) enBtn.classList.remove('active');
      }} else {{
        if (enPanel) enPanel.classList.add('active');
        zhPanel.classList.remove('active');
        if (enBtn) enBtn.classList.add('active');
        zhBtn.classList.remove('active');
      }}
      applyLangText(lang);
    }}

    async function exportScreenshot() {{
      const activePanel = document.querySelector('.panel.active');
      if (!activePanel) return;

      const shotBtn = document.getElementById('btn-shot');
      const lang = activePanel.id === 'panel-en' ? 'en' : 'zh';
      const loadingText = lang === 'en' ? (shotBtn.dataset.loadingEn || 'Exporting...') : (shotBtn.dataset.loadingZh || '导出中...');
      const prevText = shotBtn.textContent;
      shotBtn.textContent = loadingText;
      shotBtn.disabled = true;

      try {{
        const canvas = await html2canvas(activePanel, {{
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
          windowWidth: document.documentElement.scrollWidth
        }});
        const date = "{report_date}";
        const link = document.createElement('a');
        link.download = `active-info-${{date}}-${{lang}}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
      }} finally {{
        shotBtn.textContent = prevText;
        shotBtn.disabled = false;
      }}
    }}
  </script>
</body>
</html>
"""


def _render_index(reports: List[Tuple[str, int]]) -> str:
    latest = reports[0] if reports else None
    latest_html = ""
    if latest:
        latest_html = (
            '<div class="card">'
            "<strong>最新报告：</strong>"
            f'<a href="/reports/{latest[0]}">{latest[0]}</a>'
            f"<span>（共 {latest[1]} 条信号）</span>"
            "</div>"
        )
    rows = "\n".join(f'<li><a href="/reports/{date_key}">{date_key}</a> - {count} items</li>' for date_key, count in reports)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{REPORT_BRAND_TITLE_ZH}</title>
  <style>
    body {{ font-family: "Avenir Next", "PingFang SC", sans-serif; margin: 24px; background: #f6f8fb; color: #1c1d22; }}
    .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 3px 12px rgba(0,0,0,.06); margin-bottom: 16px; }}
    a {{ color: #0d4f9f; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul {{ line-height: 1.8; }}
  </style>
</head>
<body>
  <h1>{REPORT_BRAND_TITLE_ZH}</h1>
  <p style="font-style: italic; color: #3d4f70;">{REPORT_SLOGAN_ZH}</p>
  <p><a href="/rss.xml">RSS 订阅</a></p>
  {latest_html}
  <div class="card">
    <h2>历史报告</h2>
    <ul>
      {rows}
    </ul>
  </div>
</body>
</html>
"""


def export_static_site(
    settings: Settings,
    output_dir: Path,
    latest_only: bool = False,
    site_url: str = "https://example.com",
) -> Dict[str, str]:
    report_json_files = sorted(settings.report_dir.glob("*.json"))
    if latest_only and report_json_files:
        report_json_files = [report_json_files[-1]]
    if not report_json_files:
        raise ValueError(f"No report JSON found under {settings.report_dir}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(timezone.utc)
    exported: List[Tuple[str, int]] = []
    rss_reports: List[Dict[str, str]] = []
    for json_path in reversed(report_json_files):
        report_date = json_path.stem
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        translations = payload.get("translations", {})
        ingest_stats = payload.get("ingest_stats", {})

        md_fallback_path = settings.report_dir / f"{report_date}.md"
        md_fallback = md_fallback_path.read_text(encoding="utf-8") if md_fallback_path.exists() else ""
        zh_md = _strip_leading_h1(str(translations.get("zh_markdown") or md_fallback or ""))
        en_md = _strip_leading_h1(str(translations.get("en_markdown") or ""))

        source_subtitle_zh = ""
        source_subtitle_en = ""
        if isinstance(ingest_stats, dict):
            raw = ingest_stats.get("raw_items")
            uniq = ingest_stats.get("unique_items")
            dup = ingest_stats.get("duplicates_removed")
            if raw is not None and uniq is not None and dup is not None:
                source_subtitle_zh = f"数据来源·（原始抓取 {raw}，去重后 {uniq}，重复移除 {dup}）·"
                source_subtitle_en = f"Sources (raw {raw}, deduped {uniq}, removed {dup})."
                try:
                    exported.append((report_date, int(uniq)))
                except Exception:
                    exported.append((report_date, 0))
            else:
                exported.append((report_date, 0))
        else:
            exported.append((report_date, 0))

        zh_html = _md_to_html(zh_md)
        en_html = _md_to_html(en_md) if en_md.strip() else ""
        rss_reports.append(
            {
                "report_date": report_date,
                "title": f"{REPORT_BRAND_TITLE_ZH} - {report_date}",
                "summary": _rss_excerpt(zh_md),
            }
        )

        report_html = _render_report_page(
            report_date=report_date,
            source_subtitle_zh=source_subtitle_zh,
            source_subtitle_en=source_subtitle_en,
            zh_html=zh_html,
            en_html=en_html,
            has_en=bool(en_md.strip()),
        )
        report_dir = output_dir / "reports" / report_date
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "index.html").write_text(report_html, encoding="utf-8")

    exported.sort(key=lambda x: x[0], reverse=True)
    rss_reports.sort(key=lambda x: x["report_date"], reverse=True)
    index_html = _render_index(exported)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")
    rss_xml = _build_rss_xml(rss_reports, site_url=site_url, generated_at=generated_at)
    (output_dir / "rss.xml").write_text(rss_xml, encoding="utf-8")

    return {"output_dir": str(output_dir), "reports": str(len(exported)), "rss": str(output_dir / "rss.xml")}
