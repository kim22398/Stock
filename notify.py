#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""트리거 신규 발생 시 텔레그램 알림 (파이썬 표준 라이브러리만 — urllib).

update.yml 에서 fetch_data.py 직후, 커밋 직전에 실행한다.
이전 커밋(HEAD)의 docs/data.json 과 방금 생성된 docs/data.json 을 비교해
'새로 발생한' 트리거만 보낸다 (중복 방지 — 같은 상태가 유지되면 알림 0건).

트리거: 당일 ±3% 신규 진입 / 거래량 20일평균 2배 신규 / RSI 70·30 크로스 / 52주 신고가.
TELEGRAM_BOT_TOKEN · TELEGRAM_CHAT_ID (GitHub Secrets) 미설정 시 조용히 skip.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def _volx(r):
    v, a = r.get("volume"), r.get("avgVol20")
    return v / a if v and a else None


def _load_new():
    with open("docs/data.json", encoding="utf-8") as f:
        return json.load(f)


def _load_old():
    """직전 커밋(HEAD)의 data.json. 없으면(최초 실행) None."""
    try:
        out = subprocess.run(["git", "show", "HEAD:docs/data.json"],
                             capture_output=True, text=True, check=True)
        return json.loads(out.stdout)
    except Exception:
        return None


def _by_sym(snap):
    return {r["symbol"]: r for r in snap.get("rows", [])} if snap else {}


def new_triggers(old, new):
    """new 에서 '새로 켜진' 트리거만. 반환 [(symbol, name, [tag...], dayPct), ...]."""
    res = []
    for sym, n in new.items():
        o = old.get(sym)
        if not o:
            continue  # 신규 종목은 비교 불가 → skip
        tags = []
        dp_n, dp_o = n.get("dayPct"), o.get("dayPct")
        if dp_n is not None and abs(dp_n) >= 3 and not (dp_o is not None and abs(dp_o) >= 3):
            tags.append(f"{'+' if dp_n > 0 else ''}{dp_n:.1f}%")
        vx_n, vx_o = _volx(n), _volx(o)
        if vx_n is not None and vx_n >= 2 and not (vx_o is not None and vx_o >= 2):
            tags.append(f"거래량 {vx_n:.1f}x")
        r_n, r_o = n.get("rsi"), o.get("rsi")
        if r_n is not None and r_o is not None:
            if r_n >= 70 and r_o < 70:
                tags.append(f"RSI {r_n:.0f} 과열")
            elif r_n <= 30 and r_o > 30:
                tags.append(f"RSI {r_n:.0f} 과매도")
        h_n, h_o = n.get("hi52"), o.get("hi52")
        if h_n is not None and h_o is not None and h_n > h_o:
            tags.append("52주 신고가")
        if tags:
            res.append((sym, n.get("name", sym), tags, dp_n or 0))
    res.sort(key=lambda x: -abs(x[3]))
    return res


def format_msg(res):
    lines = ["⚡ 에너지 인프라 — 신규 트리거"]
    for sym, name, tags, dp in res[:10]:
        icon = "🔴" if dp < 0 else "🟢"
        lines.append(f"{icon} {sym.split('.')[0]} {name} | " + " | ".join(tags))
    return "\n".join(lines)


def send(text, token, chat):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as r:
        r.read()


def main():
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_* 미설정 — 알림 skip")
        return
    old = _by_sym(_load_old())
    new = _by_sym(_load_new())
    if not old:
        print("이전 data.json 없음 — 최초 실행, 알림 skip")
        return
    res = new_triggers(old, new)
    if not res:
        print("신규 트리거 없음 — 알림 0건")
        return
    send(format_msg(res), token, chat)
    print(f"알림 전송: {min(len(res), 10)}건")


if __name__ == "__main__":
    main()
