# 배포 가이드 — LIVE 백엔드

SSE는 **상시 연결**이라 cold start가 있는 프리티어와 상성이 나쁘다. 24/7 무료 VM이 1순위.

## 옵션 A — Fly.io / Railway / Render (프리티어)

가장 빠르게 띄울 수 있으나 프리티어는 idle 시 슬립 → **cold start**(첫 연결 수 초 지연)가 있을 수 있다.
SSE 연결이 끊기면 프론트가 정적 모드로 강등되므로 치명적이진 않지만, LIVE 체감이 끊긴다.

```bash
# 예: Fly.io
fly launch --no-deploy            # fly.toml 생성 (internal_port = 8400)
fly deploy
fly scale count 1                  # 항상 1대 (auto-stop 끄기 권장)
```

`fly.toml`에서 `[http_service] auto_stop_machines = false` 로 두어야 슬립을 막는다.
시작 명령: `uvicorn app:app --host 0.0.0.0 --port 8400`.

## 옵션 B — Oracle Cloud Always Free VM (추천)

진짜 24/7 무료(Ampere A1 / AMD micro). SSE 상시 연결에 적합.

```bash
# VM(Ubuntu)에서
sudo apt update && sudo apt install -y python3-pip git
git clone https://github.com/kim22398/Stock.git && cd Stock/server
pip3 install -r requirements.txt
# systemd 서비스로 상주 (아래) 또는:
nohup uvicorn app:app --host 0.0.0.0 --port 8400 &
```

`/etc/systemd/system/energy-live.service`:

```ini
[Unit]
Description=energy-infra LIVE backend
After=network.target
[Service]
WorkingDirectory=/home/ubuntu/Stock/server
ExecStart=/home/ubuntu/.local/bin/uvicorn app:app --host 0.0.0.0 --port 8400
Restart=always
[Install]
WantedBy=multi-user.target
```

- Oracle **보안 목록(Ingress)** 에서 8400(또는 443) 포트를 연다.
- HTTPS 필요(아래) — 브라우저가 HTTPS Pages에서 HTTP 백엔드로 EventSource 연결 시 mixed-content 차단됨.

## 옵션 C — 집/사무실 PC + cloudflared tunnel

고정 IP/포트 개방 없이 HTTPS 도메인을 얻는다.

```bash
uvicorn app:app --port 8400 &
cloudflared tunnel --url http://localhost:8400      # 무료 임시 도메인
# 또는 named tunnel 로 고정 도메인
```

## 공통 주의점

- **HTTPS 필수**: Pages(`https://…github.io`)에서 `http://` 백엔드로 EventSource를 열면 mixed-content로 차단된다.
  옵션 B는 caddy/nginx 리버스 프록시 + Let's Encrypt, 옵션 C는 cloudflared가 HTTPS를 자동 제공.
- **CORS**: `app.py`의 `ALLOW_ORIGINS`에 Pages 도메인이 있어야 한다. 커스텀 도메인은 `EXTRA_ORIGINS` 환경변수로 추가.
- **BACKEND_URL**: 배포 후 `docs/index.html`의 `BACKEND_URL`을 백엔드 HTTPS 주소로 설정·커밋하면 Pages가 LIVE로 승격.
- **키 보안**: `KIS_*`/`FINNHUB_TOKEN`은 VM 환경변수/시크릿으로만 주입 (코드 하드코딩 금지).
