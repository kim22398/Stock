#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""지표/스키마 단위 테스트 (네트워크 없이). pytest는 CI 전용 dev 의존성."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard  # noqa: E402


# ── SMA ──────────────────────────────────────────────────────────────
def test_sma_basic():
    assert dashboard.sma([1, 2, 3, 4], 2) == 3.5
    assert dashboard.sma([2, 4, 6], 3) == 4.0


def test_sma_insufficient():
    assert dashboard.sma([1, 2], 5) is None


# ── RSI(14) ──────────────────────────────────────────────────────────
def test_rsi_monotonic_up_high():
    up = [float(x) for x in range(100, 200)]
    assert dashboard.rsi14(up) > 90


def test_rsi_monotonic_down_low():
    down = [float(x) for x in range(200, 100, -1)]
    assert dashboard.rsi14(down) < 10


def test_rsi_bounds_and_short():
    assert dashboard.rsi14([1, 2, 3]) is None  # period+1 미만
    mixed = [100 + (i % 5) for i in range(40)]
    r = dashboard.rsi14([float(x) for x in mixed])
    assert r is not None and 0 <= r <= 100


# ── snapshot() 스키마 ────────────────────────────────────────────────
def test_snapshot_schema_keys():
    snap = dashboard.snapshot()
    assert {"updated", "rows", "bench"}.issubset(snap.keys())
    assert len(snap["rows"]) == len(dashboard.UNIVERSE)
    for r in snap["rows"]:
        for k in ("symbol", "name", "group", "market", "spark"):
            assert k in r, f"row missing {k}"
    for b in snap["bench"]:
        assert "symbol" in b and "spark" in b


# ── history_series() 배열 길이 정합 (합성 시계열 주입, 네트워크 없음) ──
def test_history_series_lengths():
    sym = "GEV"
    n = 60
    dates = [f"202601{(i % 28) + 1:02d}" for i in range(n)]
    closes = [100.0 + i for i in range(n)]
    with dashboard.STATE_LOCK:
        dashboard.HIST_SERIES[sym] = {
            "dates": dates, "open": closes, "high": closes,
            "low": closes, "close": closes, "volume": [1000] * n,
        }
    hs = dashboard.history_series(sym)
    length = len(hs["dates"])
    for k in ("open", "high", "low", "close", "volume", "rsi", "sma50", "sma200"):
        assert len(hs[k]) == length, f"{k} length {len(hs[k])} != {length}"
    # 워밍업 구간은 None (sma200은 200일 미만이면 전부 None)
    assert hs["sma200"][0] is None
    assert hs["close"][-1] == round(closes[-1], 4)
