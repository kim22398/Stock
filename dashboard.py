#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
에너지 인프라 실시간 대시보드 (미국 + 한국)
- 의존성 없음 (파이썬 표준 라이브러리만 사용)
- 실행:  python3 dashboard.py
- 접속:  http://localhost:8765
- 데이터: Yahoo Finance v8 chart API (시세 30초 / 지표용 일봉 10분 폴링)

지표/색상 규칙 (행 좌측 보더 + 셀 색):
  당일등락   ±3% 강조
  52주고점   -5% 이내 진입(고점권) 초록 / -20% 이탈 빨강
  RSI(14)    >=70 과열 / <=30 과매도
  거래량     20일 평균 대비 2배+ 스파이크 강조
  200일선    이탈 시 경고
  어닝       D-7 이내 배지 강조
"""

import json
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8765
QUOTE_INTERVAL = 30      # 초 — 시세 갱신
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

# ── 데이터 수집 ───────────────────────────────────────────────────────
STATE = {}
STATE_LOCK = threading.Lock()
LAST_QUOTE_TS = [0.0]


def fetch_chart(symbol, rng, interval, retries=2):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range={rng}&interval={interval}&includePrePost=false")
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
            res = data.get("chart", {}).get("result")
            return res[0] if res else None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(2 + attempt * 3)
                continue
            return None
        except Exception:
            if attempt < retries:
                time.sleep(1)
                continue
            return None


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


def update_history(symbol):
    res = fetch_chart(symbol, "1y", "1d")
    if not res:
        return
    q = res.get("indicators", {}).get("quote", [{}])[0]
    closes = [c for c in (q.get("close") or []) if c is not None]
    vols = [v for v in (q.get("volume") or []) if v]
    meta = res.get("meta", {})
    upd = {
        "rsi": rsi14(closes),
        "sma50": sma(closes, 50),
        "sma200": sma(closes, 200),
        "avgVol20": (sum(vols[-21:-1]) / 20) if len(vols) >= 21 else None,  # 당일 제외
        "hi52": meta.get("fiftyTwoWeekHigh") or (max(closes) if closes else None),
        "lo52": meta.get("fiftyTwoWeekLow") or (min(closes) if closes else None),
    }
    with STATE_LOCK:
        STATE.setdefault(symbol, {}).update(upd)


def update_quote(symbol):
    res = fetch_chart(symbol, "1d", "1d", retries=1)
    if not res:
        with STATE_LOCK:
            STATE.setdefault(symbol, {})["stale"] = True
        return
    meta = res.get("meta", {})
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    vol = meta.get("regularMarketVolume")
    if vol is None:
        q = res.get("indicators", {}).get("quote", [{}])[0]
        vs = [v for v in (q.get("volume") or []) if v]
        vol = vs[-1] if vs else None
    # 정규장 여부
    is_open = False
    try:
        reg = meta["currentTradingPeriod"]["regular"]
        is_open = reg["start"] <= time.time() <= reg["end"]
    except Exception:
        pass
    upd = {
        "price": price,
        "prevClose": prev,
        "dayPct": (price / prev - 1) * 100 if price and prev else None,
        "volume": vol,
        "currency": meta.get("currency"),
        "marketOpen": is_open,
        "marketTime": meta.get("regularMarketTime"),
        "stale": False,
    }
    with STATE_LOCK:
        STATE.setdefault(symbol, {}).update(upd)


ALL_SYMBOLS = list(UNIVERSE) + list(BENCHMARKS)


def quote_loop():
    while True:
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(update_quote, ALL_SYMBOLS))
        LAST_QUOTE_TS[0] = time.time()
        time.sleep(QUOTE_INTERVAL)


def hist_loop():
    while True:
        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(update_history, ALL_SYMBOLS))
        time.sleep(HIST_INTERVAL)


def snapshot():
    rows, bench = [], []
    with STATE_LOCK:
        for sym, (name, group, mkt, fper, growth, earn, note) in UNIVERSE.items():
            s = dict(STATE.get(sym, {}))
            s.update({"symbol": sym, "name": name, "group": group, "market": mkt,
                      "fper": fper, "growth": growth, "earnings": earn, "note": note})
            rows.append(s)
        for sym, name in BENCHMARKS.items():
            s = dict(STATE.get(sym, {}))
            s.update({"symbol": sym, "name": name})
            bench.append(s)
    return {"updated": LAST_QUOTE_TS[0], "rows": rows, "bench": bench}


# ── HTTP 서버 ────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data"):
            body = json.dumps(snapshot()).encode()
            ctype = "application/json; charset=utf-8"
        elif self.path == "/" or self.path.startswith("/index"):
            body = HTML.encode()
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


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>에너지 인프라 대시보드</title>
<style>
:root{
  --bg:#0d1117; --panel:#161b22; --border:#30363d; --txt:#e6edf3; --dim:#8b949e;
  --green:#3fb950; --green-bg:rgba(63,185,80,.13);
  --red:#f85149; --red-bg:rgba(248,81,73,.13);
  --orange:#d29922; --orange-bg:rgba(210,153,34,.15);
  --blue:#58a6ff; --purple:#bc8cff;
}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);
  font:13px/1.45 -apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif}
header{display:flex;flex-wrap:wrap;gap:14px;align-items:center;
  padding:10px 16px;border-bottom:1px solid var(--border);background:var(--panel);
  position:sticky;top:0;z-index:10}
header h1{font-size:15px;margin:0 8px 0 0}
.bench{display:flex;gap:6px;align-items:baseline;padding:3px 10px;border:1px solid var(--border);border-radius:6px}
.bench .nm{color:var(--dim);font-size:11px}
.badge{font-size:11px;padding:2px 8px;border-radius:10px;border:1px solid var(--border);color:var(--dim)}
.badge.open{color:var(--green);border-color:var(--green)}
#updated{margin-left:auto;color:var(--dim);font-size:11px}
.controls{display:flex;flex-wrap:wrap;gap:6px;padding:8px 16px}
.chip{cursor:pointer;font-size:12px;padding:3px 10px;border-radius:12px;
  border:1px solid var(--border);background:transparent;color:var(--dim)}
.chip.on{color:var(--txt);border-color:var(--blue);background:rgba(88,166,255,.12)}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:5px 9px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--border)}
th{position:sticky;top:46px;background:var(--panel);color:var(--dim);font-size:11px;
  cursor:pointer;user-select:none;z-index:5}
th:hover{color:var(--txt)} th .arr{color:var(--blue)}
td:first-child,th:first-child,td:nth-child(2),th:nth-child(2){text-align:left}
tr.r-up{box-shadow:inset 3px 0 0 var(--green)}
tr.r-dn{box-shadow:inset 3px 0 0 var(--red)}
tr.r-vol{box-shadow:inset 3px 0 0 var(--orange)}
tr:hover td{background:rgba(255,255,255,.03)}
.sym{color:var(--dim);font-size:11px;margin-left:5px}
.grp{font-size:11px;color:var(--dim)}
.up{color:var(--green)} .dn{color:var(--red)}
.c-strong-up{background:var(--green-bg);color:var(--green);font-weight:600}
.c-strong-dn{background:var(--red-bg);color:var(--red);font-weight:600}
.c-hot{background:var(--orange-bg);color:var(--orange);font-weight:600}
.c-cold{color:var(--blue);font-weight:600}
.c-near{background:var(--green-bg);color:var(--green)}
.c-deep{background:var(--red-bg);color:var(--red)}
.c-warn{color:var(--red)}
.tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:8px;margin-left:4px}
.tag.earn{background:rgba(188,140,255,.15);color:var(--purple);border:1px solid var(--purple)}
.tag.rec{background:rgba(88,166,255,.12);color:var(--blue)}
.note{color:var(--dim);font-size:11px;max-width:260px;overflow:hidden;text-overflow:ellipsis}
.stale{opacity:.45}
.legend{padding:6px 16px 14px;color:var(--dim);font-size:11px}
.legend span{margin-right:14px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle}
</style>
</head>
<body>
<header>
  <h1>⚡ 에너지 인프라</h1>
  <div id="benchbar"></div>
  <span class="badge" id="us-mkt">US</span>
  <span class="badge" id="kr-mkt">KR</span>
  <span id="updated">로딩 중…</span>
</header>
<div class="controls" id="mktchips">
  <button class="chip on" data-m="ALL">전체</button>
  <button class="chip" data-m="US">미국</button>
  <button class="chip" data-m="KR">한국</button>
</div>
<div class="controls" id="grpchips"></div>
<table id="tbl">
  <thead><tr id="hdr"></tr></thead>
  <tbody id="body"></tbody>
</table>
<div class="legend">
  <span><span class="dot" style="background:var(--green)"></span>급등/고점권(-5% 이내)</span>
  <span><span class="dot" style="background:var(--red)"></span>급락/고점-20%/200일선 이탈</span>
  <span><span class="dot" style="background:var(--orange)"></span>거래량 2배+ / RSI 70+</span>
  <span><span class="dot" style="background:var(--purple)"></span>어닝 D-7 이내</span>
  <span>행 좌측 보더 = 당일 ±3% 또는 거래량 스파이크</span>
</div>
<script>
const COLS=[
 ["name","종목"],["group","그룹"],["price","현재가"],["dayPct","등락%"],
 ["from52h","52주고점比"],["rsi","RSI"],["volX","거래량x"],
 ["vs200","200일선比"],["fper","fPER"],["growth","내재성장%"],
 ["dEarn","어닝"],["note","비고"]
];
let DATA=[], sortKey=localStorage.getItem("sk")||"dayPct",
    sortDir=+(localStorage.getItem("sd")||-1),
    mkt=localStorage.getItem("mk")||"ALL",
    grps=new Set(JSON.parse(localStorage.getItem("gs")||"[]"));

function fmtP(v,cur){if(v==null)return"—";
 const p=cur==="KRW"?v.toLocaleString("ko-KR",{maximumFractionDigits:0})
   :v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
 return p+(cur==="KRW"?"₩":cur==="USD"?"$":"");}
function pct(v,d=1){return v==null?"—":(v>0?"+":"")+v.toFixed(d)+"%";}
function n1(v){return v==null?"—":v.toFixed(1);}

function derive(r){
 r.from52h=(r.price&&r.hi52)?(r.price/r.hi52-1)*100:null;
 r.vs200=(r.price&&r.sma200)?(r.price/r.sma200-1)*100:null;
 r.vs50=(r.price&&r.sma50)?(r.price/r.sma50-1)*100:null;
 r.volX=(r.volume&&r.avgVol20)?r.volume/r.avgVol20:null;
 if(r.earnings){const d=Math.ceil((new Date(r.earnings+"T00:00:00")-Date.now())/864e5);
   r.dEarn=d>=0?d:null;}else r.dEarn=null;
 return r;}

function rowClass(r){
 if(r.dayPct!=null&&r.dayPct<=-3)return"r-dn";
 if(r.dayPct!=null&&r.dayPct>=3)return"r-up";
 if(r.volX!=null&&r.volX>=2&&r.marketOpen)return"r-vol";
 return"";}

function cell(k,r){
 switch(k){
  case"name":{let t=`<b>${r.name}</b><span class="sym">${r.symbol}</span>`;
   if((r.note||"").includes("[추천]"))t+=`<span class="tag rec">추천</span>`;
   return t;}
  case"group":return`<span class="grp">${r.group}</span>`;
  case"price":return fmtP(r.price,r.currency);
  case"dayPct":{let c=r.dayPct==null?"":r.dayPct>=3?"c-strong-up":r.dayPct<=-3?"c-strong-dn":r.dayPct>0?"up":r.dayPct<0?"dn":"";
   return`<span class="${c}">${pct(r.dayPct,2)}</span>`;}
  case"from52h":{let c=r.from52h==null?"":r.from52h>=-5?"c-near":r.from52h<=-20?"c-deep":"";
   return`<span class="${c}">${pct(r.from52h)}</span>`;}
  case"rsi":{let c=r.rsi==null?"":r.rsi>=70?"c-hot":r.rsi<=30?"c-cold":"";
   return`<span class="${c}">${n1(r.rsi)}</span>`;}
  case"volX":{let c=r.volX!=null&&r.volX>=3?"c-strong-up":r.volX!=null&&r.volX>=2?"c-hot":"";
   return`<span class="${c}">${r.volX==null?"—":r.volX.toFixed(1)+"x"}</span>`;}
  case"vs200":{let c=r.vs200!=null&&r.vs200<0?"c-warn":"";
   return`<span class="${c}">${pct(r.vs200)}</span>`;}
  case"fper":return r.fper==null?"—":r.fper.toFixed(1);
  case"growth":return r.growth==null?"—":"+"+r.growth+"%";
  case"dEarn":return r.dEarn==null?"—":r.dEarn<=7?`<span class="tag earn">D-${r.dEarn}</span>`:"D-"+r.dEarn;
  case"note":return`<span class="note" title="${r.note||""}">${(r.note||"").replace("[추천] ","")}</span>`;
 }return"";}

function render(){
 // 헤더
 document.getElementById("hdr").innerHTML=COLS.map(([k,l])=>
  `<th data-k="${k}">${l}${k===sortKey?`<span class="arr">${sortDir>0?" ▲":" ▼"}</span>`:""}</th>`).join("");
 document.querySelectorAll("#hdr th").forEach(th=>th.onclick=()=>{
  const k=th.dataset.k;
  if(k===sortKey)sortDir*=-1;else{sortKey=k;sortDir=-1;}
  localStorage.setItem("sk",sortKey);localStorage.setItem("sd",sortDir);render();});
 // 그룹칩
 const allG=[...new Set(DATA.map(r=>r.group))];
 document.getElementById("grpchips").innerHTML=allG.map(g=>
  `<button class="chip ${grps.size===0||grps.has(g)?"on":""}" data-g="${g}">${g}</button>`).join("");
 document.querySelectorAll("#grpchips .chip").forEach(b=>b.onclick=()=>{
  const g=b.dataset.g;
  if(grps.size===0){grps=new Set([g]);}
  else if(grps.has(g)){grps.delete(g);}
  else grps.add(g);
  if(grps.size===allG.length)grps.clear();
  localStorage.setItem("gs",JSON.stringify([...grps]));render();});
 document.querySelectorAll("#mktchips .chip").forEach(b=>{
  b.classList.toggle("on",b.dataset.m===mkt);
  b.onclick=()=>{mkt=b.dataset.m;localStorage.setItem("mk",mkt);render();};});
 // 정렬+필터
 let rows=DATA.filter(r=>(mkt==="ALL"||r.market===mkt)&&(grps.size===0||grps.has(r.group)));
 rows.sort((a,b)=>{
  let x=a[sortKey],y=b[sortKey];
  if(typeof x==="string")return sortDir*String(x).localeCompare(String(y),"ko");
  if(x==null)return 1; if(y==null)return -1;
  return sortDir*(x-y);});
 document.getElementById("body").innerHTML=rows.map(r=>
  `<tr class="${rowClass(r)} ${r.stale?"stale":""}">${COLS.map(([k])=>`<td>${cell(k,r)}</td>`).join("")}</tr>`).join("");
}

async function refresh(){
 try{
  const d=await(await fetch("/api/data")).json();
  DATA=d.rows.map(derive);
  // 벤치마크 바
  document.getElementById("benchbar").innerHTML=d.bench.map(b=>{
   const p=b.price&&b.prevClose?(b.price/b.prevClose-1)*100:null;
   return`<span class="bench"><span class="nm">${b.name}</span><span class="${p>0?"up":p<0?"dn":""}">${pct(p,2)}</span></span>`;
  }).join(" ");
  const us=d.rows.find(r=>r.market==="US"&&r.marketOpen),
        kr=d.rows.find(r=>r.market==="KR"&&r.marketOpen);
  document.getElementById("us-mkt").className="badge"+(us?" open":"");
  document.getElementById("us-mkt").textContent="US "+(us?"장중":"휴장");
  document.getElementById("kr-mkt").className="badge"+(kr?" open":"");
  document.getElementById("kr-mkt").textContent="KR "+(kr?"장중":"휴장");
  document.getElementById("updated").textContent=
   d.updated?"갱신 "+new Date(d.updated*1000).toLocaleTimeString("ko-KR"):"수집 중…";
  render();
 }catch(e){document.getElementById("updated").textContent="서버 연결 끊김";}
}
refresh();setInterval(refresh,15000);
</script>
</body>
</html>"""


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
