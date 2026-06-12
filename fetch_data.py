#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Actions용 — 전 종목 시세/지표 수집 후 docs/data.json 생성 (네이버 금융)"""
import json
import os

import dashboard  # 같은 레포 루트의 dashboard.py 재사용

os.chdir(os.path.dirname(os.path.abspath(__file__)))

dashboard.refresh_quotes()
dashboard.refresh_history()

snap = dashboard.snapshot()
ok = sum(1 for r in snap["rows"] if r.get("price") is not None)
print(f"수집 완료: {ok}/{len(snap['rows'])} 종목")

os.makedirs("docs", exist_ok=True)
with open("docs/data.json", "w", encoding="utf-8") as f:
    json.dump(snap, f, ensure_ascii=False)

# 일봉 히스토리 영속화 — history.yml(일 1회)에서만 WRITE_HISTORY=1로 활성화
if os.environ.get("WRITE_HISTORY") == "1":
    os.makedirs("docs/history", exist_ok=True)
    hist_ok = 0
    for sym in dashboard.ALL_SYMBOLS:
        hs = dashboard.history_series(sym)
        if hs:
            path = os.path.join("docs/history", dashboard.safe_symbol(sym) + ".json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(hs, f, ensure_ascii=False)
            hist_ok += 1
    print(f"히스토리 생성: {hist_ok}/{len(dashboard.ALL_SYMBOLS)} 파일")

if ok < len(snap["rows"]) // 2:
    raise SystemExit("절반 이상 수집 실패 — 커밋 중단")
