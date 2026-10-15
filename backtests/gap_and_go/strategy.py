"""Long-only Gap-and-Go fill model.

Research replay of historical bars. No broker, no orders, no shorts.

Opening range on 5-minute bars is 09:30, 09:35, and 09:40 ET (the 15 minutes
that end at 09:45). A buy-stop is conceptually placed at 09:45 at
``range high + stop_offset``. The first bar that trades through that level
fills at ``max(bar open, level) + slippage``. If that placement bar already
opens above the range high, the day is skipped when
``skip_if_open_above_high`` is set.

The stop starts at the opening-range low. If ``entry - stop`` is tighter than
one ATR(14), the stop is widened to ``entry - ATR``. The target is
``entry + 2R``. A bar that trades both prices counts the stop. The target is
a resting limit and is filled at the limit (no extra slippage and no price
improvement). Stops and the 15:45 flatten pay ``slippage`` per share.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pandas as pd

from backtests.gap_and_go.config import Rules

EXIT_STOP = "stop"
EXIT_TARGET = "target"
EXIT_FLAT = "flat"


@dataclass(frozen=True)
class Session:
    symbol: str
    session: dt.date
    frame: pd.DataFrame
    prev_close: float | None
    or_volume: float | None
    tradable: bool
    block_reason: str | None = None


@dataclass(frozen=True)
class Trade:
    symbol: str
    session: dt.date
    entry_time: dt.time
    exit_time: dt.time
    entry: float
    stop: float
    target: float
    exit: float
    shares: int
    r_multiple: float
    pnl: float
    exit_reason: str
    gap: float
    rvol: float
    atr: float
    or_high: float
    or_low: float


def add_atr(frame: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Simple moving average of true range, matching the prototype."""

    prev = frame["Close"].shift(1)
    true_range = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - prev).abs(),
            (frame["Low"] - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out = frame.copy()
    out["atr"] = true_range.rolling(window).mean()
    return out


def assign_rvol(
    volumes: list[float | None],
    lookback: int,
    min_prior: int,
) -> list[float | None]:
    """Volume divided by the mean of up to ``lookback`` prior valid sessions.

    Returns None until ``min_prior`` prior prints exist. The current session
    is not part of its own average.
    """

    out: list[float | None] = []
    for index, volume in enumerate(volumes):
        window = [
            value
            for value in volumes[max(0, index - lookback) : index]
            if value is not None and math.isfinite(value)
        ]
        if volume is None or not math.isfinite(volume) or len(window) < min_prior:
            out.append(None)
            continue
        baseline = float(sum(window) / len(window))
        out.append(None if baseline <= 0 else float(volume) / baseline)
    return out


def _clock(ts: pd.Timestamp) -> dt.time:
    return ts.time()


def _or_clocks(bar_minutes: int) -> tuple[dt.time, ...] | None:
    if bar_minutes == 5:
        return (dt.time(9, 30), dt.time(9, 35), dt.time(9, 40))
    if bar_minutes == 60:
        # Coarse proxy: the only bar that covers 09:30–09:45 is the 09:30 hour.
        return (dt.time(9, 30),)
    return None


def opening_range(
    day: pd.DataFrame, bar_minutes: int
) -> tuple[float, float, float, float] | None:
    """Return (high, low, volume, atr) once the placement bar exists.

    ATR is the value on the last opening-range bar, which is known when the
    stop is placed. None means the session does not have the expected clocks.
    """

    clocks = _or_clocks(bar_minutes)
    if clocks is None or len(day) <= len(clocks):
        return None
    for offset, expected in enumerate(clocks):
        if _clock(day.index[offset]) != expected:
            return None
    placement = dt.time(9, 45) if bar_minutes == 5 else dt.time(10, 30)
    if _clock(day.index[len(clocks)]) != placement:
        return None
    window = day.iloc[: len(clocks)]
    atr_value = float(window["atr"].iloc[-1]) if "atr" in window.columns else math.nan
    return (
        float(window["High"].max()),
        float(window["Low"].min()),
        float(window["Volume"].sum()),
        atr_value,
    )


def _entry_cancelled(ts: pd.Timestamp, bar_minutes: int, cutoff: dt.time) -> bool:
    """Cancel a resting stop once the bar can only trade after the cutoff.

    A 5-minute bar stamped 14:30 still trades the 14:30–14:35 window, which
    the prototype allowed (``time > 14:30``). An hourly bar stamped 14:30
    trades until 15:30, so it is cancelled.
    """

    stamp = _clock(ts)
    if bar_minutes >= 30:
        return stamp >= cutoff
    return stamp > cutoff


def _spans_past_flat(ts: pd.Timestamp, bar_minutes: int, flat: dt.time) -> bool:
    start = _clock(ts)
    start_m = start.hour * 60 + start.minute
    flat_m = flat.hour * 60 + flat.minute
    return start_m < flat_m < start_m + bar_minutes


def has_flat_opportunity(day: pd.DataFrame, bar_minutes: int, flat: dt.time) -> bool:
    """True when some bar starts at the flat time or contains it."""

    for stamp in day.index:
        if _clock(stamp) >= flat or _spans_past_flat(stamp, bar_minutes, flat):
            return True
    return False


def _stop_or_target(
    open_px: float,
    high_px: float,
    low_px: float,
    stop: float,
    target: float,
    slippage: float,
) -> tuple[float, str] | None:
    """Stop is tested before the target. A gap through the stop fills at the open."""

    if low_px <= stop:
        return min(stop, open_px) - slippage, EXIT_STOP
    if high_px >= target:
        return target, EXIT_TARGET
    return None


def _ambiguous_flat_open(
    open_px: float,
    stop: float,
    target: float,
    slippage: float,
) -> tuple[float, str]:
    """The bar contains the flat time. Only its open is a known pre-flat price."""

    if open_px <= stop:
        return min(stop, open_px) - slippage, EXIT_STOP
    if open_px >= target:
        return target, EXIT_TARGET
    return open_px - slippage, EXIT_FLAT


def _manage(
    day: pd.DataFrame,
    entry_index: int,
    stop: float,
    target: float,
    slippage: float,
    flat_time: dt.time,
    bar_minutes: int,
    honest_flat: bool,
) -> tuple[float, pd.Timestamp, str]:
    last_index = len(day) - 1
    for index in range(entry_index, len(day)):
        stamp = day.index[index]
        open_px = float(day["Open"].iloc[index])
        high_px = float(day["High"].iloc[index])
        low_px = float(day["Low"].iloc[index])
        if _spans_past_flat(stamp, bar_minutes, flat_time):
            price, reason = _ambiguous_flat_open(open_px, stop, target, slippage)
            return price, stamp, reason
        if _clock(stamp) >= flat_time:
            if not honest_flat:
                hit = _stop_or_target(open_px, high_px, low_px, stop, target, slippage)
                if hit is not None:
                    return hit[0], stamp, hit[1]
            return open_px - slippage, stamp, EXIT_FLAT
        hit = _stop_or_target(open_px, high_px, low_px, stop, target, slippage)
        if hit is not None:
            return hit[0], stamp, hit[1]
    close_px = float(day["Close"].iloc[last_index]) - slippage
    return close_px, day.index[last_index], EXIT_FLAT


def evaluate_day(
    session: Session,
    rvol: float | None,
    rules: Rules,
) -> tuple[Trade | None, str]:
    """Return the single long trade for this symbol-day, or a reject reason."""

    if session.block_reason:
        return None, session.block_reason
    if not session.tradable or session.prev_close is None:
        return None, "incomplete"
    bounds = opening_range(session.frame, rules.bar_minutes)
    if bounds is None:
        return None, "incomplete"
    or_high, or_low, _volume, atr = bounds
    if not math.isfinite(or_high) or not math.isfinite(or_low) or or_high <= 0:
        return None, "incomplete"
    if session.prev_close <= 0:
        return None, "incomplete"

    gap = float(session.frame["Open"].iloc[0]) / float(session.prev_close) - 1.0
    if gap < rules.gap_min:
        return None, "gap"
    if gap > rules.max_gap:
        return None, "huge_gap"
    if rvol is None:
        return None, "rvol_history"
    if rvol < rules.rvol_min:
        return None, "rvol"

    start = 1 if rules.bar_minutes == 60 else 3
    placement_open = float(session.frame["Open"].iloc[start])
    if rules.skip_if_open_above_high and placement_open > or_high:
        return None, "skip_open"

    level = or_high + rules.stop_offset
    entry_index: int | None = None
    for index in range(start, len(session.frame)):
        stamp = session.frame.index[index]
        if _clock(stamp) >= rules.flat_time or _spans_past_flat(stamp, rules.bar_minutes, rules.flat_time):
            break
        if _entry_cancelled(stamp, rules.bar_minutes, rules.entry_cutoff):
            break
        if float(session.frame["High"].iloc[index]) >= level:
            entry_index = index
            break
    if entry_index is None:
        return None, "no_fill"

    entry_bar = session.frame.iloc[entry_index]
    entry = max(float(entry_bar["Open"]), level) + rules.slippage
    stop = or_low
    if math.isfinite(atr) and (entry - stop) < rules.min_stop_atr * atr:
        stop = entry - rules.min_stop_atr * atr
    risk = entry - stop
    if risk <= 0 or entry <= 0:
        return None, "bad_risk"
    target = entry + rules.target_r * risk
    shares = int(min(rules.risk_dollars / risk, rules.max_notional / entry))
    if shares < 1:
        return None, "zero_shares"

    exit_px, exit_stamp, reason = _manage(
        session.frame,
        entry_index,
        stop,
        target,
        rules.slippage,
        rules.flat_time,
        rules.bar_minutes,
        rules.honest_flat,
    )
    trade = Trade(
        symbol=session.symbol,
        session=session.session,
        entry_time=_clock(session.frame.index[entry_index]),
        exit_time=_clock(exit_stamp),
        entry=entry,
        stop=stop,
        target=target,
        exit=exit_px,
        shares=shares,
        r_multiple=(exit_px - entry) / risk,
        pnl=shares * (exit_px - entry),
        exit_reason=reason,
        gap=gap,
        rvol=float(rvol),
        atr=float(atr) if math.isfinite(atr) else math.nan,
        or_high=or_high,
        or_low=or_low,
    )
    return trade, "trade"


def prepare_symbol(
    symbol: str,
    frame: pd.DataFrame,
    rules: Rules,
    split_dates: set[dt.date] | None = None,
) -> list[Session]:
    """Split a regular-hours series into sessions and attach prior close."""

    if frame.empty:
        return []
    enriched = add_atr(frame, rules.atr_window)
    blocked = split_dates or set()
    sessions: list[Session] = []
    previous_close: float | None = None
    for session_date, day in enriched.groupby(enriched.index.date, sort=True):
        day = day.sort_index()
        bounds = opening_range(day, rules.bar_minutes)
        or_volume = None if bounds is None else bounds[2]
        can_flat = has_flat_opportunity(day, rules.bar_minutes, rules.flat_time)
        reason = None
        tradable = bounds is not None and previous_close is not None and can_flat
        if session_date in blocked:
            reason = "split"
            tradable = False
        elif bounds is None or not can_flat:
            reason = "incomplete"
            tradable = False
        sessions.append(
            Session(
                symbol=symbol,
                session=session_date,
                frame=day,
                prev_close=previous_close,
                or_volume=or_volume,
                tradable=tradable,
                block_reason=reason if not tradable else None,
            )
        )
        previous_close = float(day["Close"].iloc[-1])
    return sessions


def run_sessions(sessions: list[Session], rules: Rules) -> tuple[list[Trade], dict[str, int]]:
    """One long trade per symbol per day. ``sessions`` must be a single symbol, in order."""

    rvols = assign_rvol(
        [session.or_volume for session in sessions],
        rules.rvol_lookback,
        rules.min_prior_sessions,
    )
    trades: list[Trade] = []
    counts: dict[str, int] = {}
    for session, rvol in zip(sessions, rvols):
        trade, reason = evaluate_day(session, rvol, rules)
        counts[reason] = counts.get(reason, 0) + 1
        if trade is not None:
            trades.append(trade)
    return trades, counts
