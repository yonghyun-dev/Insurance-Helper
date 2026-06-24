#!/usr/bin/env bash
# provision.sh 산출물(.secrets.env + .deploy_key)을 GitHub 리포 시크릿으로 등록 (단일 환경).
# 사전: gh auth login, provision.sh 완료, .secrets.env 에 UPSTAGE_API_KEY/JWT_SECRET_KEY 추가.
set -euo pipefail
cd "$(dirname "$0")"
source ./vars.sh

gh auth status >/dev/null 2>&1 || { echo "gh auth login 먼저"; exit 1; }
[[ -f "$SECRETS_FILE" ]] || { echo "없음: $SECRETS_FILE — provision.sh 먼저"; exit 1; }
grep -q '^UPSTAGE_API_KEY=' "$SECRETS_FILE" || { echo "UPSTAGE_API_KEY 누락 — $SECRETS_FILE 에 추가"; exit 1; }

while IFS='=' read -r key val; do
  [[ "$key" =~ ^# || -z "$key" ]] && continue
  gh secret set "$key" --repo "$GH_REPO" --body "$val"
done < "$SECRETS_FILE"

# SSH 개인키(멀티라인)
gh secret set VM_SSH_KEY --repo "$GH_REPO" < "$DEPLOY_KEY"

echo "리포 시크릿 등록 완료. 이제 git push origin main 으로 자동 배포."
