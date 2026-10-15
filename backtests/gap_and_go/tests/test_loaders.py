"""Loader safety: market-data URLs only, and paid sources stay off without keys."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from backtests.gap_and_go.data import (
    MarketDataError,
    assert_market_data_url,
    build_alpaca_bars_url,
    build_polygon_aggs_url,
    optional_source_status,
    parse_alpaca_bars,
    parse_polygon_aggs,
)


def test_paid_sources_skip_without_keys() -> None:
    status = {item.name: item for item in optional_source_status(env={})}
    assert status["alpaca_iex_5m"].enabled is False
    assert status["polygon_5m"].enabled is False
    assert "skipped" in status["alpaca_iex_5m"].reason
    enabled = {
        item.name: item
        for item in optional_source_status(
            env={"APCA_API_KEY_ID": "x", "APCA_API_SECRET_KEY": "y", "POLYGON_API_KEY": "z"}
        )
    }
    assert enabled["alpaca_iex_5m"].enabled is True
    assert enabled["polygon_5m"].enabled is True


def test_urls_are_market_data_only() -> None:
    alpaca = build_alpaca_bars_url("AAPL", dt.date(2026, 1, 1), dt.date(2026, 8, 1))
    assert alpaca.startswith("https://data.alpaca.markets/v2/stocks/bars?")
    assert "orders" not in alpaca
    polygon = build_polygon_aggs_url("MSFT", dt.date(2026, 1, 1), dt.date(2026, 8, 1), "test-key")
    assert polygon.startswith("https://api.polygon.io/v2/aggs/ticker/MSFT/range/5/minute/")
    assert "/orders" not in polygon

    for url in (
        "http://data.alpaca.markets/v2/stocks/bars",
        "https://api.alpaca.markets/v2/orders",
        "https://paper-api.alpaca.markets/v2/orders",
        "https://api.polygon.io/v2/orders",
        "https://example.com/v2/aggs",
    ):
        try:
            assert_market_data_url(url)
        except MarketDataError:
            continue
        raise AssertionError(url)


def test_cache_roundtrip_survives_daylight_saving(tmp_path, monkeypatch) -> None:
    from backtests.gap_and_go import data

    monkeypatch.setattr(data, "CACHE_DIR", tmp_path)
    index = pd.to_datetime(
        [
            "2024-01-02 09:30:00",
            "2024-01-02 10:30:00",
            "2024-06-03 09:30:00",
            "2024-06-03 10:30:00",
        ]
    ).tz_localize("America/New_York")
    frame = pd.DataFrame(
        {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0},
        index=index,
    )
    path = tmp_path / "SPY_1h_730d.csv"
    data._write_cache(frame, path)
    loaded = data._read_cache(path)
    assert [stamp.date().isoformat() for stamp in loaded.index] == [
        "2024-01-02",
        "2024-01-02",
        "2024-06-03",
        "2024-06-03",
    ]
    assert str(loaded.index.tz) == "America/New_York"


def test_bar_parsers() -> None:
    frame, token = parse_alpaca_bars(
        {
            "bars": {
                "AAPL": [
                    {"t": "2026-08-03T13:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10},
                ]
            },
            "next_page_token": "next",
        },
        "AAPL",
    )
    assert token == "next"
    assert list(frame["Close"]) == [1.5]
    assert frame.index.tz is not None

    empty, next_token = parse_alpaca_bars({"bars": {}}, "AAPL")
    assert empty.empty
    assert next_token is None

    polygon, next_url = parse_polygon_aggs(
        {"results": [{"t": 1_780_000_000_000, "o": 3, "h": 4, "l": 2, "c": 3.5, "v": 8}]}
    )
    assert next_url is None
    assert list(polygon["Volume"]) == [8]
    assert isinstance(polygon.index, pd.DatetimeIndex)


def test_package_source_does_not_reference_broker_orders() -> None:
    root = Path(__file__).resolve().parents[1]
    text = "\n".join(path.read_text() for path in root.glob("*.py"))
    for banned in (
        "ib_insync",
        "ibapi",
        "placeOrder",
        "place_order",
        "api.alpaca.markets",
        "paper-api.alpaca.markets",
    ):
        assert banned not in text
