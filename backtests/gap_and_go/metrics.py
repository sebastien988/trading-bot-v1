"""Summary statistics for hypothetical Gap-and-Go trades."""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from backtests.gap_and_go.strategy import Trade


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def profit_factor(pnls: list[float]) -> float | None:
    gains = sum(value for value in pnls if value > 0)
    losses = -sum(value for value in pnls if value < 0)
    if losses == 0:
        if gains == 0:
            return None
        return math.inf
    return gains / losses


def chronological(trades: list[Trade]) -> list[Trade]:
    return sorted(trades, key=lambda trade: (trade.session, trade.exit_time, trade.symbol, trade.entry_time))


def summarize(trades: list[Trade]) -> dict[str, float | int | None]:
    ordered = chronological(trades)
    rs = [trade.r_multiple for trade in ordered]
    pnls = [trade.pnl for trade in ordered]
    count = len(ordered)
    if count == 0:
        return {
            "trades": 0,
            "win_rate": None,
            "avg_r": None,
            "profit_factor": None,
            "max_dd_dollars": 0.0,
            "max_dd_r": 0.0,
            "pnl": 0.0,
            "expectancy_at_2k": None,
        }
    wins = sum(1 for value in rs if value > 0)
    avg_r = sum(rs) / count
    return {
        "trades": count,
        "win_rate": wins / count,
        "avg_r": avg_r,
        "profit_factor": profit_factor(pnls),
        "max_dd_dollars": _max_drawdown(pnls),
        "max_dd_r": _max_drawdown(rs),
        "pnl": sum(pnls),
        "expectancy_at_2k": avg_r * 2000.0,
    }


def half_split(
    trades: list[Trade],
    session_dates: list[dt.date],
) -> tuple[dt.date | None, list[Trade], list[Trade]]:
    """Split on the midpoint session of the sample, not of the trade dates."""

    if not session_dates:
        return None, [], []
    ordered_dates = sorted(set(session_dates))
    midpoint = ordered_dates[len(ordered_dates) // 2]
    first = [trade for trade in trades if trade.session < midpoint]
    second = [trade for trade in trades if trade.session >= midpoint]
    return midpoint, first, second


def by_symbol(trades: list[Trade]) -> dict[str, dict[str, float | int | None]]:
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.symbol].append(trade)
    return {symbol: summarize(grouped[symbol]) for symbol in sorted(grouped)}
