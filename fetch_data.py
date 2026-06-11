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

if ok < len(snap["rows"]) // 2:
    raise SystemExit("절반 이상 수집 실패 — 커밋 중단")
