"""Drawdown, profit factor, and sample-half splits."""

from __future__ import annotations

import datetime as dt
import math

from backtests.gap_and_go.metrics import half_split, profit_factor, summarize
from backtests.gap_and_go.strategy import Trade


def _trade(session: dt.date, r_multiple: float, pnl: float, symbol: str = "AAA") -> Trade:
    return Trade(
        symbol=symbol,
        session=session,
        entry_time=dt.time(10, 0),
        exit_time=dt.time(11, 0),
        entry=10.0,
        stop=9.0,
        target=12.0,
        exit=10.0 + r_multiple,
        shares=1,
        r_multiple=r_multiple,
        pnl=pnl,
        exit_reason="target" if r_multiple > 0 else "stop",
        gap=0.02,
        rvol=1.5,
        atr=1.0,
        or_high=10.0,
        or_low=9.0,
    )


def test_drawdown_and_profit_factor() -> None:
    day = dt.date(2026, 8, 3)
    trades = [
        _trade(day, 1.0, 10.0),
        _trade(day, -0.3, -3.0),
        _trade(day, -0.4, -4.0),
        _trade(day, 0.2, 2.0),
    ]
    stats = summarize(trades)
    assert stats["trades"] == 4
    assert stats["win_rate"] == 0.5
    assert stats["max_dd_dollars"] == -7.0
    assert stats["profit_factor"] == 12.0 / 7.0
    assert profit_factor([5.0]) == math.inf
    assert profit_factor([]) is None
    assert summarize([])["trades"] == 0


def test_half_split_uses_the_sample_midpoint() -> None:
    dates = [dt.date(2026, 8, d) for d in (3, 4, 5, 6)]
    trades = [
        _trade(dates[0], 1.0, 1.0),
        _trade(dates[3], -1.0, -1.0),
    ]
    midpoint, first, second = half_split(trades, dates)
    assert midpoint == dates[2]
    assert [trade.session for trade in first] == [dates[0]]
    assert [trade.session for trade in second] == [dates[3]]
