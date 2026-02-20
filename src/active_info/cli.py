from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import typer
import uvicorn

from active_info.config import get_settings
from active_info.pipeline import fetch_download_snapshot, rerun_analysis_from_snapshot, run_pipeline
from active_info.scheduler import run_daily_scheduler
from active_info.static_export import export_static_site
from active_info.storage import ReportStorage
from active_info.web import create_app

app = typer.Typer(help="Active Info Aggregator CLI")


@app.command("run-once")
def run_once(report_date: Optional[str] = typer.Option(default=None, help="YYYY-MM-DD")) -> None:
    settings = get_settings()
    storage = ReportStorage(settings.db_path)

    run_dt = date.fromisoformat(report_date) if report_date else None
    result = run_pipeline(settings, storage, run_date=run_dt)
    typer.echo(
        f"Done. date={result['report_date']} total_items={result['total_items']} "
        f"md={result['report_markdown']}"
    )


@app.command("fetch-only")
def fetch_only(report_date: Optional[str] = typer.Option(default=None, help="YYYY-MM-DD")) -> None:
    settings = get_settings()
    run_dt = date.fromisoformat(report_date) if report_date else None
    result = fetch_download_snapshot(settings, run_date=run_dt)
    typer.echo(
        f"Fetched. date={result['report_date']} total_items={result['total_items']} "
        f"snapshot={result['snapshot_json']}"
    )


@app.command("parse-only")
def parse_only(report_date: Optional[str] = typer.Option(default=None, help="YYYY-MM-DD, default latest snapshot")) -> None:
    settings = get_settings()
    storage = ReportStorage(settings.db_path)
    try:
        result = rerun_analysis_from_snapshot(settings, storage, report_date=report_date)
    except ValueError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(
        f"Parsed. date={result['report_date']} total_items={result['total_items']} "
        f"md={result['report_markdown']}"
    )


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    settings = get_settings()
    web_app = create_app(settings)
    uvicorn.run(web_app, host=host, port=port)


@app.command("scheduler")
def scheduler(daily_at: str = typer.Option("08:30", help="HH:MM local time")) -> None:
    settings = get_settings()
    run_daily_scheduler(settings, daily_at=daily_at)


@app.command("rerun-analysis")
def rerun_analysis(report_date: Optional[str] = typer.Option(default=None, help="YYYY-MM-DD, default latest snapshot")) -> None:
    # Backward-compatible alias for parse-only.
    parse_only(report_date=report_date)


@app.command("export-static")
def export_static(
    output_dir: str = typer.Option("site", help="静态站点输出目录"),
    latest_only: bool = typer.Option(False, help="仅导出最新报告"),
) -> None:
    settings = get_settings()
    try:
        result = export_static_site(settings, Path(output_dir), latest_only=latest_only)
    except ValueError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Exported static site. reports={result['reports']} out={result['output_dir']}")


if __name__ == "__main__":
    app()
