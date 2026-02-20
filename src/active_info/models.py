from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    category: str
    published_at: Optional[datetime] = None
    summary: str = ""
    score: float = 0.0


@dataclass
class AnalysisResult:
    overview: str
    breakthroughs: list[str] = field(default_factory=list)
    investment_signals: list[str] = field(default_factory=list)
    overlooked_trends: list[str] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)


@dataclass
class Report:
    report_date: str
    created_at: datetime
    total_items: int
    markdown: str
    json_content: str
