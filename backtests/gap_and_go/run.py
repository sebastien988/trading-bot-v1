"""Run the Gap-and-Go research backtest and write result CSVs.

This process downloads historical bars and writes hypothetical trades.
It does not place, route, or simulate live or paper broker orders.
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd

from backtests.gap_and_go.config import (
    GAP_GRID,
    PROTOTYPE_COMPAT_5M,
    RVOL_GRID,
    SPEC_1H,
    SPEC_5M,
    SYMBOLS,
    Rules,
)
from backtests.gap_and_go.data import (
    load_alpaca_5m,
    load_polygon_5m,
    load_splits,
    load_yfinance,
    optional_source_status,
)
from backtests.gap_and_go.report import (
    compare_to_reference,
    half_rows,
    summary_row,
    symbol_rows,
    trades_frame,
    write_frame,
)
from backtests.gap_and_go.strategy import Session, Trade, prepare_symbol, run_sessions

PACKAGE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PACKAGE_DIR / "results"
REFERENCE_PATH = RESULTS_DIR / "prototype_long_reference.csv"


def _prepare(bars: dict[str, pd.DataFrame], rules: Rules, refresh: bool) -> dict[str, list[Session]]:
    prepared: dict[str, list[Session]] = {}
    for symbol, frame in bars.items():
        try:
            splits = load_splits(symbol, refresh=refresh)
        except Exception:
            splits = set()
        # Only splits inside the loaded window can affect a signal.
        window = set(frame.index.date)
        prepared[symbol] = prepare_symbol(symbol, frame, rules, split_dates=splits & window)
    return prepared


def _run(prepared: dict[str, list[Session]], rules: Rules) -> tuple[list[Trade], dict[str, int]]:
    trades: list[Trade] = []
    counts: dict[str, int] = {}
    for sessions in prepared.values():
        got, reasons = run_sessions(sessions, rules)
        trades.extend(got)
        for key, value in reasons.items():
            counts[key] = counts.get(key, 0) + value
    return trades, counts


def _dates(prepared: dict[str, list[Session]]) -> list[dt.date]:
    found = {session.session for sessions in prepared.values() for session in sessions}
    return sorted(found)


def _span(prepared: dict[str, list[Session]]) -> tuple[str, str, int]:
    dates = _dates(prepared)
    if not dates:
        return "", "", 0
    return dates[0].isoformat(), dates[-1].isoformat(), len(dates)


def _print_headline(label: str, trades: list[Trade], counts: dict[str, int], span: tuple[str, str, int]) -> None:
    row = summary_row(label, trades)
    print(
        f"{label}: {span[0]}..{span[1]} ({span[2]} sessions) "
        f"trades={row['trades']} win={row['win_rate_pct']}% avgR={row['avg_r']} "
        f"PF={row['profit_factor']} maxDD$={row['max_dd_dollars']} maxDD_R={row['max_dd_r']} "
        f"pnl={row['pnl']}"
    )
    print(f"  rejects: {counts}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Research-only long Gap-and-Go backtest")
    parser.add_argument("--refresh", action="store_true", help="redownload cached bars")
    parser.add_argument("--results", type=Path, default=RESULTS_DIR)
    args = parser.parse_args(argv)
    out: Path = args.results
    out.mkdir(parents=True, exist_ok=True)

    print("RESEARCH ONLY — historical replay. No broker orders are placed or routed.")
    for status in optional_source_status():
        print(f"  {status.name}: {status.reason}")

    print("Loading yfinance 5-minute bars (about 60 sessions)...")
    bars_5m = load_yfinance(list(SYMBOLS), interval="5m", period="60d", refresh=args.refresh)
    print("Loading yfinance 1-hour bars (about 730 sessions)...")
    bars_1h = load_yfinance(list(SYMBOLS), interval="1h", period="730d", refresh=args.refresh)

    prepared_5m = _prepare(bars_5m, SPEC_5M, args.refresh)
    prepared_1h = _prepare(bars_1h, SPEC_1H, args.refresh)
    span_5m = _span(prepared_5m)
    span_1h = _span(prepared_1h)

    spec_trades, spec_counts = _run(prepared_5m, SPEC_5M)
    compat_trades, compat_counts = _run(prepared_5m, PROTOTYPE_COMPAT_5M)
    hourly_trades, hourly_counts = _run(prepared_1h, SPEC_1H)

    longer_label = "coarse_1h_730d"
    longer_trades = hourly_trades
    longer_counts = hourly_counts
    longer_span = span_1h
    longer_note = "yfinance 1-hour bars; first-hour range is a coarse proxy for the 15-minute range"

    # Optional finer history. A disabled source is a skip, not a failure.
    today = dt.date.today()
    start = today - dt.timedelta(days=730)
    for status in optional_source_status():
        if not status.enabled:
            continue
        try:
            if status.name == "alpaca_iex_5m":
                alpaca_bars = load_alpaca_5m(list(SYMBOLS), start, today)
                alpaca_prepared = _prepare(alpaca_bars, SPEC_5M, refresh=True)
                alpaca_trades, alpaca_counts = _run(alpaca_prepared, SPEC_5M)
                alpaca_span = _span(alpaca_prepared)
                if alpaca_span[2] > span_5m[2]:
                    longer_label = "alpaca_iex_5m"
                    longer_trades = alpaca_trades
                    longer_counts = alpaca_counts
                    longer_span = alpaca_span
                    longer_note = "Alpaca IEX 5-minute bars, same 15-minute rules"
                    write_frame(trades_frame(alpaca_trades), out / "trades_alpaca_5m.csv")
            elif status.name == "polygon_5m":
                polygon_bars = load_polygon_5m(list(SYMBOLS), start, today)
                polygon_prepared = _prepare(polygon_bars, SPEC_5M, refresh=True)
                polygon_trades, polygon_counts = _run(polygon_prepared, SPEC_5M)
                polygon_span = _span(polygon_prepared)
                if polygon_span[2] > longer_span[2] and status.name == "polygon_5m":
                    longer_label = "polygon_5m"
                    longer_trades = polygon_trades
                    longer_counts = polygon_counts
                    longer_span = polygon_span
                    longer_note = "Polygon 5-minute bars, same 15-minute rules"
                    write_frame(trades_frame(polygon_trades), out / "trades_polygon_5m.csv")
        except Exception as exc:
            print(f"  {status.name}: failed ({exc.__class__.__name__}); continuing without it")

    _print_headline("spec_5m_60d", spec_trades, spec_counts, span_5m)
    _print_headline("prototype_compat_5m", compat_trades, compat_counts, span_5m)
    _print_headline(longer_label, longer_trades, longer_counts, longer_span)

    write_frame(trades_frame(spec_trades), out / "trades_5m_60d.csv")
    write_frame(trades_frame(compat_trades), out / "trades_5m_60d_prototype_compat.csv")
    write_frame(trades_frame(hourly_trades), out / "trades_1h_730d.csv")

    summary_rows = [
        summary_row(
            "spec_5m_60d",
            spec_trades,
            {"start": span_5m[0], "end": span_5m[1], "sessions": span_5m[2], "note": "written rules on 5-minute bars"},
        ),
        summary_row(
            "prototype_compat_5m",
            compat_trades,
            {
                "start": span_5m[0],
                "end": span_5m[1],
                "sessions": span_5m[2],
                "note": "prototype fill rules (no chase-skip, 5-session warmup, 15:45 bar extremes)",
            },
        ),
        summary_row(
            longer_label,
            longer_trades,
            {"start": longer_span[0], "end": longer_span[1], "sessions": longer_span[2], "note": longer_note},
        ),
    ]
    # Always keep the hourly proxy in the summary even if a 5-minute source replaced it.
    if longer_label != "coarse_1h_730d":
        summary_rows.append(
            summary_row(
                "coarse_1h_730d",
                hourly_trades,
                {"start": span_1h[0], "end": span_1h[1], "sessions": span_1h[2], "note": "first-hour proxy"},
            )
        )
    write_frame(pd.DataFrame(summary_rows), out / "summary.csv")

    halves = []
    halves.extend(half_rows("spec_5m_60d", spec_trades, _dates(prepared_5m)))
    halves.extend(half_rows("prototype_compat_5m", compat_trades, _dates(prepared_5m)))
    halves.extend(half_rows("coarse_1h_730d", hourly_trades, _dates(prepared_1h)))
    write_frame(pd.DataFrame(halves), out / "by_half.csv")

    symbols = []
    symbols.extend(symbol_rows("spec_5m_60d", spec_trades))
    symbols.extend(symbol_rows("prototype_compat_5m", compat_trades))
    symbols.extend(symbol_rows("coarse_1h_730d", hourly_trades))
    write_frame(pd.DataFrame(symbols), out / "by_symbol.csv")

    sensitivity = []
    for gap in GAP_GRID:
        for rvol in RVOL_GRID:
            for label, prepared, base in (
                ("spec_5m_60d", prepared_5m, SPEC_5M),
                ("coarse_1h_730d", prepared_1h, SPEC_1H),
            ):
                rules = base.with_filters(gap, rvol)
                trades, _counts = _run(prepared, rules)
                sensitivity.append(
                    summary_row(
                        label,
                        trades,
                        {"gap_min": gap, "rvol_min": rvol},
                    )
                )
    write_frame(pd.DataFrame(sensitivity), out / "sensitivity.csv")

    if REFERENCE_PATH.exists():
        reference = pd.read_csv(REFERENCE_PATH, dtype={"date": str, "time": str})
        comparison = compare_to_reference(compat_trades, reference)
        write_frame(comparison, out / "prototype_overlap.csv")
        counts = comparison["status"].value_counts().to_dict() if not comparison.empty else {}
        print(f"prototype overlap (compat rules): {counts}")
    else:
        print(f"No prototype reference at {REFERENCE_PATH}")


if __name__ == "__main__":
    main()
