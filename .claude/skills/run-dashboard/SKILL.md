---
name: run-dashboard
description: Launch and verify the energy-infra stock dashboard — local server (:8765), data/fundamentals regen, the LIVE SSE backend (:8400), and browser-driven chart verification. Use when asked to run, start, smoke-test, screenshot, or verify this dashboard, or to confirm a change works in the real app.
---

# Run & verify the energy-infra dashboard

Three runtime modes share one frontend (`docs/index.html`, host auto-detect):
**local** (`dashboard.py` :8765), **Pages** (static `docs/`), **LIVE** (`server/app.py` SSE :8400).

## 1. Local dashboard (default — stdlib only, zero deps)

```bash
python3 dashboard.py        # serves http://localhost:8765
```
`dashboard.py`/`fetch_data.py` use only the Python standard library. Smoke-test:
```bash
for p in / /api/data /api/history/GEV /fundamentals.json; do
  curl -s -o /dev/null -w "%{http_code}  $p\n" "http://localhost:8765$p"; done
```
All four should be `200`. Data source is **naver finance** (no key; yahoo is blocked). If a
prior instance holds the port: `lsof -nP -iTCP:8765 -sTCP:LISTEN -t | xargs kill`.

Quick correctness check (no network): `python3 dashboard.py --selftest`.

## 2. Regenerate data files

```bash
python3 fetch_data.py                 # docs/data.json (quotes + indicators + 30d spark)
WRITE_HISTORY=1 python3 fetch_data.py # also docs/history/<symbol>.json (OHLC series, 40 files)
```
`^KS11` → filename `_KS11.json` (the `safeSym` rule, used identically in frontend/backend).

## 3. Fundamentals & LIVE backend need Python 3.12 (system python is 3.11)

`dartlab` is **Python ≥3.12 only**, and the LIVE backend wants FastAPI. Use `uv` for a 3.12 venv:

```bash
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh   # installs to ~/.local/bin
uv venv --python 3.12 /tmp/dash312 && source /tmp/dash312/bin/activate
```

**Fundamentals** (weekly job; first run downloads HF/EDGAR data, ~1 min/stock, cached in
`~/.cache/dartlab` or `~/Library/Caches/dartlab`):
```bash
uv pip install "dartlab==0.10.6"
python fetch_fundamentals.py GEV 267260.KS   # subset for a fast check; no args = all 38
# → docs/fundamentals.json {updated, items:{sym:{opMargin,debtRatio,revenueGrowth,per_relative,creditGrade}}}
```
KR symbols get `creditGrade` (dCR-*); US is null by design (it falls back to UNIVERSE PER).

**LIVE backend** (SSE push):
```bash
cd server && uv pip install -r requirements.txt
# CORS allows github.io; for a local browser test add the test origin:
EXTRA_ORIGINS="http://127.0.0.1:8088" uvicorn app:app --host 127.0.0.1 --port 8400
```
Test: `/snapshot` (200), `/stream` (SSE `event: rows`, payload `{updated, rows}`, 15s ping),
`/history/<sym>`. To exercise the frontend LIVE path, copy `docs/index.html` with
`BACKEND_URL` set to `http://127.0.0.1:8400`, serve it on a port listed in `EXTRA_ORIGINS`,
and confirm the badge flips to **LIVE 🔴**; killing the backend must degrade to 정적 모드 within 30s.

## 4. Browser verification (drive Chrome, don't just curl)

Charts (lightweight-charts via SRI-pinned CDN), heatmap, and the chart-panel DOM-move logic
only prove out in a real browser. Use `puppeteer-core` against the installed Chrome — no browser
download:

```bash
mkdir -p /tmp/dash-verify && cd /tmp/dash-verify
[ -d node_modules/puppeteer-core ] || npm i puppeteer-core@23 --silent
```
Driver essentials (executablePath = `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`,
`headless:'new'`, `--no-sandbox`, viewport 1440×900):
- Collect `page.on('pageerror')` and `console` errors — **expect 0** (a `favicon.ico` 404 is fine).
- Assert `window.LightweightCharts` is defined (if the SRI hash is wrong the script is **blocked** → undefined).
- Click `#body tr[data-sym]` → expect `tr.chart-row canvas` count ≈ 14 (candles + RSI charts).
- Heatmap fit: switch `#viewtabs .chip[data-v="heat"]`, assert `document.documentElement.scrollHeight <= 900`.
- Mobile: viewport 390 wide → `#cards .card` rendered, `scrollWidth <= innerWidth` (no h-scroll).

Look at a screenshot too — a blank frame is a failed launch, not a pass.

## 5. Tests / lint (CI parity)

```bash
python -m pytest -q      # tests/test_indicators.py (rsi/sma/snapshot/history-length)
ruff check .             # lenient: E9/F63/F7/F82 only (ruff.toml)
```

## Gotchas
- Two near-identical frontends used to exist; now `dashboard.py` serves `docs/index.html` from
  disk (single source) with a tiny stub fallback. Edit the UI in `docs/index.html` only.
- The data-bot (`update.yml`) commits `docs/` every 10 min during market hours — `git fetch` +
  `git pull --rebase` before pushing or the push is rejected.
- `UNIVERSE` in `dashboard.py` is the single source of symbols for every mode.
