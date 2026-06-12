#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 스텁 — 한국투자증권(KIS) Open API WebSocket 실시간 체결가 (한국 종목).

기본 비활성. KIS_APP_KEY / KIS_APP_SECRET 환경변수가 없으면 자동 skip 한다.
v1(네이버 5초 폴링)과 동일한 STATE 갱신 함수(on_tick)를 호출하도록 인터페이스를 통일해,
키 발급 후 폴러를 끄고 이 피드로 교체하면 LIVE 정밀도가 올라간다.

구현은 키 발급 이후 진행 (현재는 인터페이스 + 게이팅만).
"""
import os

APP_KEY = os.environ.get("KIS_APP_KEY")
APP_SECRET = os.environ.get("KIS_APP_SECRET")


def available() -> bool:
    return bool(APP_KEY and APP_SECRET)


async def run(symbols, on_tick):
    """KIS WS 실시간 체결가 구독 → 종목별 on_tick(symbol, {price, dayPct, volume, marketOpen}).

    on_tick 은 app.py 의 STATE 갱신과 동일 시그니처를 받도록 설계 (v1 폴링과 통일).
    키 없으면 즉시 반환 (no-op).
    """
    if not available():
        print("[kis_ws] KIS_APP_KEY/SECRET 미설정 — skip")
        return
    # TODO(v2): KIS 토큰 발급 → wss://openapi.koreainvestment.com:9443 체결가(H0STCNT0) 구독
    #           수신 틱을 on_tick(symbol, {...}) 으로 STATE 에 반영.
    raise NotImplementedError("KIS WebSocket feed는 v2에서 구현 예정")
