#!/usr/bin/env bash
# provision.sh 산출물(.secrets.<env>.env + .deploy_key)을 GitHub Environment(dev/prod) 시크릿으로 등록.
# 사전: gh auth login, provision.sh 실행 완료, 각 .secrets.<env>.env 에 UPSTAGE_API_KEY/JWT_SECRET_KEY 추가.
set -euo pipefail
cd "$(dirname "$0")"
source ./vars.sh

gh auth status >/dev/null 2>&1 || { echo "gh auth login 먼저"; exit 1; }

set_env_secrets() {
  local ENV="$1"
  local FILE="${SECRETS_DIR}/.secrets.${ENV}.env"
  [[ -f "$FILE" ]] || { echo "없음: $FILE — provision.sh 먼저 실행"; exit 1; }
  grep -q '^UPSTAGE_API_KEY=' "$FILE" || { echo "[$ENV] UPSTAGE_API_KEY 누락 — $FILE 에 추가"; exit 1; }

  # GitHub Environment 생성(멱등)
  gh api -X PUT "repos/${GH_REPO}/environments/${ENV}" >/dev/null

  while IFS='=' read -r key val; do
    [[ "$key" =~ ^# || -z "$key" ]] && continue
    [[ "$key" == "PG_PASSWORD" ]] && continue   # DATABASE_URL 에 이미 포함(내부 보존용)
    gh secret set "$key" --env "$ENV" --repo "$GH_REPO" --body "$val"
  done < "$FILE"

  # SSH 개인키(멀티라인)는 파일에서 직접
  gh secret set VM_SSH_KEY --env "$ENV" --repo "$GH_REPO" < "$DEPLOY_KEY"
  echo "[$ENV] 시크릿 등록 완료"
}

set_env_secrets dev
set_env_secrets prod
echo "끝. 이제 git push dev / git push main 으로 자동 배포."
