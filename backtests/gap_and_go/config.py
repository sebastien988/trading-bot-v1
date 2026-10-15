"""Universe and rule sets for the Gap-and-Go research backtest."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

# Same universe as the July–October 2026 prototype. Point-in-time membership
# is not reconstructed; see the module README.
SYMBOLS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "NVDA",
    "TSLA",
    "META",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "ORCL",
    "COIN",
    "PLTR",
    "AVGO",
    "NFLX",
    "CRWD",
    "SMH",
)

# Gaps larger than this on an unadjusted series are treated as corporate
# actions (missed splits), not tradable gaps.
MAX_TRADABLE_GAP = 0.50


@dataclass(frozen=True)
class Rules:
    """Fill and filter parameters. Long only; there is no short path."""

    name: str
    gap_min: float = 0.02
    rvol_min: float = 1.5
    rvol_lookback: int = 20
    min_prior_sessions: int = 20
    slippage: float = 0.02
    stop_offset: float = 0.02
    risk_dollars: float = 2_000.0
    max_notional: float = 500_000.0
    target_r: float = 2.0
    min_stop_atr: float = 1.0
    atr_window: int = 14
    entry_cutoff: dt.time = dt.time(14, 30)
    flat_time: dt.time = dt.time(15, 45)
    # At the placement bar, skip the day if that bar opens above the range high.
    skip_if_open_above_high: bool = True
    # Exit the flat bar at its open. Do not use that bar's high/low.
    honest_flat: bool = True
    max_gap: float = MAX_TRADABLE_GAP
    bar_minutes: int = 5

    def with_filters(self, gap_min: float, rvol_min: float) -> Rules:
        return Rules(
            name=f"{self.name}_gap{gap_min}_rvol{rvol_min}",
            gap_min=gap_min,
            rvol_min=rvol_min,
            rvol_lookback=self.rvol_lookback,
            min_prior_sessions=self.min_prior_sessions,
            slippage=self.slippage,
            stop_offset=self.stop_offset,
            risk_dollars=self.risk_dollars,
            max_notional=self.max_notional,
            target_r=self.target_r,
            min_stop_atr=self.min_stop_atr,
            atr_window=self.atr_window,
            entry_cutoff=self.entry_cutoff,
            flat_time=self.flat_time,
            skip_if_open_above_high=self.skip_if_open_above_high,
            honest_flat=self.honest_flat,
            max_gap=self.max_gap,
            bar_minutes=self.bar_minutes,
        )


# Written rules: 20-session RVOL, do not chase a 09:45 open already through
# the opening-range high, and flatten at the 15:45 open.
SPEC_5M = Rules(name="spec_5m", bar_minutes=5)

# The attached prototype allowed a signal once 5 prior sessions existed, did
# not skip a 09:45 open already above the range high, and checked the 15:45
# bar's high/low before flattening at its open.
PROTOTYPE_COMPAT_5M = Rules(
    name="prototype_compat_5m",
    min_prior_sessions=5,
    skip_if_open_above_high=False,
    honest_flat=False,
    max_gap=math.inf,
    bar_minutes=5,
)

# Same filters as SPEC_5M, on 60-minute bars. The opening "range" is the
# first hour because that is the finest free window longer than 60 sessions.
SPEC_1H = Rules(name="coarse_1h", bar_minutes=60)

GAP_GRID: tuple[float, ...] = (0.015, 0.02, 0.03)
RVOL_GRID: tuple[float, ...] = (1.2, 1.5, 2.0)
