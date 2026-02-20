from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from active_info.config import Settings
from active_info.pipeline import run_pipeline
from active_info.storage import ReportStorage


def run_daily_scheduler(settings: Settings, daily_at: str = "08:30") -> None:
    storage = ReportStorage(settings.db_path)
    scheduler = BlockingScheduler()

    hour, minute = daily_at.split(":")

    def _job() -> None:
        run_pipeline(settings, storage)

    scheduler.add_job(
        _job,
        trigger="cron",
        hour=int(hour),
        minute=int(minute),
        id="daily_active_info_job",
        replace_existing=True,
    )

    # Startup run to avoid waiting until next cron window.
    _job()

    print(f"[{datetime.now().isoformat()}] Scheduler started, next runs at {daily_at} daily")
    scheduler.start()
