# ⚡ 에너지 인프라 대시보드

AI capex / 전력 인프라 테마 38종목(미국+한국) 모니터링.

## 두 가지 모드

| 모드 | 갱신 | 사용법 |
|---|---|---|
| 로컬 (실시간) | 30초 | `python3 dashboard.py` → http://localhost:8765 |
| GitHub Pages (정적) | 장중 10분 주기 (5~15분 지연) | `docs/` Pages URL 접속 |

의존성 없음 — 파이썬 표준 라이브러리만 사용. 데이터: 네이버 금융 API (키 불필요. 야후 API는 IP 차단이 잦아 사용하지 않음).

## 구조

- `dashboard.py` — 로컬 서버 + 유니버스/지표 정의 (단일 소스)
- `fetch_data.py` — Actions용 수집 스크립트 → `docs/data.json`
- `.github/workflows/update.yml` — 한국장/미국장 시간대 10분 크론
- `docs/index.html` — Pages 정적 대시보드

## 색상 트리거

당일 ±3% · 52주 고점 -5% 이내(초록)/-20% 이탈(빨강) · RSI 70/30 · 거래량 20일 평균 2배+ · 200일선 이탈 · 어닝 D-7 배지

## 유니버스 수정

`dashboard.py`의 `UNIVERSE` 딕셔너리에 한 줄 추가/삭제하면 로컬·Pages 양쪽에 반영됨.
