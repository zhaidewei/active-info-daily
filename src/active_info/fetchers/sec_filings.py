from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from dateutil import parser as date_parser

from active_info.models import NewsItem

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def _normalize_cik(cik_value: Any) -> str:
    try:
        return str(int(cik_value)).zfill(10)
    except (TypeError, ValueError):
        return ""


def _fetch_ticker_cik_map(headers: Dict[str, str], timeout: int) -> Dict[str, str]:
    try:
        resp = requests.get(TICKER_MAP_URL, headers=headers, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return {}

    mapping: Dict[str, str] = {}
    for row in payload.values():
        ticker = str(row.get("ticker", "")).upper().strip()
        cik = _normalize_cik(row.get("cik_str"))
        if ticker and cik:
            mapping[ticker] = cik
    return mapping


def _parse_recent_filings(
    ticker: str,
    cik: str,
    payload: Dict[str, Any],
    forms: set[str],
    lookback_days: int,
    per_ticker_limit: int,
) -> List[NewsItem]:
    recent = payload.get("filings", {}).get("recent", {})
    forms_list = list(recent.get("form", []))
    filing_dates = list(recent.get("filingDate", []))
    accessions = list(recent.get("accessionNumber", []))
    primary_docs = list(recent.get("primaryDocument", []))
    descriptions = list(recent.get("primaryDocDescription", []))

    now = datetime.utcnow()
    cutoff = now - timedelta(days=lookback_days)
    items: List[NewsItem] = []

    for idx, form in enumerate(forms_list):
        if idx >= len(filing_dates):
            continue
        if str(form).upper() not in forms:
            continue

        filing_date_raw = filing_dates[idx]
        try:
            filing_dt = date_parser.parse(str(filing_date_raw))
        except (ValueError, TypeError, OverflowError):
            continue

        if filing_dt < cutoff:
            continue

        accession = str(accessions[idx]).replace("-", "") if idx < len(accessions) else ""
        primary_doc = str(primary_docs[idx]) if idx < len(primary_docs) else ""
        description = str(descriptions[idx]) if idx < len(descriptions) else ""

        cik_no_zero = str(int(cik)) if cik else ""
        if accession and primary_doc and cik_no_zero:
            link = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zero}/{accession}/{primary_doc}"
        else:
            link = "https://www.sec.gov/edgar/search/"

        title = f"{ticker} filed {str(form).upper()} ({filing_dt.date().isoformat()})"
        summary = description if description else "SEC filing update"

        items.append(
            NewsItem(
                title=title,
                url=link,
                source="SEC Filing",
                category="earnings",
                summary=summary,
                published_at=filing_dt,
            )
        )
        if len(items) >= per_ticker_limit:
            break

    return items


def fetch_sec_filings(config: Dict[str, Any], timeout: int = 15) -> List[NewsItem]:
    if not config.get("enabled", False):
        return []

    tickers = [str(x).upper().strip() for x in config.get("tickers", []) if str(x).strip()]
    if not tickers:
        return []

    user_agent = str(config.get("user_agent", "active-info local-research contact@example.com")).strip()
    forms = {str(f).upper().strip() for f in config.get("forms", ["10-Q", "10-K", "8-K"]) if str(f).strip()}
    lookback_days = int(config.get("lookback_days", 45))
    per_ticker_limit = int(config.get("per_ticker_limit", 4))

    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
    ticker_map = _fetch_ticker_cik_map(headers=headers, timeout=timeout)
    if not ticker_map:
        return []

    all_items: List[NewsItem] = []
    for ticker in tickers:
        cik = ticker_map.get(ticker)
        if not cik:
            continue

        try:
            resp = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=headers, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError):
            continue

        items = _parse_recent_filings(
            ticker=ticker,
            cik=cik,
            payload=payload,
            forms=forms,
            lookback_days=lookback_days,
            per_ticker_limit=per_ticker_limit,
        )
        all_items.extend(items)

    return all_items
