#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
에너지 인프라 실시간 대시보드 (미국 + 한국)
- 의존성 없음 (파이썬 표준 라이브러리만 사용)
- 실행:  python3 dashboard.py
- 접속:  http://localhost:8765
- 데이터: 네이버 금융 API (시세 30초 / 지표용 일봉 10분 폴링)
  * 야후 API는 데이터센터 IP 429 차단으로 사용 불가 → 네이버로 교체

지표/색상 규칙 (행 좌측 보더 + 셀 색):
  당일등락   ±3% 강조
  52주고점   -5% 이내 진입(고점권) 초록 / -20% 이탈 빨강
  RSI(14)    >=70 과열 / <=30 과매도
  거래량     20일 평균 대비 2배+ 스파이크 강조
  200일선    이탈 시 경고
  어닝       D-7 이내 배지 강조
"""

import os
import json
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
QUOTE_INTERVAL = 7       # 초 — 시세 갱신 (네이버 공식 폴링 주기와 동일)
HIST_INTERVAL = 600      # 초 — 일봉/지표 갱신
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# ── 유니버스 ──────────────────────────────────────────────────────────
# (이름, 그룹, 시장, 포워드PER, 내재성장%, 어닝일 'YYYY-MM-DD', 비고)
UNIVERSE = {
    # 미국 — 기존 유니버스
    "GEV":   ("GE버노바",        "터빈/EPC",     "US", None, None, "2026-07-22", "섹터 방향타 — 백로그/슬롯"),
    "AGX":   ("아르간",          "터빈/EPC",     "US", 36.2, 43,   "2026-09-03", "가스발전 EPC"),
    "BE":    ("블룸에너지",      "연료전지",     "US", 53.8, None, "2026-07-30", "BTM, 52주 +1,025% (어닝일 추정)"),
    "STRL":  ("스털링",          "시공",         "US", 33.3, 107,  "2026-08-03", "DC 부지조성"),
    "MYRG":  ("MYR그룹",         "시공",         "US", 30.9, 51,   "2026-07-29", "T&D 시공"),
    "EME":   ("EMCOR",           "시공",         "US", 23.8, 17,   "2026-07-30", "로우베타 코너"),
    "IESC":  ("IES홀딩스",       "시공",         "US", None, None, None,         "전기 시공(DC)"),
    "FIX":   ("콤포트시스템즈",  "시공",         "US", None, None, "2026-07-23", "시공 백로그"),
    "POWL":  ("파웰",            "전력기기",     "US", None, None, "2026-08-04", "메가오더 마진 공개 예정"),
    "HUBB":  ("허벨",            "전력기기",     "US", None, None, "2026-07-28", "로우베타 코너"),
    "NVT":   ("엔벤트",          "전력기기",     "US", 27.9, 100,  "2026-07-31", "인클로저/액랭"),
    "VRT":   ("버티브",          "쿨링",         "US", None, None, "2026-07-29", "DC 전력 수요 체감치"),
    "MOD":   ("모딘",            "쿨링",         "US", 22.7, 400,  "2026-07-28", "내재성장 +400%는 왜곡 가능성"),
    "AAON":  ("AAON",            "쿨링",         "US", 36.8, 149,  "2026-08-10", "DC 공조"),
    "HWM":   ("하우멧",          "소재",         "US", None, None, "2026-08-06", "IGT 믹스, 영업마진 28.2%"),
    "CRS":   ("카펜터",          "소재",         "US", None, None, "2026-07-30", "특수합금"),
    "ATI":   ("ATI",             "소재",         "US", None, None, "2026-07-28", "티타늄/합금"),
    "CLF":   ("클리블랜드클리프스","소재",       "US", None, None, "2026-07-20", "전기강판 — 시즌 개막"),
    "BWXT":  ("BWXT",            "원자력/우라늄","US", 35.2, 39,   "2026-08-03", "원자로 부품/TRISO"),
    "CCJ":   ("카메코",          "원자력/우라늄","US", 50.0, 92,   "2026-07-30", "우라늄"),
    "LEU":   ("센트러스",        "원자력/우라늄","US", None, None, "2026-08-04", "HALEU"),
    "OKLO":  ("오클로",          "원자력/우라늄","US", None, None, None,         "SMR, 적자"),
    "SMR":   ("뉴스케일",        "원자력/우라늄","US", None, None, None,         "SMR, 적자, 52주 -74%"),
    # 미국 — 신규 추천
    "PWR":   ("퀀타서비스",      "시공",         "US", None, None, None,         "[추천] T&D 시공 1위 — MYRG/EME 비교축"),
    "ETN":   ("이튼",            "전력기기",     "US", None, None, None,         "[추천] 전력기기 메가캡, 로우베타"),
    "CEG":   ("콘스텔레이션",    "IPP",          "US", None, None, None,         "[추천] 원전 IPP — PPA 뉴스 수혜축"),
    "VST":   ("비스트라",        "IPP",          "US", None, None, None,         "[추천] 가스+원전 IPP"),
    # 한국 — 기존 유니버스
    "062040.KS": ("산일전기",        "전력기기", "KR", 23.8, None, None, "영업마진 36.9% — 미국 동종 대비 저평가"),
    "103590.KS": ("일진전기",        "전력기기", "KR", 20.1, None, None, ""),
    "033100.KQ": ("제룡전기",        "전력기기", "KR", None, None, None, "매출 -31% 경고"),
    "267260.KS": ("HD현대일렉트릭",  "전력기기", "KR", 28.0, None, None, ""),
    "298040.KS": ("효성중공업",      "전력기기", "KR", 26.5, None, None, ""),
    "010120.KS": ("LS ELECTRIC",     "전력기기", "KR", 51.5, None, None, "한국 전력기기 중 최고 멀티플"),
    "034020.KS": ("두산에너빌리티",  "터빈/EPC", "KR", 85.6, None, None, "포워드 85.6배"),
    # 한국 — 신규 추천
    "001440.KS": ("대한전선",        "전력기기", "KR", None, None, None, "[추천] 전선/변압기 2위축"),
    "052690.KS": ("한전기술",        "원자력/우라늄","KR", None, None, None, "[추천] 원전 설계 — SMR 서브테마"),
    "229640.KS": ("LS에코에너지",    "전력기기", "KR", None, None, None, "[추천] 전선/해저케이블"),
    "336260.KS": ("두산퓨얼셀",      "연료전지", "KR", None, None, None, "[추천] BE 한국 비교축"),
}

BENCHMARKS = {"QQQ": "나스닥100", "^KS11": "KOSPI"}

# ── 데이터 수집 (네이버 금융 — 야후는 IP 차단이 잦아 교체) ──────────────
STATE = {}
HIST_SERIES = {}  # sym → {"dates": [...], "close": [...], "volume": [...]} (원시 일봉 캐시)
STATE_LOCK = threading.Lock()
LAST_QUOTE_TS = [0.0]

# 미국 티커 → 네이버(로이터) 코드. NYSE=무접미사, NASDAQ=.O, 일부=.K
NAVER_US = {
    "GEV": "GEV", "AGX": "AGX", "BE": "BE", "STRL": "STRL.O", "MYRG": "MYRG.O",
    "EME": "EME", "IESC": "IESC.O", "FIX": "FIX", "POWL": "POWL.O", "HUBB": "HUBB.K",
    "NVT": "NVT", "VRT": "VRT", "MOD": "MOD", "AAON": "AAON.O", "HWM": "HWM",
    "CRS": "CRS", "ATI": "ATI", "CLF": "CLF", "BWXT": "BWXT.K", "CCJ": "CCJ",
    "LEU": "LEU", "OKLO": "OKLO.K", "SMR": "SMR", "PWR": "PWR", "ETN": "ETN",
    "CEG": "CEG.O", "VST": "VST", "QQQ": "QQQ.O",
}
US_SYMBOLS = [s for s, v in UNIVERSE.items() if v[2] == "US"] + ["QQQ"]
KR_SYMBOLS = [s for s, v in UNIVERSE.items() if v[2] == "KR"]
_REV_US = {NAVER_US[s]: s for s in US_SYMBOLS}


def _get(url, retries=2, timeout=12):
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            if attempt < retries:
                time.sleep(1 + attempt * 2)
    return None


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace(",", "").replace("%", "").strip()
    if not s or s in ("-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _set(sym, **kw):
    with STATE_LOCK:
        STATE.setdefault(sym, {}).update(kw)


def refresh_quotes():
    """미국/한국/KOSPI 시세를 배치 3건으로 갱신."""
    # 미국 — 배치 1건
    got = set()
    codes = ",".join(NAVER_US[s] for s in US_SYMBOLS)
    body = _get(f"https://polling.finance.naver.com/api/realtime/worldstock/stock/{codes}")
    if body:
        try:
            for it in json.loads(body).get("datas", []):
                sym = _REV_US.get(it.get("reutersCode") or it.get("itemCode"))
                if not sym:
                    continue
                _set(sym, price=_num(it.get("closePrice")),
                     dayPct=_num(it.get("fluctuationsRatio")),
                     volume=_num(it.get("accumulatedTradingVolume")),
                     currency="USD",
                     marketOpen=(it.get("marketStatus") == "OPEN"),
                     stale=False)
                got.add(sym)
        except Exception:
            pass
    # 한국 — 배치 1건
    codes = ",".join(s.split(".")[0] for s in KR_SYMBOLS)
    body = _get(f"https://polling.finance.naver.com/api/realtime/domestic/stock/{codes}")
    if body:
        try:
            for it in json.loads(body).get("datas", []):
                code = it.get("itemCode")
                sym = next((s for s in KR_SYMBOLS if s.split(".")[0] == code), None)
                if not sym:
                    continue
                _set(sym, price=_num(it.get("closePrice")),
                     dayPct=_num(it.get("fluctuationsRatio")),
                     volume=_num(it.get("accumulatedTradingVolume")),
                     currency="KRW",
                     marketOpen=(it.get("marketStatus") == "OPEN"),
                     stale=False)
                got.add(sym)
        except Exception:
            pass
    # KOSPI — 폴링 실패 시 일봉 마지막 2개로 폴백
    body = _get("https://polling.finance.naver.com/api/realtime/domestic/index/KOSPI")
    kospi_ok = False
    if body:
        try:
            datas = json.loads(body).get("datas", [])
            if datas:
                it = datas[0]
                _set("^KS11", price=_num(it.get("closePrice")),
                     dayPct=_num(it.get("fluctuationsRatio")),
                     prevClose=None, stale=False)
                kospi_ok = True
        except Exception:
            pass
    if not kospi_ok:
        try:
            _, _, _, _, closes, _ = _hist_kr("KOSPI", days=10)
            if len(closes) >= 2:
                _set("^KS11", price=closes[-1],
                     dayPct=(closes[-1] / closes[-2] - 1) * 100, stale=False)
                kospi_ok = True
        except Exception:
            pass
    for s in ALL_SYMBOLS:
        if s not in got and not (s == "^KS11" and kospi_ok):
            _set(s, stale=True)
    LAST_QUOTE_TS[0] = time.time()


def _date(days_ago=0):
    t = time.localtime(time.time() - days_ago * 86400)
    return time.strftime("%Y%m%d", t)


def _hist_us(sym):
    code = NAVER_US[sym]
    url = (f"https://api.stock.naver.com/chart/foreign/item/{urllib.parse.quote(code)}"
           f"/day?startDateTime={_date(370)}000000&endDateTime={_date(-1)}000000")
    body = _get(url)
    dates, opens, highs, lows, closes, vols = [], [], [], [], [], []
    if body:
        for row in json.loads(body):
            c = _num(row.get("closePrice"))
            if c is not None:
                dates.append(str(row.get("localDate", "")))
                opens.append(_num(row.get("openPrice")) or c)
                highs.append(_num(row.get("highPrice")) or c)
                lows.append(_num(row.get("lowPrice")) or c)
                closes.append(c)
                vols.append(_num(row.get("accumulatedTradingVolume")) or 0)
    return dates, opens, highs, lows, closes, vols


def _hist_kr(code, days=370):
    url = (f"https://api.finance.naver.com/siseJson.naver?symbol={code}"
           f"&requestType=1&startTime={_date(days)}&endTime={_date(-1)}&timeframe=day")
    body = _get(url)
    dates, opens, highs, lows, closes, vols = [], [], [], [], [], []
    if body:
        import ast
        for row in ast.literal_eval(body.strip()):  # 작은따옴표 혼용이라 json 불가
            # [날짜, 시가, 고가, 저가, 종가, 거래량, ...]
            if not isinstance(row, (list, tuple)) or len(row) < 6 or not str(row[0]).isdigit():
                continue
            c = _num(row[4])
            if c is not None:
                dates.append(str(row[0]))
                opens.append(_num(row[1]) or c)
                highs.append(_num(row[2]) or c)
                lows.append(_num(row[3]) or c)
                closes.append(c)
                vols.append(_num(row[5]) or 0)
    return dates, opens, highs, lows, closes, vols


def _hist_one(sym):
    try:
        if sym == "^KS11":
            dates, opens, highs, lows, closes, vols = _hist_kr("KOSPI")
        elif sym in NAVER_US:
            dates, opens, highs, lows, closes, vols = _hist_us(sym)
        else:
            dates, opens, highs, lows, closes, vols = _hist_kr(sym.split(".")[0])
        if closes:
            _set(sym, rsi=rsi14(closes), sma50=sma(closes, 50), sma200=sma(closes, 200),
                 avgVol20=(sum(vols[-21:-1]) / 20) if len(vols) >= 21 else None,
                 hi52=max(closes), lo52=min(closes))
            with STATE_LOCK:
                HIST_SERIES[sym] = {"dates": dates, "open": opens, "high": highs,
                                    "low": lows, "close": closes, "volume": vols}
    except Exception:
        pass


def refresh_history():
    """일봉 기반 지표(RSI/이평/52주/평균거래량) 갱신. 6병렬."""
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(_hist_one, ALL_SYMBOLS))


def safe_symbol(sym):
    """파일명 안전 치환 (^KS11 → _KS11). 프론트와 동일 규칙."""
    return sym.replace("^", "_")


def history_series(sym):
    """일봉 시계열 + 파생 지표 시리즈. 전 배열 길이 동일, 워밍업 구간은 None."""
    with STATE_LOCK:
        cached = HIST_SERIES.get(sym)
    if not cached:
        _hist_one(sym)
        with STATE_LOCK:
            cached = HIST_SERIES.get(sym)
    if not cached:
        return None
    dates = list(cached["dates"])
    opens = list(cached.get("open") or cached["close"])
    highs = list(cached.get("high") or cached["close"])
    lows = list(cached.get("low") or cached["close"])
    closes = list(cached["close"])
    vols = list(cached["volume"])
    rsi_s, sma50_s, sma200_s = [], [], []
    for i in range(1, len(closes) + 1):
        win = closes[:i]
        r = rsi14(win)
        rsi_s.append(round(r, 2) if r is not None else None)
        v = sma(win, 50)
        sma50_s.append(round(v, 2) if v is not None else None)
        v = sma(win, 200)
        sma200_s.append(round(v, 2) if v is not None else None)
    return {"symbol": sym, "dates": dates,
            "open": [round(o, 4) for o in opens],
            "high": [round(h, 4) for h in highs],
            "low": [round(lo, 4) for lo in lows],
            "close": [round(c, 4) for c in closes],
            "volume": [int(v) for v in vols],
            "rsi": rsi_s, "sma50": sma50_s, "sma200": sma200_s}


def rsi14(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period - 1) + gains[i]) / period
        avg_l = (avg_l * (period - 1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def sma(vals, n):
    return sum(vals[-n:]) / n if len(vals) >= n else None


ALL_SYMBOLS = US_SYMBOLS + KR_SYMBOLS + ["^KS11"]


def quote_loop():
    while True:
        try:
            refresh_quotes()
        except Exception:
            pass
        time.sleep(QUOTE_INTERVAL)


def hist_loop():
    while True:
        try:
            refresh_history()
        except Exception:
            pass
        time.sleep(HIST_INTERVAL)


def _spark(sym):
    """최근 30일 종가 — 행 내 스파크라인용 (히스토리 캐시 재사용, 추가 fetch 0회)."""
    hs = HIST_SERIES.get(sym)
    return [round(c, 4) for c in hs["close"][-30:]] if hs and hs.get("close") else None


def snapshot():
    rows, bench = [], []
    with STATE_LOCK:
        for sym, (name, group, mkt, fper, growth, earn, note) in UNIVERSE.items():
            s = dict(STATE.get(sym, {}))
            s.update({"symbol": sym, "name": name, "group": group, "market": mkt,
                      "fper": fper, "growth": growth, "earnings": earn, "note": note,
                      "spark": _spark(sym)})
            rows.append(s)
        for sym, name in BENCHMARKS.items():
            s = dict(STATE.get(sym, {}))
            s.update({"symbol": sym, "name": name, "spark": _spark(sym)})
            bench.append(s)
    return {"updated": LAST_QUOTE_TS[0], "rows": rows, "bench": bench}


# ── HTTP 서버 ────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(_HERE, "docs", "index.html")
FUNDAMENTALS_JSON = os.path.join(_HERE, "docs", "fundamentals.json")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/history/"):
            sym = urllib.parse.unquote(self.path[len("/api/history/"):].split("?")[0])
            if sym not in ALL_SYMBOLS and sym.startswith("_") and ("^" + sym[1:]) in ALL_SYMBOLS:
                sym = "^" + sym[1:]  # 파일명 치환 규칙(_KS11) 역변환 허용
            data = history_series(sym) if sym in ALL_SYMBOLS else None
            if data is None:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(data).encode()
            ctype = "application/json; charset=utf-8"
        elif self.path.startswith("/api/data"):
            body = json.dumps(snapshot()).encode()
            ctype = "application/json; charset=utf-8"
        elif self.path.startswith("/fundamentals.json"):
            # 로컬 모드에서도 펀더멘털 표시 — docs/fundamentals.json 정적 서빙 (없으면 404 → 프론트가 무시)
            try:
                with open(FUNDAMENTALS_JSON, "rb") as f:
                    body = f.read()
            except OSError:
                self.send_response(404)
                self.end_headers()
                return
            ctype = "application/json; charset=utf-8"
        elif self.path == "/" or self.path.startswith("/index"):
            # 프론트는 docs/index.html 단일 소스. 로컬/Pages가 host로 데이터소스 자동 감지.
            try:
                with open(INDEX_HTML, "rb") as f:
                    body = f.read()
            except OSError:
                body = ("<!doctype html><meta charset=utf-8>"
                        "<body style='font:14px sans-serif;background:#0d1117;color:#e6edf3;padding:40px'>"
                        "docs/index.html 을 찾을 수 없습니다 — 레포 루트에서 python3 dashboard.py 로 실행하세요."
                        ).encode("utf-8")
            ctype = "text/html; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)



def selftest():
    closes = [100 + i * 0.5 + (3 if i % 7 == 0 else 0) for i in range(260)]
    r = rsi14(closes)
    assert r is not None and 0 <= r <= 100, f"RSI 비정상: {r}"
    assert abs(sma(closes, 50) - sum(closes[-50:]) / 50) < 1e-9
    assert sma(closes[:10], 200) is None
    down = list(range(300, 100, -1))
    assert rsi14([float(x) for x in down]) < 10
    up = list(range(100, 300))
    assert rsi14([float(x) for x in up]) > 90
    print("selftest OK — RSI/SMA 검증 통과")


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)

    threading.Thread(target=quote_loop, daemon=True).start()
    threading.Thread(target=hist_loop, daemon=True).start()
    print(f"⚡ 에너지 인프라 대시보드: http://localhost:{PORT}")
    print(f"   종목 {len(UNIVERSE)}개 + 벤치마크 {len(BENCHMARKS)}개 | 시세 {QUOTE_INTERVAL}s / 지표 {HIST_INTERVAL//60}min 폴링")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
