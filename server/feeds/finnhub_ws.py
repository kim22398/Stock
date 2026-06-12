#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 스텁 — Finnhub WebSocket 실시간 체결가 (미국 종목).

기본 비활성. FINNHUB_TOKEN 환경변수가 없으면 자동 skip 한다.
v1(네이버 5초 폴링)과 동일한 on_tick 인터페이스를 호출하도록 통일.

구현은 토큰 발급 이후 진행 (현재는 인터페이스 + 게이팅만).
"""
import os

TOKEN = os.environ.get("FINNHUB_TOKEN")


def available() -> bool:
    return bool(TOKEN)


async def run(symbols, on_tick):
    """Finnhub WS(trades) 구독 → 종목별 on_tick(symbol, {price, volume, ...}).

    키 없으면 즉시 반환 (no-op).
    """
    if not available():
        print("[finnhub_ws] FINNHUB_TOKEN 미설정 — skip")
        return
    # TODO(v2): wss://ws.finnhub.io?token=... 에 {"type":"subscribe","symbol":SYM} 전송,
    #           trade 메시지를 on_tick(symbol, {...}) 으로 STATE 에 반영.
    raise NotImplementedError("Finnhub WebSocket feed는 v2에서 구현 예정")
