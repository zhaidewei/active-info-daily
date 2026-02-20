from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from active_info.models import Report


class ReportStorage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    report_date TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    total_items INTEGER NOT NULL,
                    markdown TEXT NOT NULL,
                    json_content TEXT NOT NULL
                )
                """
            )

    def upsert_report(self, report: Report) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (report_date, created_at, total_items, markdown, json_content)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(report_date) DO UPDATE SET
                    created_at=excluded.created_at,
                    total_items=excluded.total_items,
                    markdown=excluded.markdown,
                    json_content=excluded.json_content
                """,
                (
                    report.report_date,
                    report.created_at.isoformat(),
                    report.total_items,
                    report.markdown,
                    report.json_content,
                ),
            )

    def list_reports(self, limit: int = 60) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT report_date, created_at, total_items FROM reports ORDER BY report_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_report(self, report_date: str) -> Optional[Dict[str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_date, created_at, total_items, markdown, json_content FROM reports WHERE report_date = ?",
                (report_date,),
            ).fetchone()
        return dict(row) if row else None

    def latest_report(self) -> Optional[Dict[str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_date, created_at, total_items, markdown, json_content FROM reports ORDER BY report_date DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None


def build_report(date_key: str, total_items: int, markdown: str, json_content: str) -> Report:
    return Report(
        report_date=date_key,
        created_at=datetime.utcnow(),
        total_items=total_items,
        markdown=markdown,
        json_content=json_content,
    )
