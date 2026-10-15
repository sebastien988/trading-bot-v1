"""Fill, stop, and filter tests for the long-only Gap-and-Go replay."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pandas as pd
import pytest

from backtests.gap_and_go.config import SPEC_1H, SPEC_5M
from backtests.gap_and_go.strategy import (
    Session,
    assign_rvol,
    evaluate_day,
    opening_range,
)

DAY = "2026-08-03"


def make_bars(start: str, end: str, freq: str, price: float = 99.0) -> pd.DataFrame:
    index = pd.date_range(start, end, freq=freq, tz="America/New_York")
    return pd.DataFrame(
        {
            "Open": price,
            "High": price + 0.10,
            "Low": price - 0.10,
            "Close": price,
            "Volume": 1_000.0,
            "atr": 1.0,
        },
        index=index,
    )


def patch(frame: pd.DataFrame, clock: dt.time, **values: float) -> None:
    mask = [stamp.time() == clock for stamp in frame.index]
    for column, value in values.items():
        frame.loc[mask, column] = value


def five_minute_day() -> pd.DataFrame:
    frame = make_bars(f"{DAY} 09:30", f"{DAY} 15:55", "5min", price=99.0)
    for clock in (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40)):
        patch(frame, clock, Open=99.0, High=100.0, Low=98.0, Close=99.5, Volume=5_000.0, atr=1.0)
    patch(frame, dt.time(9, 45), Open=99.4, High=99.6, Low=99.2, Close=99.5, atr=1.0)
    return frame


def session(frame: pd.DataFrame, prev_close: float = 97.0) -> Session:
    return Session(
        symbol="TEST",
        session=frame.index[0].date(),
        frame=frame,
        prev_close=prev_close,
        or_volume=15_000.0,
        tradable=True,
    )


def test_opening_range_is_the_first_fifteen_minutes() -> None:
    bounds = opening_range(five_minute_day(), 5)
    assert bounds is not None
    high, low, volume, atr = bounds
    assert high == 100.0
    assert low == 98.0
    assert volume == 15_000.0
    assert atr == 1.0


def test_buy_stop_fills_at_level_plus_slippage_and_targets_two_r() -> None:
    frame = five_minute_day()
    # Open is below the stop level; the bar trades through 100.02.
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    patch(frame, dt.time(11, 0), Open=101.0, High=105.0, Low=100.8, Close=104.5)
    trade, reason = evaluate_day(session(frame), 1.5, SPEC_5M)
    assert reason == "trade"
    assert trade is not None
    assert trade.entry_time == dt.time(10, 0)
    assert trade.entry == pytest.approx(100.04, abs=1e-9)  # max(99.5, 100.02) + 0.02
    assert trade.stop == 98.0
    assert trade.target == pytest.approx(100.04 + 2 * (100.04 - 98.0), abs=1e-9)
    assert trade.exit == trade.target
    assert trade.exit_reason == "target"
    assert trade.r_multiple == 2.0
    assert trade.shares == 980  # floor(2000 / 2.04), under the notional cap
    assert trade.pnl == trade.shares * (trade.exit - trade.entry)


def test_later_bar_gapping_through_the_stop_fills_at_the_open_plus_slippage() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=104.0, High=104.5, Low=103.5, Close=104.2)
    trade, reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert reason == "trade"
    assert trade is not None
    # 09:45 opened below the range high, so the order was working.
    # The 10:00 gap through the level is a real stop fill, not a skip.
    assert trade.entry == 104.02
    assert trade.entry_time == dt.time(10, 0)


def test_skip_when_the_0945_open_is_already_above_the_range_high() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(9, 45), Open=100.5, High=101.0, Low=100.2, Close=100.8)
    patch(frame, dt.time(10, 0), Open=101.0, High=110.0, Low=100.8, Close=109.0)
    trade, reason = evaluate_day(session(frame), 3.0, SPEC_5M)
    assert trade is None
    assert reason == "skip_open"

    compat = replace(SPEC_5M, skip_if_open_above_high=False)
    chased, chased_reason = evaluate_day(session(frame), 3.0, compat)
    assert chased_reason == "trade"
    assert chased is not None
    assert chased.entry_time == dt.time(9, 45)
    assert chased.entry == 100.52  # max(100.5, 100.02) + 0.02


def test_same_bar_stop_and_target_counts_the_stop() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    patch(frame, dt.time(10, 30), Open=100.0, High=110.0, Low=90.0, Close=100.0)
    trade, reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert reason == "trade"
    assert trade is not None
    assert trade.exit_reason == "stop"
    assert trade.exit == 98.0 - 0.02
    assert trade.r_multiple < 0


def test_stop_gap_fills_at_the_open_minus_slippage() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    patch(frame, dt.time(10, 30), Open=97.0, High=97.4, Low=96.5, Close=96.8)
    trade, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert trade is not None
    assert trade.exit_reason == "stop"
    assert trade.exit == 97.0 - 0.02


def test_stop_on_the_entry_bar_is_taken_before_the_target() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=110.0, Low=90.0, Close=100.0)
    trade, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert trade is not None
    assert trade.entry_time == dt.time(10, 0)
    assert trade.exit_time == dt.time(10, 0)
    assert trade.exit_reason == "stop"


def test_tight_stop_widens_to_one_atr_and_a_wider_range_does_not() -> None:
    frame = five_minute_day()
    for clock in (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40)):
        patch(frame, clock, High=100.0, Low=99.5, atr=1.0)
    patch(frame, dt.time(10, 0), Open=99.8, High=100.2, Low=99.7, Close=100.1)
    patch(frame, dt.time(11, 0), Open=101.0, High=103.0, Low=100.5, Close=102.5)
    widened, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert widened is not None
    assert widened.entry == pytest.approx(100.04, abs=1e-9)
    assert widened.stop == pytest.approx(widened.entry - 1.0, abs=1e-9)
    assert widened.target == pytest.approx(widened.entry + 2.0, abs=1e-9)
    assert widened.shares == 2000

    for clock in (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40)):
        patch(frame, clock, Low=98.0, atr=2.0)
    unchanged, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert unchanged is not None
    assert unchanged.entry == pytest.approx(100.04, abs=1e-9)
    # Risk is about $2.04, which is wider than the $2 ATR, so the range low stands.
    assert unchanged.stop == 98.0
    assert abs(unchanged.stop - (unchanged.entry - 2.0)) > 1e-6


def test_nan_atr_does_not_widen_or_crash() -> None:
    frame = five_minute_day()
    frame["atr"] = float("nan")
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    trade, reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert reason == "trade"
    assert trade is not None
    assert trade.stop == 98.0


def test_no_entry_after_1430_and_1430_bar_still_allowed() -> None:
    late = five_minute_day()
    patch(late, dt.time(14, 35), Open=99.5, High=101.0, Low=99.4, Close=100.5)
    trade, reason = evaluate_day(session(late), 2.0, SPEC_5M)
    assert trade is None
    assert reason == "no_fill"

    on_cutoff = five_minute_day()
    patch(on_cutoff, dt.time(14, 30), Open=99.5, High=101.0, Low=99.4, Close=100.4)
    filled, filled_reason = evaluate_day(session(on_cutoff), 2.0, SPEC_5M)
    assert filled_reason == "trade"
    assert filled is not None
    assert filled.entry_time == dt.time(14, 30)


def test_honest_flat_ignores_the_1545_bar_extremes() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    patch(frame, dt.time(15, 45), Open=101.0, High=120.0, Low=80.0, Close=110.0)
    trade, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert trade is not None
    assert trade.exit_reason == "flat"
    assert trade.exit_time == dt.time(15, 45)
    assert trade.exit == 101.0 - 0.02

    compat = replace(SPEC_5M, honest_flat=False)
    looked, _reason = evaluate_day(session(frame), 2.0, compat)
    assert looked is not None
    # The prototype inspects the flat bar's low before its open, so the stop wins.
    assert looked.exit_reason == "stop"


def test_unfilled_stop_is_cancelled() -> None:
    trade, reason = evaluate_day(session(five_minute_day()), 2.0, SPEC_5M)
    assert trade is None
    assert reason == "no_fill"


def test_filters_are_long_only_and_inclusive_at_the_threshold() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    base = session(frame, prev_close=97.0)  # 99/97 - 1 > 2%
    assert evaluate_day(base, 1.5, SPEC_5M)[0] is not None
    assert evaluate_day(base, 1.5, replace(SPEC_5M, gap_min=0.03))[1] == "gap"
    assert evaluate_day(session(frame, prev_close=110.0), 5.0, SPEC_5M)[1] == "gap"
    assert evaluate_day(base, 1.49, SPEC_5M)[1] == "rvol"
    assert evaluate_day(base, 1.5, SPEC_5M)[0] is not None
    assert evaluate_day(base, None, SPEC_5M)[1] == "rvol_history"

    exact = five_minute_day()
    patch(exact, dt.time(9, 30), Open=102.0)
    for clock in (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40)):
        patch(exact, clock, High=103.0, Low=101.5)
    patch(exact, dt.time(10, 0), Open=102.2, High=103.2, Low=102.0, Close=103.0)
    # 102 / 100 - 1 == 0.02 exactly.
    trade, reason = evaluate_day(session(exact, prev_close=100.0), 1.5, SPEC_5M)
    assert reason == "trade"
    assert trade is not None


def test_notional_cap_and_share_floor() -> None:
    frame = five_minute_day()
    for clock in (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40)):
        patch(frame, clock, Open=500.0, High=500.0, Low=499.90, Close=499.95, atr=0.01)
    patch(frame, dt.time(9, 45), Open=499.95, High=499.98, Low=499.92)
    patch(frame, dt.time(10, 0), Open=500.0, High=500.10, Low=499.95, Close=500.05)
    trade, reason = evaluate_day(session(frame, prev_close=490.0), 2.0, SPEC_5M)
    assert reason == "trade"
    assert trade is not None
    assert trade.entry == pytest.approx(500.04, abs=1e-9)
    assert trade.shares == 999  # floor(500_000 / 500.04), not floor(2000 / 0.14)

    tiny = replace(SPEC_5M, risk_dollars=1.0)
    ordinary = five_minute_day()
    patch(ordinary, dt.time(10, 0), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    assert evaluate_day(session(ordinary), 2.0, tiny)[1] == "zero_shares"


def test_one_trade_per_day_and_missing_placement_bar() -> None:
    frame = five_minute_day()
    patch(frame, dt.time(10, 0), Open=99.5, High=110.0, Low=99.4, Close=105.0)
    patch(frame, dt.time(10, 5), Open=105.0, High=120.0, Low=104.0, Close=118.0)
    trade, _reason = evaluate_day(session(frame), 2.0, SPEC_5M)
    assert trade is not None
    assert trade.entry_time == dt.time(10, 0)

    broken = frame.drop(frame.index[frame.index.time == dt.time(9, 45)])
    assert opening_range(broken, 5) is None
    assert evaluate_day(session(broken), 2.0, SPEC_5M)[1] == "incomplete"


def test_rvol_uses_prior_sessions_only() -> None:
    volumes: list[float | None] = [100.0] * 20 + [150.0]
    ratios = assign_rvol(volumes, lookback=20, min_prior=20)
    assert ratios[19] is None
    assert ratios[20] == 1.5
    short = assign_rvol([100.0] * 5 + [200.0], lookback=20, min_prior=5)
    assert short[4] is None
    assert short[5] == 2.0


def test_hourly_proxy_exits_at_the_1530_open_and_cancels_the_1430_hour() -> None:
    frame = make_bars(f"{DAY} 09:30", f"{DAY} 15:30", "60min", price=99.0)
    patch(frame, dt.time(9, 30), Open=99.0, High=100.0, Low=98.0, Close=99.5, Volume=20_000, atr=1.0)
    patch(frame, dt.time(10, 30), Open=99.4, High=99.6, Low=99.2, Close=99.5)
    patch(frame, dt.time(11, 30), Open=99.5, High=100.5, Low=99.4, Close=100.2)
    # The 15:30 hour contains 15:45. Its high trades the target; that path is unknowable.
    patch(frame, dt.time(15, 30), Open=101.0, High=120.0, Low=90.0, Close=110.0)
    trade, reason = evaluate_day(session(frame), 2.0, SPEC_1H)
    assert reason == "trade"
    assert trade is not None
    assert trade.entry_time == dt.time(11, 30)
    assert trade.entry == pytest.approx(100.04, abs=1e-9)
    assert trade.exit_reason == "flat"
    assert trade.exit_time == dt.time(15, 30)
    assert trade.exit == 101.0 - 0.02

    late = make_bars(f"{DAY} 09:30", f"{DAY} 15:30", "60min", price=99.0)
    patch(late, dt.time(9, 30), Open=99.0, High=100.0, Low=98.0, Close=99.4, atr=1.0)
    patch(late, dt.time(10, 30), Open=99.2, High=99.4, Low=99.0)
    patch(late, dt.time(14, 30), Open=99.5, High=110.0, Low=99.4, Close=108.0)
    assert evaluate_day(session(late), 2.0, SPEC_1H)[1] == "no_fill"

    gapped = make_bars(f"{DAY} 09:30", f"{DAY} 15:30", "60min", price=99.0)
    patch(gapped, dt.time(9, 30), Open=99.0, High=100.0, Low=98.0, Close=99.4, atr=1.0)
    patch(gapped, dt.time(10, 30), Open=100.4, High=101.0, Low=100.1, Close=100.8)
    assert evaluate_day(session(gapped), 2.0, SPEC_1H)[1] == "skip_open"
