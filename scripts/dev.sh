#!/usr/bin/env bash
# 로컬 개발 서버 — 백엔드(uvicorn) + 프론트(vite) 동시 기동.
#
# 사용:
#   ./scripts/dev.sh            # 빈 포트 자동 선택(8001→8020…)
#   ./scripts/dev.sh 8020       # 백엔드 포트 지정
#
# 프론트(vite :5173)는 VITE_PROXY_TARGET 로 백엔드 포트에 자동 프록시된다.
set -euo pipefail
cd "$(dirname "$0")/.."

pick_port() {
  for p in "$@"; do
    if ! ss -ltn 2>/dev/null | grep -q ":$p "; then echo "$p"; return 0; fi
  done
  return 1
}

BACKEND_PORT="${1:-$(pick_port 8001 8020 8021 8022 8080 || true)}"
if [ -z "${BACKEND_PORT:-}" ]; then echo "빈 백엔드 포트를 찾지 못했습니다."; exit 1; fi

echo "▶ 백엔드 http://127.0.0.1:${BACKEND_PORT} (uvicorn, 최신 코드)"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT}" --log-level warning &
BACKEND_PID=$!
trap 'kill "${BACKEND_PID}" 2>/dev/null || true' EXIT INT TERM

# 백엔드 헬스 대기(최대 ~20초)
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://127.0.0.1:${BACKEND_PORT}/api/v1/products"; then break; fi
  sleep 0.5
done

echo "▶ 프론트 http://localhost:5173 (vite, 프록시→:${BACKEND_PORT})"
cd frontend
VITE_PROXY_TARGET="http://localhost:${BACKEND_PORT}" npm run dev
