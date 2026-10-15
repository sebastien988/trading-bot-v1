"""CSV writers and the prototype-trade comparison."""

from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd

from backtests.gap_and_go.metrics import by_symbol, chronological, half_split, summarize
from backtests.gap_and_go.strategy import Trade


def _num(value: float | int | None, digits: int | None = None) -> float | int | None | str:
    if value is None:
        return None
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if digits is not None and isinstance(value, float):
        return round(value, digits)
    return value


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    for trade in chronological(trades):
        rows.append(
            {
                "symbol": trade.symbol,
                "date": trade.session.isoformat(),
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
                "entry": round(trade.entry, 4),
                "stop": round(trade.stop, 4),
                "target": round(trade.target, 4),
                "exit": round(trade.exit, 4),
                "shares": trade.shares,
                "r_multiple": trade.r_multiple,
                "pnl": trade.pnl,
                "exit_reason": trade.exit_reason,
                "gap": trade.gap,
                "rvol": trade.rvol,
                "atr": trade.atr,
                "or_high": round(trade.or_high, 4),
                "or_low": round(trade.or_low, 4),
            }
        )
    return pd.DataFrame(rows)


def summary_row(label: str, trades: list[Trade], extra: dict | None = None) -> dict:
    stats = summarize(trades)
    row = {
        "run": label,
        "trades": stats["trades"],
        "win_rate_pct": _num(None if stats["win_rate"] is None else float(stats["win_rate"]) * 100, 1),
        "avg_r": _num(stats["avg_r"], 3),
        "profit_factor": _num(stats["profit_factor"], 2),
        "max_dd_dollars": _num(stats["max_dd_dollars"], 2),
        "max_dd_r": _num(stats["max_dd_r"], 3),
        "pnl": _num(stats["pnl"], 2),
        "expectancy_at_2k": _num(stats["expectancy_at_2k"], 2),
    }
    if extra:
        row.update(extra)
    return row


def half_rows(label: str, trades: list[Trade], session_dates: list[dt.date]) -> list[dict]:
    midpoint, first, second = half_split(trades, session_dates)
    rows = []
    for name, subset in (("H1", first), ("H2", second)):
        row = summary_row(f"{label}_{name}", subset)
        row["half"] = name
        row["midpoint_session"] = None if midpoint is None else midpoint.isoformat()
        rows.append(row)
    return rows


def symbol_rows(label: str, trades: list[Trade]) -> list[dict]:
    rows = []
    for symbol, stats in by_symbol(trades).items():
        row = {
            "run": label,
            "symbol": symbol,
            "trades": stats["trades"],
            "win_rate_pct": _num(None if stats["win_rate"] is None else float(stats["win_rate"]) * 100, 1),
            "avg_r": _num(stats["avg_r"], 3),
            "profit_factor": _num(stats["profit_factor"], 2),
            "max_dd_dollars": _num(stats["max_dd_dollars"], 2),
            "pnl": _num(stats["pnl"], 2),
        }
        rows.append(row)
    return rows


def write_frame(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def compare_to_reference(trades: list[Trade], reference: pd.DataFrame) -> pd.DataFrame:
    """Match long prototype trades on symbol and session date.

    Prices in the prototype file are rounded to the cent. A row matches when
    entry, stop, exit, and shares agree at that precision and the entry clock
    agrees.
    """

    ours = {(trade.symbol, trade.session.isoformat()): trade for trade in trades}
    seen: set[tuple[str, str]] = set()
    rows = []
    for record in reference.itertuples(index=False):
        key = (str(record.sym), str(record.date))
        seen.add(key)
        trade = ours.get(key)
        if trade is None:
            rows.append({"symbol": key[0], "date": key[1], "status": "missing"})
            continue
        entry_ok = round(trade.entry, 2) == round(float(record.entry), 2)
        stop_ok = round(trade.stop, 2) == round(float(record.stop), 2)
        exit_ok = round(trade.exit, 2) == round(float(record.exit), 2)
        shares_ok = trade.shares == int(record.shares)
        time_ok = trade.entry_time.isoformat() == str(record.time)
        status = "match" if all((entry_ok, stop_ok, exit_ok, shares_ok, time_ok)) else "mismatch"
        rows.append(
            {
                "symbol": key[0],
                "date": key[1],
                "status": status,
                "ref_time": str(record.time),
                "our_time": trade.entry_time.isoformat(),
                "ref_entry": round(float(record.entry), 2),
                "our_entry": round(trade.entry, 2),
                "ref_stop": round(float(record.stop), 2),
                "our_stop": round(trade.stop, 2),
                "ref_exit": round(float(record.exit), 2),
                "our_exit": round(trade.exit, 2),
                "ref_shares": int(record.shares),
                "our_shares": trade.shares,
                "ref_r": float(record.R),
                "our_r": trade.r_multiple,
                "entry_ok": entry_ok,
                "stop_ok": stop_ok,
                "exit_ok": exit_ok,
                "shares_ok": shares_ok,
                "time_ok": time_ok,
            }
        )
    for key, trade in sorted(ours.items()):
        if key in seen:
            continue
        rows.append(
            {
                "symbol": key[0],
                "date": key[1],
                "status": "extra",
                "our_time": trade.entry_time.isoformat(),
                "our_entry": round(trade.entry, 2),
                "our_stop": round(trade.stop, 2),
                "our_exit": round(trade.exit, 2),
                "our_shares": trade.shares,
                "our_r": trade.r_multiple,
            }
        )
    return pd.DataFrame(rows)
