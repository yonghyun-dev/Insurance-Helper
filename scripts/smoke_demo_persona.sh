#!/usr/bin/env bash
set -u
cd /home/edgar/dev/Insurance-Helper
uv run uvicorn app.main:app --host 127.0.0.1 --port 8011 >/tmp/persona_srv.log 2>&1 &
SRV=$!
for i in $(seq 1 40); do
  curl -s -o /dev/null http://127.0.0.1:8011/api/v1/auth/demo-personas && break
  sleep 0.5
done
J=/tmp/persona_cookie.txt
echo "=== demo-login {김민서, 010-1234-5678} ==="
curl -s -c "$J" -X POST http://127.0.0.1:8011/api/v1/auth/demo-login \
  -H "Content-Type: application/json" \
  -d '{"name":"김민서","phone":"010-1234-5678"}' | python3 -m json.tool | head -8
echo "=== /me/insurances ==="
curl -s -b "$J" http://127.0.0.1:8011/api/v1/auth/me/insurances | python3 -m json.tool
echo "=== /me/health/history (treatments count) ==="
curl -s -b "$J" http://127.0.0.1:8011/api/v1/me/health/history | python3 -c "import sys,json; d=json.load(sys.stdin); print('treatments:', len(d.get('treatments',[]))); [print(' -', t['diagnosis'], t['claim_amount']) for t in d.get('treatments',[])]"
echo "=== demo-login miss {없는사람} → expect 404 ==="
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8011/api/v1/auth/demo-login \
  -H "Content-Type: application/json" -d '{"name":"없는사람","phone":"010-0000-0000"}'
kill "$SRV" 2>/dev/null
echo done
