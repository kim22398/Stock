#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify.new_triggers() 단위 테스트 (네트워크/깃 없음 — 인메모리 dict 만).

new_triggers 는 순수 함수: 이전(old)·현재(new) 스냅샷 dict 를 받아
'새로 켜진' 트리거만 반환한다. 각 가드의 경계를 직접 검증한다.
  · 당일 ±3% '신규 진입' 가드 (직전엔 ±3% 아니어야 발화)
  · 거래량 2x — 직전에 이미 2x 가 아니어야 발화 (volume/avgVol20)
  · RSI 70/30 크로스 — 양쪽 스냅샷 모두 non-null 필요
  · 52주 신고가 — hi52 > 직전 hi52
fetch_fundamentals 의 순수 헬퍼(dart_code/_latest/_latest_two)도 함께 검증.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import notify  # noqa: E402


def _snap(**kw):
    """행 하나를 만들기 위한 헬퍼 — 지정한 필드만 채운다."""
    return kw


def _tags(old_row, new_row, sym="AAA"):
    """단일 종목에 대해 new_triggers 가 낸 태그 목록(없으면 [])."""
    res = notify.new_triggers({sym: old_row}, {sym: new_row})
    return res[0][2] if res else []


# ── 당일 ±3% '신규 진입' 가드 ─────────────────────────────────────────
def test_daypct_new_entry_fires():
    tags = _tags(_snap(dayPct=1.0), _snap(dayPct=4.2))
    assert any("4.2%" in t for t in tags)
    assert any(t.startswith("+") for t in tags)


def test_daypct_negative_entry_fires_with_sign():
    tags = _tags(_snap(dayPct=-1.0), _snap(dayPct=-3.5))
    assert any(t == "-3.5%" for t in tags)


def test_daypct_already_over_threshold_no_refire():
    # 직전에도 이미 ±3% 였으면 '신규'가 아니므로 발화 금지
    assert _tags(_snap(dayPct=3.4), _snap(dayPct=4.0)) == []


def test_daypct_below_threshold_no_fire():
    assert _tags(_snap(dayPct=0.5), _snap(dayPct=2.9)) == []


def test_daypct_exactly_three_is_inclusive():
    # abs(dp_n) >= 3 — 경계 포함
    tags = _tags(_snap(dayPct=1.0), _snap(dayPct=3.0))
    assert any("3.0%" in t for t in tags)


def test_daypct_new_none_no_fire():
    assert _tags(_snap(dayPct=None), _snap(dayPct=None)) == []


# ── 거래량 2x (volume / avgVol20) — 이미 2x 가 아니어야 발화 ───────────
def test_volume_spike_new_fires():
    old = _snap(volume=1000, avgVol20=1000)        # 1.0x
    new = _snap(volume=2500, avgVol20=1000)        # 2.5x
    assert any("거래량" in t and "2.5x" in t for t in _tags(old, new))


def test_volume_already_2x_no_refire():
    old = _snap(volume=2200, avgVol20=1000)        # 2.2x (이미 2x 이상)
    new = _snap(volume=3000, avgVol20=1000)        # 3.0x
    assert _tags(old, new) == []


def test_volume_exactly_2x_inclusive():
    old = _snap(volume=1000, avgVol20=1000)        # 1.0x
    new = _snap(volume=2000, avgVol20=1000)        # 정확히 2.0x → 발화
    assert any("거래량" in t for t in _tags(old, new))


def test_volume_missing_fields_no_fire():
    # avgVol20 누락 → _volx None → 발화 없음
    old = _snap(volume=1000, avgVol20=None)
    new = _snap(volume=5000, avgVol20=None)
    assert _tags(old, new) == []


# ── RSI 70/30 크로스 — 양쪽 모두 non-null 필요 ────────────────────────
def test_rsi_cross_overbought_fires():
    tags = _tags(_snap(rsi=68), _snap(rsi=72))
    assert any("과열" in t for t in tags)


def test_rsi_cross_oversold_fires():
    tags = _tags(_snap(rsi=33), _snap(rsi=28))
    assert any("과매도" in t for t in tags)


def test_rsi_overbought_requires_old_below_70():
    # 직전에도 이미 70 이상이면 '크로스'가 아님 → 발화 금지
    assert _tags(_snap(rsi=71), _snap(rsi=75)) == []


def test_rsi_oversold_requires_old_above_30():
    assert _tags(_snap(rsi=29), _snap(rsi=25)) == []


def test_rsi_old_none_no_fire():
    # 직전 RSI 가 None 이면 양쪽 non-null 조건 불충족 → 발화 없음
    assert _tags(_snap(rsi=None), _snap(rsi=75)) == []


def test_rsi_new_none_no_fire():
    assert _tags(_snap(rsi=68), _snap(rsi=None)) == []


# ── 52주 신고가 — hi52 > 직전 hi52, 양쪽 non-null ─────────────────────
def test_hi52_new_high_fires():
    assert "52주 신고가" in _tags(_snap(hi52=100.0), _snap(hi52=105.0))


def test_hi52_equal_no_fire():
    # 같으면 '신'고가가 아님 (엄격한 > )
    assert _tags(_snap(hi52=100.0), _snap(hi52=100.0)) == []


def test_hi52_lower_no_fire():
    assert _tags(_snap(hi52=100.0), _snap(hi52=95.0)) == []


def test_hi52_old_none_no_fire():
    assert _tags(_snap(hi52=None), _snap(hi52=105.0)) == []


# ── 신규 종목 / 정렬 / 다중 태그 ──────────────────────────────────────
def test_new_symbol_skipped():
    # old 에 없는 종목은 비교 불가 → 건너뜀
    res = notify.new_triggers({}, {"NEW": _snap(dayPct=9.0, rsi=80, hi52=200.0)})
    assert res == []


def test_unchanged_snapshot_yields_nothing():
    row = _snap(dayPct=1.0, volume=1000, avgVol20=1000, rsi=50, hi52=100.0)
    assert notify.new_triggers({"AAA": row}, {"AAA": dict(row)}) == []


def test_multiple_tags_on_one_symbol():
    old = _snap(dayPct=0.0, volume=1000, avgVol20=1000, rsi=60, hi52=100.0)
    new = _snap(dayPct=5.0, volume=3000, avgVol20=1000, rsi=75, hi52=110.0)
    tags = _tags(old, new)
    assert any("5.0%" in t for t in tags)
    assert any("거래량" in t for t in tags)
    assert any("과열" in t for t in tags)
    assert "52주 신고가" in tags


def test_results_sorted_by_abs_daypct_desc():
    old = {"A": _snap(dayPct=0.0), "B": _snap(dayPct=0.0)}
    new = {"A": _snap(dayPct=3.5), "B": _snap(dayPct=-8.0)}
    res = notify.new_triggers(old, new)
    syms = [r[0] for r in res]
    assert syms == ["B", "A"]  # |−8.0| > |3.5|


def test_return_shape():
    old = {"AAA": _snap(dayPct=0.0)}
    new = {"AAA": _snap(dayPct=4.0, name="알파")}
    res = notify.new_triggers(old, new)
    assert len(res) == 1
    sym, name, tags, dp = res[0]
    assert sym == "AAA"
    assert name == "알파"
    assert isinstance(tags, list) and tags
    assert dp == 4.0


# ── fetch_fundamentals 순수 헬퍼 ──────────────────────────────────────
import fetch_fundamentals as ff  # noqa: E402


def test_dart_code_korean_strips_suffix():
    assert ff.dart_code("267260.KS") == "267260"
    assert ff.dart_code("033100.KQ") == "033100"


def test_dart_code_us_unchanged():
    assert ff.dart_code("AAPL") == "AAPL"
    assert ff.dart_code("GEV") == "GEV"


def test_is_kr():
    assert ff.is_kr("267260.KS") is True
    assert ff.is_kr("033100.KQ") is True
    assert ff.is_kr("AAPL") is False


def test_latest_returns_first_non_null():
    hist = [{"x": None}, {"x": 5}, {"x": 9}]
    assert ff._latest(hist, "x") == 5


def test_latest_all_null_or_empty():
    assert ff._latest([{"x": None}], "x") is None
    assert ff._latest([], "x") is None
    assert ff._latest(None, "x") is None


def test_latest_two_pair():
    hist = [{"v": 10}, {"v": None}, {"v": 7}, {"v": 3}]
    assert ff._latest_two(hist, "v") == (10, 7)


def test_latest_two_single_value_second_none():
    assert ff._latest_two([{"v": 4}], "v") == (4, None)


def test_latest_two_empty_is_none_pair():
    assert ff._latest_two([], "v") == (None, None)
    assert ff._latest_two(None, "v") == (None, None)
