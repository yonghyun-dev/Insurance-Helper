# Track A 프로비저닝 공통 변수 — provision.sh / set-github-secrets.sh 가 source 한다.
# 값은 환경에 맞게 수정. SUFFIX 는 전역 고유 리소스명(ACR/Storage/PG)에 쓰이니 유일하게.

# 전역 고유 접미사 (소문자/숫자, 3~8자) — 팀/조직 식별자 권장
export SUFFIX="${SUFFIX:-dfocus}"

export LOCATION="${LOCATION:-koreacentral}"
export RG="${RG:-ica-rg}"

# 공유 리소스
export ACR_NAME="${ACR_NAME:-ica${SUFFIX}acr}"          # 5~50 영숫자, 전역 고유
export STORAGE="${STORAGE:-ica${SUFFIX}sa}"             # 3~24 소문자 영숫자, 전역 고유
export BLOB_CONTAINER="${BLOB_CONTAINER:-terms}"        # 약관 PDF 컨테이너(프라이빗)

# 환경별 Postgres (Flexible, pgvector) — 전역 고유
export PG_DEV="${PG_DEV:-ica-${SUFFIX}-pg-dev}"
export PG_PROD="${PG_PROD:-ica-${SUFFIX}-pg-prod}"
export PG_ADMIN="${PG_ADMIN:-icaadmin}"
export PG_DB="${PG_DB:-ica_db}"
export PG_SKU="${PG_SKU:-Standard_B2s}"                 # Burstable B2s (데모). 운영 시 GP
export PG_TIER="${PG_TIER:-Burstable}"
export PG_VERSION="${PG_VERSION:-16}"
export PG_STORAGE_GB="${PG_STORAGE_GB:-32}"

# 환경별 VM
export VM_DEV="${VM_DEV:-ica-vm-dev}"
export VM_PROD="${VM_PROD:-ica-vm-prod}"
export VM_SIZE="${VM_SIZE:-Standard_B4ms}"             # 4vCPU/16GB 버스터블 (대기형 워크로드)
export VM_IMAGE="${VM_IMAGE:-Ubuntu2204}"
export VM_ADMIN="${VM_ADMIN:-azureuser}"               # GitHub Actions VM_USER 와 동일

# GitHub 리포 (set-github-secrets.sh 가 사용; gh CLI 인증 필요)
export GH_REPO="${GH_REPO:-dfocus-ai/Insurance-Helper}"

# 산출물(시크릿) 저장 경로 — gitignore 됨
export SECRETS_DIR="${SECRETS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export DEPLOY_KEY="${SECRETS_DIR}/.deploy_key"         # 배포용 SSH 개인키(VM_SSH_KEY)
