#!/usr/bin/env bash
# Track A — Azure 프로비저닝 (멱등). 2-VM(dev/prod) 완전 격리 + 환경별 Postgres(pgvector) + 공유 ACR/Blob.
#
# 사전: az CLI 로그인(az login), 구독 선택(az account set -s <id>), gh CLI(시크릿 등록용, 선택).
# 실행: bash infra/azure/provision.sh
# 산출: infra/azure/.secrets.dev.env / .secrets.prod.env (gitignore) + .deploy_key (SSH 개인키)
#
# 재실행 안전 — 이미 있으면 건너뛴다. 비밀번호는 최초 1회 생성해 시크릿 파일에 보존.
set -euo pipefail
cd "$(dirname "$0")"
source ./vars.sh

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
exists() { az "$@" >/dev/null 2>&1; }

# ── 0. 사전 점검 ──────────────────────────────────────────────
az account show >/dev/null || { echo "az login 먼저 실행"; exit 1; }
command -v openssl >/dev/null || { echo "openssl 필요"; exit 1; }

# ── 1. 리소스 그룹 ────────────────────────────────────────────
say "리소스 그룹 $RG ($LOCATION)"
exists group show -n "$RG" || az group create -n "$RG" -l "$LOCATION" -o none

# ── 2. ACR (공유, admin 활성 — Actions 가 user/pw 로 push/pull) ──
say "ACR $ACR_NAME"
exists acr show -n "$ACR_NAME" -g "$RG" \
  || az acr create -n "$ACR_NAME" -g "$RG" --sku Basic --admin-enabled true -o none
ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" -g "$RG" --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

# ── 3. Storage + Blob 컨테이너 (약관 PDF, 프라이빗) ───────────
say "Storage $STORAGE + 컨테이너 $BLOB_CONTAINER"
exists storage account show -n "$STORAGE" -g "$RG" \
  || az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 -o none
STORAGE_KEY=$(az storage account keys list -n "$STORAGE" -g "$RG" --query "[0].value" -o tsv)
az storage container create -n "$BLOB_CONTAINER" --account-name "$STORAGE" --account-key "$STORAGE_KEY" --public-access off -o none >/dev/null

# ── 4. 배포용 SSH 키 (VM_SSH_KEY) — 최초 1회 생성 ─────────────
say "배포 SSH 키"
if [[ ! -f "$DEPLOY_KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -C "ica-deploy" -f "$DEPLOY_KEY" -q
  echo "생성: $DEPLOY_KEY(.pub)"
else
  echo "기존 키 재사용: $DEPLOY_KEY"
fi
SSH_PUB=$(cat "${DEPLOY_KEY}.pub")

# ── 환경별 프로비저닝 함수 ────────────────────────────────────
provision_env() {
  local ENV="$1" PG="$2" VM="$3"
  local SECRETS_FILE="${SECRETS_DIR}/.secrets.${ENV}.env"

  # 비밀번호: 시크릿 파일에 있으면 재사용, 없으면 생성(재실행 시 PG 비번 불일치 방지)
  local PG_PW
  if [[ -f "$SECRETS_FILE" ]] && grep -q '^PG_PASSWORD=' "$SECRETS_FILE"; then
    PG_PW=$(grep '^PG_PASSWORD=' "$SECRETS_FILE" | cut -d= -f2-)
  else
    PG_PW=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
  fi

  say "[$ENV] Postgres $PG (pgvector)"
  if ! exists postgres flexible-server show -n "$PG" -g "$RG"; then
    az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOCATION" \
      --tier "$PG_TIER" --sku-name "$PG_SKU" --storage-size "$PG_STORAGE_GB" --version "$PG_VERSION" \
      --admin-user "$PG_ADMIN" --admin-password "$PG_PW" \
      --public-access None --yes -o none
  fi
  # pgvector allowlist (CREATE EXTENSION vector 전제) + DB + 적용 위해 재시작
  az postgres flexible-server parameter set -g "$RG" -s "$PG" --name azure.extensions --value vector -o none
  az postgres flexible-server db create -g "$RG" -s "$PG" -d "$PG_DB" -o none 2>/dev/null || true
  az postgres flexible-server restart -g "$RG" -n "$PG" -o none

  say "[$ENV] VM $VM ($VM_SIZE)"
  if ! exists vm show -n "$VM" -g "$RG"; then
    az vm create -g "$RG" -n "$VM" -l "$LOCATION" --image "$VM_IMAGE" --size "$VM_SIZE" \
      --admin-username "$VM_ADMIN" --ssh-key-values "$SSH_PUB" \
      --custom-data ./cloud-init.yaml --public-ip-sku Standard -o none
  fi
  az vm open-port -g "$RG" -n "$VM" --port 80,443 --priority 1000 -o none >/dev/null 2>&1 || true
  local VM_IP
  VM_IP=$(az vm list-ip-addresses -g "$RG" -n "$VM" --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv)

  # PG 방화벽: 이 VM 공인 IP 만 허용
  az postgres flexible-server firewall-rule create -g "$RG" -n "$PG" \
    --rule-name "vm-${ENV}" --start-ip-address "$VM_IP" --end-ip-address "$VM_IP" -o none

  local PG_HOST="${PG}.postgres.database.azure.com"
  local DATABASE_URL="postgresql+psycopg://${PG_ADMIN}:${PG_PW}@${PG_HOST}:5432/${PG_DB}?sslmode=require"

  # 환경 시크릿 파일 기록 (gitignore) — set-github-secrets.sh 가 읽음
  umask 077
  cat > "$SECRETS_FILE" <<EOF
# ${ENV} 환경 시크릿 — gitignore. set-github-secrets.sh 로 GitHub Environment 에 등록.
ACR_LOGIN_SERVER=${ACR_LOGIN_SERVER}
ACR_USERNAME=${ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD}
VM_HOST=${VM_IP}
VM_USER=${VM_ADMIN}
DATABASE_URL=${DATABASE_URL}
PG_PASSWORD=${PG_PW}
PUBLIC_ORIGIN=http://${VM_IP}
EOF
  echo "[$ENV] VM=$VM_IP  PG=$PG_HOST  →  $SECRETS_FILE"
}

provision_env dev  "$PG_DEV"  "$VM_DEV"
provision_env prod "$PG_PROD" "$VM_PROD"

say "완료. 다음:"
cat <<EOF
  1) UPSTAGE_API_KEY / JWT_SECRET_KEY 를 각 .secrets.<env>.env 에 추가(아래 키는 .env 에서 복사):
       echo "UPSTAGE_API_KEY=..." >> infra/azure/.secrets.dev.env   (prod 도 동일)
       echo "JWT_SECRET_KEY=..."  >> infra/azure/.secrets.dev.env
  2) GitHub Environment 시크릿 등록:  bash infra/azure/set-github-secrets.sh
  3) git push dev / git push main → 자동 배포
EOF
