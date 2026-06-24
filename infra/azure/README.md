# Azure 프로비저닝 (Track A)

2-VM(dev/prod) 완전 격리 + 환경별 Postgres(pgvector) + 공유 ACR/Blob 을 az CLI 로 일괄 생성한다.
설계: `docs/infra/azure-deploy.md`.

## 생성 리소스
- 리소스 그룹 1 (Korea Central)
- ACR 1 (공유, admin 활성)
- Storage + Blob 컨테이너 1 (약관 PDF, 프라이빗 · 아카이브용)
- Postgres Flexible 2 (dev/prod, pgvector allowlist, `ica_db`)
- VM 2 (dev/prod, Ubuntu+Docker, `/opt/ica`)
- 배포 SSH 키 1쌍, 환경별 시크릿 파일

## 사전 준비
- `az login` + 구독 선택(`az account set -s <id>`)
- `gh auth login` (시크릿 등록용)
- `openssl`, `ssh-keygen`

## 실행 순서
```bash
# 1) (선택) 이름 접미사 등 조정
vim infra/azure/vars.sh        # SUFFIX 는 전역 고유하게

# 2) 프로비저닝 (멱등 — 재실행 안전)
bash infra/azure/provision.sh

# 3) 앱 시크릿을 환경별 파일에 추가 (.env 에서 복사)
echo "UPSTAGE_API_KEY=$(grep ^UPSTAGE_API_KEY= .env | cut -d= -f2-)" | tee -a infra/azure/.secrets.dev.env infra/azure/.secrets.prod.env
echo "JWT_SECRET_KEY=$(grep ^JWT_SECRET_KEY= .env | cut -d= -f2-)"   | tee -a infra/azure/.secrets.dev.env infra/azure/.secrets.prod.env

# 4) GitHub Environment 시크릿 등록
bash infra/azure/set-github-secrets.sh

# 5) 배포 트리거
git push origin dev      # → 개발 VM
git push origin main     # → 운영 VM (Environment 승인 게이트 설정 시 승인 필요)
```

## 배포 후 데이터 적재 (Track C2 — Upstage 비용)
배포된 앱은 스키마/시드만 있고 **약관 청크는 비어 있다**. 로컬(약관 PDF + Upstage 키 보유)에서 Azure PG 로 직접 적재:
```bash
# 내 공인 IP 를 PG 방화벽에 임시 허용 (적재용)
MYIP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create -g ica-rg -n <PG_PROD> --rule-name local --start-ip-address $MYIP --end-ip-address $MYIP

# Azure PG 를 가리켜 적재 (DATABASE_URL 은 .secrets.prod.env 참조)
DATABASE_URL="<prod DATABASE_URL>" VECTOR_STORE=pgvector uv run ica ingest
DATABASE_URL="<prod DATABASE_URL>" uv run ica verify
# dev 환경도 동일 반복. 적재 후 방화벽 local 규칙 제거 권장.
```

## 주의
- `.secrets.*.env`, `.deploy_key*` 는 **gitignore** — 절대 커밋 금지.
- ACR admin 비번/PG 비번은 시크릿 파일에 평문 보존(로컬). 대회 후 로테이션.
- TLS(443/도메인): 운영 도메인 연결 후 nginx+certbot 추가 (Track D2). 현재 80 포트.
- prod 환경에 `Required reviewers` 설정 시 main 배포에 수동 승인 게이트가 걸린다.
- 정리: `az group delete -n ica-rg --yes` (전체 삭제).
