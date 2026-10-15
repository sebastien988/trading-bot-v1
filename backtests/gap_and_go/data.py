"""Pluggable historical-bar loaders.

Market data only. URL builders refuse trading hosts and order paths.
Alpaca and Polygon run only when their key environment variables are set;
otherwise the caller is told to skip them.
"""

from __future__ import annotations

import datetime as dt
import os
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

PACKAGE_DIR = Path(__file__).resolve().parent
CACHE_DIR = PACKAGE_DIR / ".cache"

_ALLOWED_HOSTS = frozenset(
    {
        "data.alpaca.markets",
        "api.polygon.io",
    }
)
_FORBIDDEN_PATH_TOKENS = ("/orders", "/order", "/account", "/positions", "/portfolio")

ALPACA_KEY_NAMES = ("APCA_API_KEY_ID", "ALPACA_API_KEY")
ALPACA_SECRET_NAMES = ("APCA_API_SECRET_KEY", "ALPACA_API_SECRET", "ALPACA_SECRET_KEY")
POLYGON_KEY_NAMES = ("POLYGON_API_KEY", "POLYGON_KEY")


class MarketDataError(RuntimeError):
    """A loader could not return bars. Never used for order routing."""


def assert_market_data_url(url: str) -> str:
    """Reject anything that is not a known market-data URL."""

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise MarketDataError(f"refusing non-https URL: {url}")
    if parsed.hostname not in _ALLOWED_HOSTS:
        raise MarketDataError(f"refusing non-market-data host: {parsed.hostname}")
    path = parsed.path.lower()
    if any(token in path for token in _FORBIDDEN_PATH_TOKENS):
        raise MarketDataError(f"refusing broker path: {parsed.path}")
    return url


def _first_env(names: tuple[str, ...], env: dict[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    for name in names:
        value = source.get(name)
        if value:
            return value
    return None


@dataclass(frozen=True)
class SourceStatus:
    name: str
    enabled: bool
    reason: str


def optional_source_status(env: dict[str, str] | None = None) -> list[SourceStatus]:
    alpaca_key = _first_env(ALPACA_KEY_NAMES, env)
    alpaca_secret = _first_env(ALPACA_SECRET_NAMES, env)
    polygon_key = _first_env(POLYGON_KEY_NAMES, env)
    statuses = []
    if alpaca_key and alpaca_secret:
        statuses.append(SourceStatus("alpaca_iex_5m", True, "credentials present"))
    else:
        statuses.append(
            SourceStatus(
                "alpaca_iex_5m",
                False,
                "skipped: set APCA_API_KEY_ID and APCA_API_SECRET_KEY to enable IEX 5-minute history",
            )
        )
    if polygon_key:
        statuses.append(SourceStatus("polygon_5m", True, "credentials present"))
    else:
        statuses.append(
            SourceStatus(
                "polygon_5m",
                False,
                "skipped: set POLYGON_API_KEY to enable Polygon 5-minute history",
            )
        )
    return statuses


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame = frame.copy()
        frame.columns = [str(column[0]) for column in frame.columns]
    lookup = {str(column).lower(): column for column in frame.columns}
    for name in ("open", "high", "low", "close", "volume"):
        if name not in lookup:
            raise MarketDataError(f"bars are missing {name}")
    out = pd.DataFrame(
        {
            "Open": frame[lookup["open"]],
            "High": frame[lookup["high"]],
            "Low": frame[lookup["low"]],
            "Close": frame[lookup["close"]],
            "Volume": frame[lookup["volume"]],
        },
        index=frame.index,
    )
    out = out.apply(pd.to_numeric, errors="coerce").dropna()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True).tz_convert("America/New_York")
    elif out.index.tz is None:
        out.index = out.index.tz_localize("America/New_York")
    else:
        out.index = out.index.tz_convert("America/New_York")
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.between_time("09:30", "15:55")


def _cache_file(symbol: str, interval: str, period: str) -> Path:
    safe = f"{symbol}_{interval}_{period}.csv"
    return CACHE_DIR / safe


def _read_cache(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    # Offsets change across DST, so the column is parsed in UTC and then shown in New York.
    frame.index = pd.to_datetime(frame.index, utc=True).tz_convert("America/New_York")
    return normalize_ohlcv(frame)


def _write_cache(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path)


def _flatten_download(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        levels = list(frame.columns.get_level_values(0))
        if symbol in levels:
            frame = frame[symbol].copy()
        else:
            frame = frame.copy()
            frame.columns = [str(column[0]) for column in frame.columns]
    return normalize_ohlcv(frame)


def load_yfinance(
    symbols: list[str],
    *,
    interval: str,
    period: str,
    refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """Download regular-hours bars. ``auto_adjust`` is off so $0.02 is a real cent."""

    import yfinance as yf

    loaded: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        print(f"  {interval} {symbol}", flush=True)
        path = _cache_file(symbol, interval, period)
        if path.exists() and not refresh:
            loaded[symbol] = _read_cache(path)
            continue
        frame = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                downloaded = yf.download(
                    symbol,
                    period=period,
                    interval=interval,
                    progress=False,
                    auto_adjust=False,
                    prepost=False,
                    threads=False,
                )
                if downloaded is not None and len(downloaded) > 0:
                    frame = _flatten_download(downloaded, symbol)
                    break
            except Exception as exc:  # yfinance raises a mix of request and parse errors
                last_error = exc
            time.sleep(1.0 * (attempt + 1))
        if frame is None or frame.empty:
            detail = f"{last_error}" if last_error else "empty response"
            raise MarketDataError(f"yfinance {interval} {period} failed for {symbol}: {detail}")
        _write_cache(frame, path)
        loaded[symbol] = frame
    return loaded


def load_splits(symbol: str, refresh: bool = False) -> set[dt.date]:
    """Ex-dates from Yahoo. Failures yield an empty set and are reported by the caller."""

    import yfinance as yf

    path = CACHE_DIR / f"{symbol}_splits.csv"
    if path.exists() and not refresh:
        frame = pd.read_csv(path, parse_dates=["date"])
        return set(pd.to_datetime(frame["date"]).dt.date)
    try:
        series = yf.Ticker(symbol).splits
    except Exception:
        return set()
    if series is None or len(series) == 0:
        dates: set[dt.date] = set()
    else:
        index = pd.to_datetime(series.index)
        if getattr(index, "tz", None) is not None:
            index = index.tz_convert("America/New_York")
        dates = set(index.date)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"date": sorted(dates)}).to_csv(path, index=False)
    return dates


def build_alpaca_bars_url(
    symbol: str,
    start: dt.date,
    end: dt.date,
    page_token: str | None = None,
) -> str:
    query = {
        "symbols": symbol,
        "timeframe": "5Min",
        "start": f"{start.isoformat()}T00:00:00Z",
        "end": f"{end.isoformat()}T00:00:00Z",
        "limit": "10000",
        "adjustment": "raw",
        "feed": "iex",
    }
    if page_token:
        query["page_token"] = page_token
    url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(query)
    return assert_market_data_url(url)


def parse_alpaca_bars(payload: dict, symbol: str) -> tuple[pd.DataFrame, str | None]:
    rows = (payload.get("bars") or {}).get(symbol) or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        return empty, payload.get("next_page_token")
    frame = frame.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    frame.index = pd.to_datetime(frame["t"], utc=True)
    return frame[["Open", "High", "Low", "Close", "Volume"]], payload.get("next_page_token")


def build_polygon_aggs_url(symbol: str, start: dt.date, end: dt.date, api_key: str) -> str:
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{urllib.parse.quote(symbol)}/range/5/minute/"
        f"{start.isoformat()}/{end.isoformat()}?adjusted=false&sort=asc&limit=50000&"
        + urllib.parse.urlencode({"apiKey": api_key})
    )
    return assert_market_data_url(url)


def parse_polygon_aggs(payload: dict) -> tuple[pd.DataFrame, str | None]:
    rows = payload.get("results") or []
    frame = pd.DataFrame(rows)
    if frame.empty:
        empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        return empty, payload.get("next_url")
    frame = frame.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
    frame.index = pd.to_datetime(frame["t"], unit="ms", utc=True)
    return frame[["Open", "High", "Low", "Close", "Volume"]], payload.get("next_url")


def _http_json(url: str, headers: dict[str, str] | None = None) -> dict:
    assert_market_data_url(url)
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        # Do not chain the requests error: its message can contain the query string.
        raise MarketDataError("market-data request failed")
    return response.json()


def load_alpaca_5m(
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    env: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    key = _first_env(ALPACA_KEY_NAMES, env)
    secret = _first_env(ALPACA_SECRET_NAMES, env)
    if not key or not secret:
        raise MarketDataError("Alpaca credentials are not set")
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    loaded: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frames = []
        token: str | None = None
        for _ in range(50):
            url = build_alpaca_bars_url(symbol, start, end, token)
            payload = _http_json(url, headers)
            frame, token = parse_alpaca_bars(payload, symbol)
            if not frame.empty:
                frames.append(frame)
            if not token:
                break
        if not frames:
            raise MarketDataError(f"Alpaca returned no bars for {symbol}")
        loaded[symbol] = normalize_ohlcv(pd.concat(frames))
    return loaded


def load_polygon_5m(
    symbols: list[str],
    start: dt.date,
    end: dt.date,
    env: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    key = _first_env(POLYGON_KEY_NAMES, env)
    if not key:
        raise MarketDataError("Polygon credentials are not set")
    loaded: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frames = []
        url: str | None = build_polygon_aggs_url(symbol, start, end, key)
        for _ in range(50):
            if url is None:
                break
            payload = _http_json(url)
            frame, next_url = parse_polygon_aggs(payload)
            if not frame.empty:
                frames.append(frame)
            if not next_url:
                break
            # next_url already contains the key; still must be a data URL.
            url = assert_market_data_url(next_url)
        if not frames:
            raise MarketDataError(f"Polygon returned no bars for {symbol}")
        loaded[symbol] = normalize_ohlcv(pd.concat(frames))
    return loaded
