# Azure 프로비저닝 (Track A — 1환경 올인원)

VM 1대에 nginx + backend + **postgres(pgvector 컨테이너)** 전부 올리는 최소 비용 구성.
관리형 Postgres·dev 환경 없음. 설계: `docs/infra/azure-deploy.md`.

## 생성 리소스 (월 ~$35, 끄면 ~$2)
- 리소스 그룹 1 (Korea Central)
- ACR 1 (Basic, 공유)
- VM 1 (B2s 2vCPU/4GB, Ubuntu+Docker, `/opt/ica`)
- 배포 SSH 키 1쌍, 시크릿 파일

## 사전 준비
- `az login` + 구독 선택(`az account set -s <id>`)
- `gh auth login`
- `openssl`, `ssh-keygen`

## 실행 순서
```bash
# 1) (선택) 이름/사이즈 조정
vim infra/azure/vars.sh        # SUFFIX 전역 고유, VM_SIZE 등

# 2) 프로비저닝 (멱등)
bash infra/azure/provision.sh

# 3) 앱 키를 시크릿 파일에 추가 (.env 에서 복사)
echo "UPSTAGE_API_KEY=$(grep ^UPSTAGE_API_KEY= .env | cut -d= -f2-)" >> infra/azure/.secrets.env
echo "JWT_SECRET_KEY=$(grep ^JWT_SECRET_KEY= .env | cut -d= -f2-)"   >> infra/azure/.secrets.env

# 4) GitHub 리포 시크릿 등록
bash infra/azure/set-github-secrets.sh

# 5) 배포 트리거
git push origin main           # → 올인원 VM 자동 배포 (web/backend/postgres)
```

## 배포 후 데이터 적재 (1회 — Upstage 비용)
배포된 앱은 스키마/시드만 있고 **약관 청크는 비어 있다**. postgres 가 VM 컨테이너라 적재도 VM 에서:
```bash
# 약관 PDF 를 VM 으로 복사 (로컬 data/raw → VM)
scp -i infra/azure/.deploy_key -r data/raw azureuser@<VM_IP>:/opt/ica/data/

# VM 에서 적재 + 검증
ssh -i infra/azure/.deploy_key azureuser@<VM_IP>
cd /opt/ica
docker compose -f docker-compose.prod.yml run --rm migrate ica ingest
docker compose -f docker-compose.prod.yml run --rm migrate ica verify
```

## 비용 절감 — 안 쓸 때 끄기
데모/심사 때만 켜고 평소엔 컴퓨팅 과금 정지:
```bash
az vm deallocate -g ica-rg -n ica-vm    # 정지 (디스크만 소액 과금)
az vm start      -g ica-rg -n ica-vm    # 재개 (공인 IP 가 바뀌면 VM_HOST 시크릿 갱신)
```

## 주의
- `.secrets.env`, `.deploy_key*` 는 **gitignore** — 절대 커밋 금지.
- postgres 데이터는 VM 의 docker 볼륨(`ica-pg-data`)에 영속. VM 삭제 시 사라짐(재적재 가능).
- TLS(443/도메인): 도메인 연결 후 nginx+certbot — Track D2.
- 전체 정리: `az group delete -n ica-rg --yes`.
