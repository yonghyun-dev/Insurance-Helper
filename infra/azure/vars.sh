# Track A 프로비저닝 공통 변수 (1환경 올인원) — provision.sh / set-github-secrets.sh 가 source.
# 구조: VM 1대(B2s)에 nginx+backend+postgres(pgvector 컨테이너) 전부. 관리형 PG·dev 환경 없음.
# 값은 환경에 맞게 수정. SUFFIX 는 전역 고유 리소스명(ACR)에 쓰이니 유일하게.

export SUFFIX="${SUFFIX:-dfocus}"
export LOCATION="${LOCATION:-koreacentral}"
export RG="${RG:-ica-rg}"

# 공유: ACR (이미지 레지스트리, 전역 고유)
export ACR_NAME="${ACR_NAME:-ica${SUFFIX}acr}"

# 올인원 VM 1대 (nginx+backend+postgres 컨테이너)
export VM_NAME="${VM_NAME:-ica-vm}"
export VM_SIZE="${VM_SIZE:-Standard_B2s}"          # 2vCPU/4GB 버스터블 — 가벼운 워크로드에 충분
export VM_IMAGE="${VM_IMAGE:-Ubuntu2204}"
export VM_ADMIN="${VM_ADMIN:-azureuser}"           # GitHub Actions VM_USER 와 동일

# GitHub 리포 (set-github-secrets.sh — gh CLI 인증 필요)
export GH_REPO="${GH_REPO:-yonghyun-dev/Insurance-Helper}"

# 산출물(시크릿) 경로 — gitignore
export SECRETS_DIR="${SECRETS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export DEPLOY_KEY="${SECRETS_DIR}/.deploy_key"     # 배포용 SSH 개인키(VM_SSH_KEY)
export SECRETS_FILE="${SECRETS_DIR}/.secrets.env"  # 단일 환경 시크릿
