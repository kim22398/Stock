#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LIVE 모드 백엔드 — 항상 켜진 서버가 시세를 폴링하고 SSE로 브라우저에 push.

v1 데이터 소스: 레포 루트 dashboard.py 의 refresh_quotes()/refresh_history() 를 그대로 재사용한다
(검증된 네이버 수집 로직). 시세 폴링 주기 5초, 장 마감 시 60초로 완화 (데이터 소스 예의 + 리소스 절약).

프레임워크 선택 — FastAPI + uvicorn + sse-starlette:
  · sse-starlette 가 SSE keep-alive(ping)·동시접속을 깔끔하게 처리
  · CORSMiddleware 한 줄로 github.io 허용
  · async 라 다수 클라이언트를 스레드-퍼-커넥션 없이 수용
  (stdlib ThreadingHTTPServer 로도 가능하나 SSE keep-alive/다중접속 코드가 늘어 FastAPI 택1.)

실행:  uvicorn app:app --port 8400   (server/ 에서)
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager

# 레포 루트(dashboard.py)를 import 경로에 추가 — 검증된 수집 로직 재사용
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard  # noqa: E402

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sse_starlette.sse import EventSourceResponse  # noqa: E402

POLL_OPEN = 5      # 초 — 장중 시세 폴링
POLL_CLOSED = 60   # 초 — 양 시장 모두 휴장 시
HIST_INTERVAL = 600  # 초 — 일봉/지표 갱신
STREAM_TICK = 2    # 초 — SSE 변경 감지 주기
HEARTBEAT = 15     # 초 — SSE keep-alive ping

# CORS 허용 출처 — Pages 도메인 (+ 환경변수로 확장 가능)
ALLOW_ORIGINS = ["https://kim22398.github.io"]
if os.environ.get("EXTRA_ORIGINS"):
    ALLOW_ORIGINS += [o.strip() for o in os.environ["EXTRA_ORIGINS"].split(",") if o.strip()]

# 공유 최신 스냅샷 — 폴러가 1회 갱신, SSE 클라이언트들은 lock 없이 읽기만 (이벤트 루프 블로킹 제거)
_LATEST = {"snap": None}
_TASKS = []


def _publish():
    _LATEST["snap"] = dashboard.snapshot()


def _market_open():
    snap = _LATEST["snap"]
    return bool(snap) and any(r.get("marketOpen") for r in snap["rows"])


async def _quote_poller():
    """5초(장중)/60초(휴장) 주기로 시세 갱신 — blocking 수집은 thread 로 오프로드."""
    while True:
        try:
            await asyncio.to_thread(dashboard.refresh_quotes)
            _publish()
        except Exception as e:
            print("quote poll error:", e)
        await asyncio.sleep(POLL_OPEN if _market_open() else POLL_CLOSED)


async def _hist_poller():
    """일봉/지표(RSI·이평·52주)는 10분 주기."""
    while True:
        try:
            await asyncio.to_thread(dashboard.refresh_history)
            _publish()
        except Exception as e:
            print("hist poll error:", e)
        await asyncio.sleep(HIST_INTERVAL)


@asynccontextmanager
async def lifespan(app):
    _publish()  # 빈 스냅샷이라도 즉시 준비 (snapshot/stream 초기 응답)
    _TASKS.append(asyncio.create_task(_hist_poller()))
    _TASKS.append(asyncio.create_task(_quote_poller()))  # 참조 보관 — GC 방지
    try:
        yield
    finally:
        for t in _TASKS:
            t.cancel()


app = FastAPI(title="energy-infra LIVE backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOW_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _resolve_sym(sym):
    """파일명 치환(_KS11) 역변환 허용 — dashboard.Handler 와 동일 규칙."""
    if sym not in dashboard.ALL_SYMBOLS and sym.startswith("_") and ("^" + sym[1:]) in dashboard.ALL_SYMBOLS:
        return "^" + sym[1:]
    return sym


def _sig(r):
    """행 변경 감지용 시그니처 — 시세 + 일봉지표(hist refresh로만 바뀌는 필드 포함)."""
    return (r.get("price"), r.get("dayPct"), r.get("volume"),
            r.get("marketOpen"), r.get("stale"), r.get("rsi"),
            r.get("sma50"), r.get("sma200"), r.get("hi52"), r.get("lo52"), r.get("avgVol20"))


@app.get("/snapshot")
async def snapshot():
    """초기 로드용 전체 스냅샷 — data.json 과 동일 스키마."""
    return JSONResponse(_LATEST["snap"] or dashboard.snapshot())


@app.get("/history/{sym}")
async def history(sym: str):
    real = _resolve_sym(sym)
    if real not in dashboard.ALL_SYMBOLS:
        return JSONResponse({"error": "unknown symbol"}, status_code=404)
    data = await asyncio.to_thread(dashboard.history_series, real)
    if data is None:
        return JSONResponse({"error": "no history"}, status_code=404)
    return JSONResponse(data)


@app.get("/stream")
async def stream(request: Request):
    """SSE — 시세 갱신마다 변경된 row 만 push (event: rows). 15초 heartbeat(ping)."""
    async def gen():
        last = {}
        first = True
        while True:
            if await request.is_disconnected():
                break
            snap = _LATEST["snap"]  # 공유 캐시 — lock/재계산 없이 읽기만
            if snap:
                rows = snap["rows"] + snap["bench"]
                if first:
                    for r in rows:
                        last[r["symbol"]] = _sig(r)
                    yield {"event": "rows",
                           "data": dashboard.json.dumps({"updated": snap["updated"], "rows": rows})}
                    first = False
                else:
                    changed = []
                    for r in rows:
                        sig = _sig(r)
                        if last.get(r["symbol"]) != sig:
                            last[r["symbol"]] = sig
                            changed.append(r)
                    if changed:
                        yield {"event": "rows",
                               "data": dashboard.json.dumps({"updated": snap["updated"], "rows": changed})}
            await asyncio.sleep(STREAM_TICK)

    return EventSourceResponse(gen(), ping=HEARTBEAT)


@app.get("/")
async def root():
    return {"service": "energy-infra LIVE backend",
            "endpoints": ["/snapshot", "/stream", "/history/{sym}"],
            "marketOpen": _market_open(), "updated": dashboard.LAST_QUOTE_TS[0]}
