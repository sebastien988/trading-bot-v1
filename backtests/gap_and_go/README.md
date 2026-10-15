# Gap-and-Go, long only (research replay)

Historical replay of a long-only opening-range continuation. The module writes hypothetical trades from downloaded bars. It has no broker client and no order path, and it does not call Interactive Brokers.

## Rules

A session can produce one long trade.

1. Gap: the 09:30 ET open is at least +2% above the prior regular-session close.
2. Relative volume: 09:30–09:45 ET volume is at least 1.5× the average of that same window over the prior 20 sessions. The current session is left out of its own average. Signals start once 20 prior windows exist.
3. At 09:45, a buy-stop sits at the 09:30–09:45 high plus $0.02. If the 09:45 bar opens already above that high, the day is skipped.
4. Fill: `max(bar open, stop level) + $0.02`. The level is cancelled when the bar can only trade after 14:30 ET. A 5-minute bar stamped 14:30 is still eligible.
5. Stop: the 09:30–09:45 low. If `entry - stop` is tighter than one 5-minute ATR(14), the stop widens to `entry - ATR`. ATR is the simple average of true range, read on the last bar of the opening range.
6. Target: `entry + 2R`, with `R = entry - stop`. Shares: `floor($2,000 / R)` and also `floor($500,000 / entry)`.
7. Inside a bar, a touch of the stop counts even if the target is also inside that bar. A stop that gaps through fills at `min(stop, bar open) - $0.02`. The target is a resting limit and fills at the limit.
8. Still-open trades leave at the 15:45 ET bar's open, minus $0.02. That bar's high and low are ignored.
9. There is no short side.

## Run

```bash
pip install -r requirements.txt
python -m pytest backtests/gap_and_go/tests
python -m backtests.gap_and_go
```

Optional 5-minute history, used only when the process environment already has credentials:

- Alpaca IEX: `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` (or `ALPACA_API_KEY` / `ALPACA_API_SECRET`)
- Polygon: `POLYGON_API_KEY`

With neither pair set, those loaders print a skip line and the run continues. This environment had neither, so the longer window is Yahoo 1-hour bars.

Cached bars stay in `backtests/gap_and_go/.cache/` and are gitignored. Result CSVs are in `results/`.

## Data

| Run | Source | Window | Sessions |
| --- | --- | --- | --- |
| 5-minute | yfinance `5m`, `period=60d`, `auto_adjust=False` | 2026-07-22 .. 2026-10-14 | 60 |
| Longer | yfinance `1h`, `period=730d`, `auto_adjust=False` | 2023-11-15 .. 2026-10-14 | 730 |

Yahoo is the longest intraday history reachable here without a new key. Five-minute, 15-minute, and 30-minute bars stop at about 60 sessions. The hourly run is a coarser proxy: the opening range is the 09:30–10:30 bar, the stop is placed at 10:30, ATR is the hourly ATR(14), the 14:30 hour is not an entry bar, and a position still open at 15:30 leaves at that bar's open because the hour contains the 15:45 flat. Known split ex-dates inside the hourly window were blocked: NVDA 2024-06-10, AVGO 2024-07-15, NFLX 2025-11-17, CRWD 2026-07-02. Gaps above +50% are also blocked as missed corporate actions; none fired.

Universe, in prototype order: SPY, QQQ, IWM, NVDA, TSLA, META, AAPL, MSFT, AMZN, GOOGL, ORCL, COIN, PLTR, AVGO, NFLX, CRWD, SMH.

## Findings

Dollar drawdown is the peak-to-trough of cumulative trade PnL in exit-time order. `avgR` is the mean R multiple. Profit factor uses dollar PnL. The sample half-split cuts the session calendar in half (5-minute midpoint 2026-09-02, hourly midpoint 2025-05-02).

### 60 sessions, 5-minute bars

Two runs are reported. `prototype_compat` follows the attached script: a signal is allowed after 5 prior sessions, a 09:45 open already above the range high is still filled, and the 15:45 bar's high and low are inspected before the flatten. `spec` follows the written rules above (full 20-session baseline, chase skipped, 15:45 extremes ignored).

| Run | Trades | Win rate | Avg R | Profit factor | Max DD | PnL |
| --- | --- | --- | --- | --- | --- | --- |
| Prototype script (sanity check) | 25 | 68.0% | +0.396 | 4.57 | −$2,005 | +$19,785 |
| Written rules | 11 | 72.7% | +0.317 | 3.14 | −$2,005 | +$6,952 |
| Prototype note (long side) | 25 | 68% | +0.40 | — | — | — |

The sanity check reproduces the prototype headline (25 longs, 68% wins, about +0.40R). All 25 prototype long trades are present, with the same entry clock, entry, stop, and share count. Twenty match the exit to the cent. Five differ only in the 15:45 flatten price, which moved by $0.01 to $0.27 versus the prototype file (NVDA 2026-08-05, PLTR 2026-08-04, CRWD 2026-08-27, TSLA 2026-09-03, NFLX 2026-09-14). Those revisions change total PnL from $19,777 to $19,785 and the profit factor from 4.56 to 4.57. None flips a win into a loss. See `results/prototype_overlap.csv`.

On this window the chase-skip and the stricter 15:45 flatten change nothing: no qualified day opened the 09:45 bar above the range high, and the 15:45 bar's extremes never changed an exit. The drop from 25 trades to 11 is the 20-session baseline. The prototype averaged as few as five prior windows, so it kept 14 early trades (including five names on 2026-07-30) that a full 20-session average cannot score. Yahoo's rolling window now starts on 2026-07-22 rather than the prototype's 2026-07-21, but every prototype long-trade date is still inside the file. Even with 2026-07-21 included, late July would not have 20 prior sessions.

Written-rule halves: 4 trades at +0.049R before 2026-09-02, and 7 trades at +0.471R after. The prototype-compatible halves are +0.368R (18 trades) and +0.471R (7 trades). Both halves of the compatible run are positive; the written-rule run is a handful of trades whose second half carries the average.

By symbol under the written rules, CRWD (+$3,811, 2 trades) and META (+$3,681, 2 trades) are the dollar total. COIN is negative (−$624, 3 trades). SMH is a single −1.0R stop (−$2,005). Full grid: `results/by_symbol.csv`.

### Longer test: 730 sessions, hourly proxy

| Trades | Win rate | Avg R | Profit factor | Max DD | PnL |
| --- | --- | --- | --- | --- | --- |
| 140 | 53.6% | +0.031 | 1.19 | −$9,026 (−4.52R) | +$8,660 |

The hourly proxy prints +0.031R across 140 trades, next to +0.396R on the 25-trade 5-minute sample. Halves are +0.059R (66 trades before 2025-05-02) and +0.007R (74 trades from 2025-05-02). COIN is 26 of the 140 trades, +0.210R, and +$10,858. The other 114 trades are −0.010R and −$2,198. The hourly dollar profit is that one symbol.

### Sensitivity

Same written rules, gap threshold crossed with the relative-volume floor.

5-minute, 60 sessions:

| Gap | RVOL | Trades | Win rate | Avg R | PF | Max DD |
| --- | --- | --- | --- | --- | --- | --- |
| 1.5% | 1.2× | 24 | 62.5% | +0.186 | 1.93 | −$5,556 |
| 1.5% | 1.5× | 15 | 60.0% | +0.132 | 1.59 | −$4,018 |
| 1.5% | 2.0× | 8 | 75.0% | +0.501 | 7.44 | −$1,240 |
| 2% | 1.2× | 16 | 68.8% | +0.382 | 3.95 | −$2,005 |
| 2% | 1.5× | 11 | 72.7% | +0.317 | 3.14 | −$2,005 |
| 2% | 2.0× | 8 | 75.0% | +0.501 | 7.44 | −$1,240 |
| 3% | 1.2× | 8 | 75.0% | +0.325 | 5.19 | −$1,240 |
| 3% | 1.5× | 7 | 71.4% | +0.310 | 4.49 | −$1,240 |
| 3% | 2.0× | 6 | 66.7% | +0.310 | 3.99 | −$1,240 |

Every 5-minute cell is positive. Every cell has 24 trades or fewer, so the sign is a small-sample result. The 1.5%/2× cell and the 2%/2× cell are the same eight trades.

Hourly proxy, 730 sessions:

| Gap | RVOL | Trades | Win rate | Avg R | PF | Max DD |
| --- | --- | --- | --- | --- | --- | --- |
| 1.5% | 1.2× | 262 | 49.6% | −0.006 | 0.97 | −$35,286 |
| 1.5% | 1.5× | 168 | 53.6% | +0.009 | 1.05 | −$12,483 |
| 1.5% | 2.0× | 95 | 57.9% | +0.068 | 1.47 | −$8,049 |
| 2% | 1.2× | 193 | 49.2% | −0.006 | 0.97 | −$29,796 |
| 2% | 1.5× | 140 | 53.6% | +0.031 | 1.19 | −$9,026 |
| 2% | 2.0× | 85 | 60.0% | +0.097 | 1.74 | −$4,775 |
| 3% | 1.2× | 114 | 47.4% | −0.097 | 0.60 | −$26,528 |
| 3% | 1.5× | 88 | 55.7% | −0.000 | 1.00 | −$9,816 |
| 3% | 2.0× | 58 | 56.9% | +0.043 | 1.31 | −$4,210 |

On the long window, a 1.2× relative-volume floor is negative at every gap, and a 3% gap is flat to negative unless relative volume is 2×. The cells that stay positive are small in R.

## Caveats

- Intrabar path is unknown. A bar that contains both the stop and the target is booked as a stop. On the entry bar that can book a stop that printed before the breakout.
- The target fill ignores price improvement when a bar opens through the limit, and it pays no extra slippage. Stops, gap-through entries, and the 15:45 exit pay $0.02 a share. There are no commissions or regulatory fees.
- The $2,000 risk budget and the $500,000 notional cap are per trade. Several names can trigger on the same morning (five names on 2026-07-30, about $550k of notional combined). The replay does not constrain account buying power.
- Drawdown is the sum of those trade results. It is not a percent of a funded account.
- Prices are unadjusted, so a $0.02 slippage stays a cent. Dividend gaps remain in the open-versus-prior-close filter. Split ex-dates listed above are removed; an unknown corporate action above +50% would be removed too.
- The 17 symbols are a current liquid list. Membership is not point-in-time, and names that fell out of that list are absent.
- Yahoo's 5-minute history is about 60 sessions and the prints can be revised. The five exit mismatches above are that kind of revision. The hourly proxy cannot see a 15-minute range, so its +0.03R is evidence about a coarser cousin of the rule, not a confirmation of the 5-minute backtest.
- ATR uses the bars already closed at the decision, and relative volume uses the opening window already closed at 09:45. The replay does not read a later bar to decide the entry. The hourly flat uses only the 15:30 open, because the rest of that hour is after the decision point or is indistinguishable from it.
