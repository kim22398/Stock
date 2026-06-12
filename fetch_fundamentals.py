#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""주 1회 — dartlab(DART 한국 + EDGAR 미국 공시)로 전 종목 펀더멘털 수집 → docs/fundamentals.json.

의존성 격리: dartlab은 이 파일에서만 import 한다 (dashboard.py / fetch_data.py 무수정).
심볼 단일 소스: dashboard.UNIVERSE 재사용 (시세/수집 로직은 쓰지 않음).
dartlab (Apache-2.0): https://github.com/eddmpython/dartlab — 외부 API 키 불필요, HF 공시 데이터 자동 다운로드.

실측한 dartlab 0.10.x API 표면만 사용한다 (버전별로 다르므로):
  Company(code).analysis("financial","수익성")["marginTrend"]["history"]   → 영업이익률/매출YoY
  Company(code).analysis("financial","안정성")["leverageTrend"]["history"]  → 부채비율 (US+KR 공통)
  Company(code).analysis("가치평가")["relativeValuation"]["currentMultiples"] → 상대 PER (주로 KR)
  credit(code)["grade"]                                                      → dCR 신용등급 (한국만)
"""
import json
import os
import sys
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))
import dashboard  # noqa: E402  — 심볼 단일 소스 (표준 라이브러리만, dartlab 미사용)


def dart_code(sym):
    """한국 '267260.KS'/'033100.KQ' → '267260', 미국 티커는 그대로."""
    return sym.split(".")[0] if sym.endswith((".KS", ".KQ")) else sym


def is_kr(sym):
    return sym.endswith((".KS", ".KQ"))


def _latest(history, key):
    """history(최신순)에서 처음 만나는 비어있지 않은 값."""
    for h in history or []:
        if h.get(key) is not None:
            return h[key]
    return None


def _latest_two(history, key):
    vals = [h.get(key) for h in (history or []) if h.get(key) is not None]
    return (vals[0] if vals else None, vals[1] if len(vals) >= 2 else None)


def collect_one(sym):
    """한 종목 펀더멘털. 실패 항목은 None + 사유 로그, 전체 실패는 예외 전파."""
    import dartlab

    code = dart_code(sym)
    out = {"per_relative": None, "opMargin": None, "opMarginDir": None,
           "debtRatio": None, "revenueGrowth": None, "creditGrade": None}
    c = dartlab.Company(code)

    try:  # 영업이익률 + 매출 YoY
        hist = c.analysis("financial", "수익성")["marginTrend"]["history"]
        om0, om1 = _latest_two(hist, "operatingMargin")
        if om0 is not None:
            out["opMargin"] = round(om0, 2)
            if om1 is not None:
                out["opMarginDir"] = "↑" if om0 >= om1 else "↓"
        rg = _latest(hist, "revenueYoy")
        if rg is not None:
            out["revenueGrowth"] = round(rg, 2)
    except Exception as e:
        print(f"  [{sym}] 수익성 실패: {str(e)[:90]}")

    try:  # 부채비율 (US+KR 공통 — 안정성 leverageTrend)
        lh = c.analysis("financial", "안정성")["leverageTrend"]["history"]
        dr = _latest(lh, "debtRatio")
        if dr is not None:
            out["debtRatio"] = round(dr, 1)
    except Exception as e:
        print(f"  [{sym}] 안정성 실패: {str(e)[:90]}")

    try:  # 상대 PER (주로 KR; US는 None인 경우 많음 → 프론트가 UNIVERSE 값으로 폴백)
        per = c.analysis("가치평가")["relativeValuation"]["currentMultiples"].get("PER")
        if per is not None:
            out["per_relative"] = round(per, 1)
    except Exception as e:
        print(f"  [{sym}] 가치평가 실패: {str(e)[:90]}")

    if is_kr(sym):  # 신용등급 — 한국만 (미국은 yahoo 429로 느려 skip; 플랜 동일)
        try:
            out["creditGrade"] = dartlab.credit(code).get("grade")
        except Exception as e:
            print(f"  [{sym}] credit 실패: {str(e)[:90]}")

    return out


def main(symbols=None):
    syms = symbols or list(dashboard.UNIVERSE.keys())
    items, ok = {}, 0
    for sym in syms:
        try:
            d = collect_one(sym)
            items[sym] = d
            if any(d[k] is not None for k in
                   ("opMargin", "debtRatio", "revenueGrowth", "per_relative", "creditGrade")):
                ok += 1
                print(f"[{sym}] opM={d['opMargin']} dir={d['opMarginDir']} "
                      f"debt={d['debtRatio']} revG={d['revenueGrowth']} "
                      f"PER={d['per_relative']} cr={d['creditGrade']}")
            else:
                print(f"[{sym}] 수집 0 — 전부 null")
        except Exception as e:
            items[sym] = {"error": str(e)[:120]}
            print(f"[{sym}] 전체 실패: {str(e)[:120]}")

    out = {"updated": time.time(), "items": items}
    os.makedirs("docs", exist_ok=True)
    with open("docs/fundamentals.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\n펀더멘털 수집: {ok}/{len(syms)} 종목")
    if ok < len(syms) // 2:
        raise SystemExit("절반 이상 수집 실패 — 커밋 중단")


if __name__ == "__main__":
    # 인자로 심볼을 주면 부분 수집 (디버그/검증용), 없으면 전체.
    main(sys.argv[1:] or None)
