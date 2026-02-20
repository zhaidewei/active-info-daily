from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

import markdown

from active_info.config import Settings


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


def _render_report_page(report_date: str, source_subtitle: str, zh_html: str, en_html: str, has_en: bool) -> str:
    en_btn = '<button id="btn-en" class="btn" onclick="switchLang(\'en\')">English</button>' if has_en else ""
    en_panel = f'<article id="panel-en" class="panel">{en_html}</article>' if has_en else ""
    subtitle_html = f'<div class="subtitle">{source_subtitle}</div>' if source_subtitle else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>主动信息汇总日报 - {report_date}</title>
  <style>
    body {{ font-family: "Avenir Next", "PingFang SC", sans-serif; margin: 24px; background: #f4f7ff; color: #1f2430; }}
    .container {{ max-width: 980px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 14px; box-shadow: 0 4px 20px rgba(0,0,0,.08); }}
    .page-title {{ margin: 14px 0 6px; line-height: 1.2; }}
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
    <a href="/">返回列表</a>
    <h1 class="page-title">主动信息汇总日报 - {report_date}</h1>
    {subtitle_html}

    <div class="toolbar">
      <button id="btn-zh" class="btn active" onclick="switchLang('zh')">中文</button>
      {en_btn}
      <button id="btn-shot" class="btn" onclick="exportScreenshot()">一键导出长图</button>
    </div>

    <article id="panel-zh" class="panel active">{zh_html}</article>
    {en_panel}
  </div>

  <script src="https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js"></script>
  <script>
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
    }}

    async function exportScreenshot() {{
      const activePanel = document.querySelector('.panel.active');
      if (!activePanel) return;

      const shotBtn = document.getElementById('btn-shot');
      const prevText = shotBtn.textContent;
      shotBtn.textContent = '导出中...';
      shotBtn.disabled = true;

      try {{
        const canvas = await html2canvas(activePanel, {{
          scale: 2,
          useCORS: true,
          backgroundColor: '#ffffff',
          windowWidth: document.documentElement.scrollWidth
        }});
        const date = "{report_date}";
        const lang = activePanel.id === 'panel-en' ? 'en' : 'zh';
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
  <title>主动信息聚合</title>
  <style>
    body {{ font-family: "Avenir Next", "PingFang SC", sans-serif; margin: 24px; background: #f6f8fb; color: #1c1d22; }}
    .card {{ background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 3px 12px rgba(0,0,0,.06); margin-bottom: 16px; }}
    a {{ color: #0d4f9f; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    ul {{ line-height: 1.8; }}
  </style>
</head>
<body>
  <h1>主动信息聚合日报</h1>
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


def export_static_site(settings: Settings, output_dir: Path, latest_only: bool = False) -> Dict[str, str]:
    report_json_files = sorted(settings.report_dir.glob("*.json"))
    if latest_only and report_json_files:
        report_json_files = [report_json_files[-1]]
    if not report_json_files:
        raise ValueError(f"No report JSON found under {settings.report_dir}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "reports").mkdir(parents=True, exist_ok=True)

    exported: List[Tuple[str, int]] = []
    for json_path in reversed(report_json_files):
        report_date = json_path.stem
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        translations = payload.get("translations", {})
        ingest_stats = payload.get("ingest_stats", {})

        md_fallback_path = settings.report_dir / f"{report_date}.md"
        md_fallback = md_fallback_path.read_text(encoding="utf-8") if md_fallback_path.exists() else ""
        zh_md = _strip_leading_h1(str(translations.get("zh_markdown") or md_fallback or ""))
        en_md = _strip_leading_h1(str(translations.get("en_markdown") or ""))

        source_subtitle = ""
        if isinstance(ingest_stats, dict):
            raw = ingest_stats.get("raw_items")
            uniq = ingest_stats.get("unique_items")
            dup = ingest_stats.get("duplicates_removed")
            if raw is not None and uniq is not None and dup is not None:
                source_subtitle = f"数据来源·（原始抓取 {raw}，去重后 {uniq}，重复移除 {dup}）·"
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

        report_html = _render_report_page(
            report_date=report_date,
            source_subtitle=source_subtitle,
            zh_html=zh_html,
            en_html=en_html,
            has_en=bool(en_md.strip()),
        )
        report_dir = output_dir / "reports" / report_date
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "index.html").write_text(report_html, encoding="utf-8")

    exported.sort(key=lambda x: x[0], reverse=True)
    index_html = _render_index(exported)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    return {"output_dir": str(output_dir), "reports": str(len(exported))}
