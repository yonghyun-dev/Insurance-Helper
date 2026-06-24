#!/usr/bin/env bash
# Track A — Azure 프로비저닝 (1환경 올인원, 멱등).
# 생성: 리소스그룹 · ACR(공유) · VM 1대(Docker, nginx+backend+postgres 컨테이너) · SSH 키.
# 관리형 Postgres 없음(컨테이너 pgvector). dev 환경 없음.
#
# 사전: az login + 구독 선택. gh(시크릿 등록, 선택).
# 실행: bash infra/azure/provision.sh
# 산출: infra/azure/.secrets.env (gitignore) + .deploy_key (SSH 개인키)
set -euo pipefail
cd "$(dirname "$0")"
source ./vars.sh

say() { printf "\n\033[1;36m▶ %s\033[0m\n" "$*"; }
exists() { az "$@" >/dev/null 2>&1; }

az account show >/dev/null || { echo "az login 먼저"; exit 1; }
command -v openssl >/dev/null || { echo "openssl 필요"; exit 1; }

# ── 1. 리소스 그룹 ──
say "리소스 그룹 $RG ($LOCATION)"
exists group show -n "$RG" || az group create -n "$RG" -l "$LOCATION" -o none

# ── 2. ACR (admin 활성) ──
say "ACR $ACR_NAME"
exists acr show -n "$ACR_NAME" -g "$RG" \
  || az acr create -n "$ACR_NAME" -g "$RG" --sku Basic --admin-enabled true -o none
ACR_LOGIN_SERVER=$(az acr show -n "$ACR_NAME" -g "$RG" --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show -n "$ACR_NAME" --query username -o tsv)
ACR_PASSWORD=$(az acr credential show -n "$ACR_NAME" --query "passwords[0].value" -o tsv)

# ── 3. 배포용 SSH 키 (최초 1회) ──
say "배포 SSH 키"
if [[ ! -f "$DEPLOY_KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -C "ica-deploy" -f "$DEPLOY_KEY" -q
  echo "생성: $DEPLOY_KEY(.pub)"
else
  echo "기존 키 재사용"
fi
SSH_PUB=$(cat "${DEPLOY_KEY}.pub")

# ── 4. VM (올인원) ──
# 주의: --custom-data(cloud-init) 는 비-ASCII 구독명(예: '디포커스 AI')에서 az CLI latin-1
# 인코딩 버그를 유발 → 사용하지 않고 Docker 는 아래 SSH 로 설치. 포트 우선순위 900(SSH 1000 회피).
say "VM $VM_NAME ($VM_SIZE)"
if ! exists vm show -n "$VM_NAME" -g "$RG"; then
  az vm create -g "$RG" -n "$VM_NAME" -l "$LOCATION" --image "$VM_IMAGE" --size "$VM_SIZE" \
    --admin-username "$VM_ADMIN" --ssh-key-values "$SSH_PUB" \
    --public-ip-sku Standard -o none
fi
az vm open-port -g "$RG" -n "$VM_NAME" --port 80,443 --priority 900 -o none >/dev/null 2>&1 || true
VM_IP=$(az vm list-ip-addresses -g "$RG" -n "$VM_NAME" \
  --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv)

# ── 4b. Docker 설치 (cloud-init 대체, 멱등) ──
say "VM Docker 설치 (SSH $VM_IP)"
SSHO="-i $DEPLOY_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"
for _ in $(seq 1 12); do ssh $SSHO "${VM_ADMIN}@${VM_IP}" true 2>/dev/null && break || sleep 6; done
ssh $SSHO "${VM_ADMIN}@${VM_IP}" "command -v docker >/dev/null || curl -fsSL https://get.docker.com | sudo sh; sudo usermod -aG docker ${VM_ADMIN}; sudo mkdir -p /opt/ica; sudo chown -R ${VM_ADMIN}:${VM_ADMIN} /opt/ica; sudo systemctl enable --now docker" </dev/null

# ── 5. 컨테이너 Postgres 비밀번호 (최초 1회 생성, 보존) ──
if [[ -f "$SECRETS_FILE" ]] && grep -q '^POSTGRES_PASSWORD=' "$SECRETS_FILE"; then
  PG_PW=$(grep '^POSTGRES_PASSWORD=' "$SECRETS_FILE" | cut -d= -f2-)
else
  PG_PW=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
fi

# ── 6. 시크릿 파일 (gitignore) ──
umask 077
cat > "$SECRETS_FILE" <<EOF
# 배포 시크릿 — gitignore. set-github-secrets.sh 로 GitHub 리포 시크릿 등록.
ACR_LOGIN_SERVER=${ACR_LOGIN_SERVER}
ACR_USERNAME=${ACR_USERNAME}
ACR_PASSWORD=${ACR_PASSWORD}
VM_HOST=${VM_IP}
VM_USER=${VM_ADMIN}
POSTGRES_PASSWORD=${PG_PW}
PUBLIC_ORIGIN=http://${VM_IP}
EOF

say "완료 — VM=$VM_IP"
cat <<EOF
다음:
  1) 앱 키 추가(.env 에서 복사):
       echo "UPSTAGE_API_KEY=\$(grep ^UPSTAGE_API_KEY= .env | cut -d= -f2-)" >> infra/azure/.secrets.env
       echo "JWT_SECRET_KEY=\$(grep ^JWT_SECRET_KEY= .env | cut -d= -f2-)"   >> infra/azure/.secrets.env
  2) GitHub 시크릿 등록:  bash infra/azure/set-github-secrets.sh
  3) git push origin main → 자동 배포
  4) 데이터 적재(1회): infra/azure/README.md 참고 (PDF scp + ica ingest)
EOF
