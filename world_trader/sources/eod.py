"""Daily OHLCV and corporate actions from the Yahoo Finance v8 chart endpoint.

Admission status (research/manifests/sources_v1.json, plan §3.3): evaluated-only
source. The v8 chart endpoint returned complete daily bars, adjclose, dividend and
split events keyless on 2026-11-04. It is an UNLABELED free endpoint: no registered
key, no published access contract, no entitlement guarantee. Panels built from it
are labelled yahoo-chart-derived and require an independent cross-check before any
performance claim (P1 does spot cross-checks vs the local CBOE archive spots).
"""

from datetime import datetime, timezone

from ..models import DataError, record, utc
from . import identifier, require

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64)"


def chart(client, symbol: str, *, start: str, end: str):
    """Daily bars + div/split events for `symbol` in [start, end] (ISO dates).

    Bars are split-adjusted; `adjclose` additionally reflects distributions.
    Row semantics: observed date is the exchange session (UTC-midnight key),
    payload keeps raw OHLCV, adjclose, and per-bar timezone-qualified market time.
    """
    identifier(symbol, "symbol")
    for name, value in (("start", start), ("end", end)):
        datetime.fromisoformat(value)
    if start > end:
        raise DataError("start must be on or before end")
    period1 = int(datetime.fromisoformat(start + "T00:00:00+00:00").timestamp())
    period2 = int(datetime.fromisoformat(end + "T23:59:59+00:00").timestamp())
    doc = client.get(
        f"{BASE}/{symbol.upper()}",
        params={"period1": period1, "period2": period2, "interval": "1d", "events": "div,split"},
        headers={"User-Agent": USER_AGENT},
        ttl=86400,
    )
    result = require(require(doc.payload, "chart", dict), "result", list)
    if not result:
        raise DataError(f"Empty chart result for {symbol}")
    first = require(result[0], "meta", dict)
    if first.get("symbol", "").upper() != symbol.upper():
        raise DataError("Chart symbol echo mismatch")
    return doc, result[0]


def _bars(doc, payload, symbol):
    timestamps = require(payload, "timestamp", list)
    quote = require(require(payload, "indicators", dict), "quote", list)[0]
    adj = require(payload, "indicators", dict).get("adjclose")
    adjclose = require(adj[0], "adjclose", list) if adj else None
    rows = []
    for i, raw in enumerate(timestamps):
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise DataError("Unexpected chart timestamp")
        session = datetime.fromtimestamp(raw, timezone.utc)
        values = {}
        for field in ("open", "high", "low", "close", "volume"):
            values[field] = quote.get(field, [None] * len(timestamps))[i] if quote.get(field) else None
        adjusted = adjclose[i] if adjclose and i < len(adjclose) else None
        if any(v is not None and not isinstance(v, (int, float)) for v in values.values()):
            raise DataError("Unexpected chart quote schema")
        if adjusted is not None and not isinstance(adjusted, (int, float)):
            raise DataError("Unexpected adjclose schema")
        rows.append(record(
            doc, source="yahoo-chart", dataset="daily_bars", entity=symbol.upper(),
            key=session.date().isoformat(), observed=session.date().isoformat(),
            basis="first_seen",
            data={
                "date": session.date().isoformat(),
                "market_time_utc": utc(session),
                **values,
                "adjclose": adjusted,
            },
        ))
    return rows


def _events(doc, payload, symbol):
    rows = []
    events = payload.get("events") or {}
    dividends = events.get("dividends") or {}
    splits = events.get("splits") or {}
    for item in dividends.values():
        if not isinstance(item, dict) or not all(k in item for k in ("date", "amount")):
            raise DataError("Unexpected dividend event schema")
        ex_date = datetime.fromtimestamp(item["date"], timezone.utc).date().isoformat()
        rows.append(record(
            doc, source="yahoo-chart", dataset="dividends", entity=symbol.upper(),
            key=ex_date, observed=ex_date, basis="first_seen",
            data={"date": ex_date, "amount": float(item["amount"])},
        ))
    for item in splits.values():
        if not isinstance(item, dict) or not all(k in item for k in ("date", "numerator", "denominator")):
            raise DataError("Unexpected split event schema")
        effective = datetime.fromtimestamp(item["date"], timezone.utc).date().isoformat()
        denominator = float(item["denominator"])
        if denominator <= 0:
            raise DataError("Split denominator must be positive")
        rows.append(record(
            doc, source="yahoo-chart", dataset="splits", entity=symbol.upper(),
            key=effective, observed=effective, basis="first_seen",
            data={"date": effective, "numerator": float(item["numerator"]),
                  "denominator": denominator, "ratio": item.get("splitRatio")},
        ))
    return rows


def daily(client, symbol: str, *, start: str, end: str):
    """Bars + corporate actions for one symbol; deduplicated by record id."""
    doc, payload = chart(client, symbol, start=start, end=end)
    rows = _bars(doc, payload, symbol) + _events(doc, payload, symbol)
    unique = {}
    for row in rows:
        unique[(row.dataset, row.record_id)] = row
    return sorted(unique.values(), key=lambda row: (row.dataset, row.record_id))
