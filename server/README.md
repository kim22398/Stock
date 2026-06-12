# LIVE 백엔드 (SSE push)

항상 켜진 백엔드가 네이버 시세를 5초 폴링하고, SSE로 브라우저에 변경분만 push 한다.
Pages 정적 모드는 그대로 두고, 백엔드가 살아있으면 `docs/index.html`이 자동으로 **LIVE 모드**로 승격된다.
백엔드가 죽으면 30초 내 정적 모드로 자동 강등 (회귀 0).

## 실행

```bash
cd server
pip install -r requirements.txt
uvicorn app:app --port 8400
# 또는 외부 노출:  uvicorn app:app --host 0.0.0.0 --port 8400
```

데이터 소스는 레포 루트 `dashboard.py`의 검증된 수집 로직(`refresh_quotes`/`refresh_history`)을 그대로 재사용한다.

## 엔드포인트

| 경로 | 설명 |
|---|---|
| `GET /snapshot` | 초기 로드용 전체 스냅샷 (`data.json` 동일 스키마) |
| `GET /stream` | SSE. 시세 갱신마다 변경 row만 push (`event: rows`), 15초 heartbeat |
| `GET /history/{sym}` | 일봉 OHLC + 지표 시계열 (`^KS11`은 `_KS11`로 치환) |

## 프론트 연결

`docs/index.html` 상단 `BACKEND_URL` 상수를 백엔드 주소로 설정한다 (기본 `null` = 정적 모드 유지).

```js
const BACKEND_URL = "https://your-backend.example.com";
```

## 장중 게이팅

양 시장(미국/한국)이 모두 휴장이면 폴링 주기를 5초 → 60초로 낮춘다 (데이터 소스 예의 + 리소스 절약).

## v2 — 실시간 체결가 (선택)

`feeds/kis_ws.py`(한국투자증권), `feeds/finnhub_ws.py`(Finnhub)는 인터페이스 스텁이다.
환경변수 키가 없으면 자동 skip 하며, v1 폴링과 동일한 `on_tick` 시그니처로 STATE를 갱신하도록 통일돼 있다.

- `KIS_APP_KEY` / `KIS_APP_SECRET`
- `FINNHUB_TOKEN`

키는 절대 코드에 하드코딩하지 않는다 (환경변수만).

배포는 [`DEPLOY.md`](DEPLOY.md) 참고.
