# Azure 배포 설계 (VM + nginx + docker-compose + pgvector)

- 작성: 2026-06-24
- 상태: 설계 확정 (구현 전). 작업 분해는 본문 末 §8.
- 선행 결정(사용자): ① 컴퓨팅 = **단일 VM + docker-compose + nginx**(자체관리) ② 벡터 = **Azure Postgres Flexible + pgvector 통합**(Chroma 제거)

---

## 1. 배경·목표

대회 데모/소규모 운영을 위해 현재 로컬(SQLite + Chroma) 스택을 Azure로 올린다.
- 프론트(React/Vite 정적) + 백엔드(FastAPI) + 약관 RAG.
- **[하드 제약]** 제품 전 영역 국내 AI(Upstage) 전용. → 호스팅은 **Korea Central(한국 중부)** 로 국내 데이터 잔류 + Upstage 지연 최소.

## 2. 핵심 통찰 — 왜 "가벼운 컴퓨팅 + 관리형 DB"인가

1. **무거운 AI가 전부 외부(Upstage API)**: Solar 추론·solar-embedding·Document Parse 모두 외부 호출. 백엔드는 I/O-bound 오케스트레이터 → **GPU 불필요, CPU/RAM 소형, 유휴 대기 多**(버스터블 VM에 유리).
2. **벡터 코퍼스가 작다(2,189청크)**: 4096-d exact(무인덱스) 코사인 스캔이 sub-ms. ANN 인덱스 불필요.
3. **pgvector 경로는 이미 코드에 존재**(아래 §6). 이번 작업은 *구현*이 아니라 *프로비저닝·연결·검증*.

## 3. 확정 아키텍처

```
                 [사용자] ──HTTPS(443)──┐
                                        ▼
        ┌──────────── Azure VM (Ubuntu, docker-compose) ────────────┐
        │  nginx 컨테이너                                             │
        │   ├ dist/ 정적 서빙 (Vite 빌드)                              │
        │   ├ /api → 백엔드 리버스프록시 + LB(라운드로빈)                │
        │   └ TLS 종단 (certbot / acme-companion, 자동갱신)            │
        │        ├──► backend #1 (uvicorn, FastAPI)                   │
        │        ├──► backend #2                                      │
        │        └──► backend #3   (compose --scale backend=3)        │
        └──────┬─────────────────────────────┬──────────────────────┘
               │ 외부 egress                  │ DB (5432, SSL)
               ▼                              ▼
        Upstage API (국내 AI)        Azure Database for PostgreSQL Flexible
        Solar·임베딩·OCR             ├ clause_chunks / users / audit (관계형)
                                     └ clause_chunks.embedding vector(4096) — exact scan
               │ 인덱싱 시에만
               ▼
        Azure Blob Storage (약관 PDF — 인덱싱 소스/아카이브, 런타임 무관)

   가로지원: ACR(이미지) · Key Vault(시크릿) · GitHub Actions(CI/CD) · App Insights/Log Analytics
```

## 4. 구성 요소 확정값

| 영역 | 선택 | 사이징/근거 |
|:--|:--|:--|
| 리전 | **Korea Central** | 국내 잔류 + Upstage 지연 |
| VM | **B4ms (4vCPU/16GB)** Ubuntu LTS | 워크로드 유휴 대기형 → 버스터블 크레딧 비용효율. 안전 시 D4s_v5 |
| 디스크 | Premium SSD P10(~128GB) | OS + docker. PDF는 Blob(디스크 X) |
| 백엔드 replica | 데모 **1** 권장 / 2+ 는 §5.7 선결 | 멀티턴 세션이 프로세스 메모리 → 2+ replica 는 sticky/Redis 필요 |
| 백엔드 컨테이너 | 0.5~1 vCPU / 1~2GB each | API 대기형이라 경량 |
| DB | **Postgres Flexible B2s (2vCPU/4GB)** | 관계형+벡터 통합. 운영 시 GP D2ds |
| 벡터 | `clause_chunks.embedding vector(4096)`, **인덱스 없음**(exact) | 2189행 sub-ms |
| 스토리지 | **Blob Standard Hot**, 프라이빗 + Managed Identity | PDF 인덱싱 소스 |
| TLS | nginx + certbot(Let's Encrypt) 자동갱신 | VM 자체관리 표준 |
| 시크릿 | **Key Vault** → 배포 시 `.env`(chmod 600) | UPSTAGE_API_KEY·JWT_SECRET·DATABASE_URL |
| 레지스트리 | **ACR Basic** | backend·nginx 이미지 |
| CI/CD | **GitHub Actions** → ACR 빌드/푸시 → VM SSH `compose pull && up -d` | repo 이미 연결됨 |
| 관측 | App Insights + Log Analytics (또는 기존 prometheus + node-exporter) | 감사로그 연계 |

## 5. 비-자명한 함정 (반드시 선반영)

1. **Azure Postgres의 pgvector는 allowlist 필요**: 서버 파라미터 `azure.extensions` 에 `VECTOR` 를 명시해야 `CREATE EXTENSION vector` 가 통과한다. (기본 비활성 → 누락 시 마이그레이션 실패)
2. **nginx + compose 스케일 DNS**: 오픈소스 nginx는 `upstream` 을 시작 시 1회만 DNS 해석 → `--scale` 로 늘린 replica 미인식. **Docker 임베디드 DNS(`resolver 127.0.0.11 valid=10s;`) + 변수 proxy_pass**(`set $up backend; proxy_pass http://$up:8000;`) 로 런타임 재해석해야 3개에 분산.
3. **fresh Postgres에 alembic 전 리비전 적용**: 초기 리비전(`e9ae743…`)부터 sprint16까지 Postgres에서 처음부터 `upgrade head` 가 통과하는지 검증(SQLite 가정 잔존 점검). pgvector 리비전은 이미 dialect 분기(`if bind.dialect.name != "postgresql": return`)로 보호됨.
4. **4096-d ANN 인덱스 불가**: pgvector 한계(vector 2000 / halfvec 4000). 현재 exact로 충분하나, 코퍼스 10만+ 성장 시 ① 임베딩 차원 축소(≤2000) ② Azure AI Search/Qdrant 분리. (sprint16 마이그레이션에 이미 명시·구현됨)
5. **데이터 이관 ≠ 덤프**: SQLite→PG는 약관 PDF가 Blob에 있으므로 **`ica ingest` 재적재가 가장 깔끔**(청크/임베딩 재생성). users/demo는 `ica seed-demo`, audit은 신규 시작.
6. **휘발 컨셉**: 세션 상태 영속 불필요(JWT). 단 audit log는 Postgres 영속(정책).
7. **⚠️ 세션 affinity (로컬 검증에서 발견)**: `SessionStore` 는 **프로세스 메모리 dict**(`app/domains/sessions/store.py`, 30분 TTL). nginx 라운드로빈으로 **멀티턴의 각 턴이 다른 replica 로 분산되면 세션이 유실**된다(턴2에서 세션 미존재 에러 실측). → **백엔드 2+ replica 는 다음 중 하나 필수**:
   - (a) **단일 replica**(데모 최단경로, HA 포기) — 30분 휘발 세션엔 수용 가능
   - (b) **nginx sticky**(ip_hash) — 단 OSS nginx 는 `upstream` 블록이 시작 시 1회 DNS 해석이라 `--scale` 동적 IP 와 충돌(고정 upstream 필요)
   - (c) **공유 세션스토어(Redis)** — `SessionStore` 를 Redis 백엔드로(중간 규모 코드 작업, 가장 견고)
   - 참고: 관리형 ACA 는 세션 affinity 옵션 내장 — VM+nginx 자체관리의 트레이드오프.

## 6. 코드 변경 — 거의 없음 (이미 구현됨)

이번 전환의 핵심 코드는 **Sprint 12·16에서 이미 완성**되어 있다. 신규 구현 최소.

| 구성 | 상태 | 위치 |
|:--|:--|:--|
| `VectorStoreAdapter` Protocol | ✅ 존재 | `app/domains/rag/vectorstore.py` |
| `PgVectorAdapter` (upsert/query/delete/count/dim/health/reset) | ✅ **완전 구현** (`<=>` exact, vector(4096)) | 동 파일 |
| `get_vector_store()` 팩토리 (effective_vector_store 분기) | ✅ 존재 | 동 파일 |
| `database_url` + `vector_store` 토글 + 자동감지 | ✅ 존재 | `app/infrastructure/core/config.py` |
| alembic: embedding 컬럼 생성(dialect 분기) | ✅ `b1c2d3e4f5a6_sprint12` | `alembic/versions/` |
| alembic: vector(4096) + HNSW 제거(exact) | ✅ `d3e4f5a6b7c8_sprint16` | 동 |
| 의존성 psycopg[binary]·pgvector·chromadb | ✅ pyproject | — |
| pgvector 통합테스트(testcontainers) | ✅ `pgvector_integration` 마커 | tests |

→ **남은 일은 인프라 프로비저닝 + 실 Postgres 연결 + 적재/검증 + 컨테이너화/배포**(DevOps).
→ 선택: 안정화 후 `ChromaAdapter`·chromadb 의존 제거(원래 폐기 계획). 데모 기간엔 폴백으로 잔존 가능.

**예외 — Track C 로컬 검증에서 발견·수정한 코드 1건**: `app/shared/tools/dispatcher.py` 의 에이전트 `search_terms` 도구가 `search_service.similarity_search`(Chroma 전용)를 직접 호출 → pgvector 모드에서 빈 결과. `get_vector_store().query()`(어댑터 경유)로 교체해 backend 무관 동작. *(같은 이유로 `ica search` CLI 도 pgvector 모드에서 Chroma 를 쳐서 0건 — dev 도구라 후속 정리)*

## 7. 비용 개요 (Korea Central, 고정비 — 정확 견적은 SKU 확정 후)

- VM B4ms + Premium 디스크 / Postgres Flexible B2s / Blob(수백 MB) / ACR Basic / egress(Upstage 호출·소량).
- 전부 고정 SKU라 **월 비용 예측 용이**. 비용 드라이버: VM > Postgres > 나머지. 데모 종료 시 VM/DB stop 으로 절감.

## 8. 작업 분해 (배포 스프린트)

> 성격: **DevOps/통합 스프린트** (Python 신규 구현 최소). 트랙 A~D, A→C 순서 의존.

### Track A — Azure 프로비저닝
- **A1** 리소스그룹(Korea Central) + 네이밍/태그 + (선택)Bicep/Terraform IaC.
- **A2** Postgres Flexible(B2s) 생성 → `azure.extensions=VECTOR` 파라미터 → DB·롤 생성 → 방화벽(VM IP)+SSL강제. *(함정 §5.1)*
- **A3** Storage 계정 + 프라이빗 컨테이너(약관 PDF 업로드) + Managed Identity/SAS.
- **A4** ACR Basic + Key Vault(UPSTAGE_API_KEY·JWT_SECRET·DATABASE_URL).
- **A5** VM(B4ms Ubuntu) + Docker/compose + 방화벽(22/80/443) + 고정 공인IP·DNS.

### Track B — 컨테이너화 & compose
- **B1** 백엔드 Dockerfile (uv 멀티스테이지, uvicorn, `/health`).
- **B2** 프론트 빌드 → nginx 이미지: `dist` 정적 + `/api` 리버스프록시 + **DNS resolver 스케일 패턴** + TLS. *(함정 §5.2)*
- **B3** `docker-compose.yml`: nginx + backend(×3) + certbot, `env_file`, healthcheck, `restart: unless-stopped`.
- **B4** nginx LB 분산 검증(3 replica 라운드로빈 실증).

### Track C — pgvector 전환·검증 (코드 거의 없음)
- **C1** `DATABASE_URL=postgresql+psycopg://…` + `vector_store=pgvector` 로 `alembic upgrade head` (전 리비전 fresh PG 통과). *(함정 §5.3)*
- **C2** Blob 약관 PDF로 `ica ingest` 재적재 → 2189청크 + 4096 임베딩. `ica seed-demo`.
- **C3** `ica verify`(카운트 일치/dim 4096/exact 검색) + 라이브 검색·에이전트 라운드트립(롯데 포함 5사 조 인용).
- **C4** `pgvector_integration` 테스트 CI 회귀(Chroma 대비 top-8 동등성 ≥7/8).

### Track D — CI/CD & 운영
- **D1** GitHub Actions: backend·nginx 이미지 빌드→ACR 푸시→VM SSH `compose pull && up -d`.
- **D2** 시크릿 흐름(Key Vault→`.env`) + TLS 자동갱신 cron.
- **D3** 관측(App Insights/Log Analytics) + Postgres 자동백업 확인 + 롤백 절차(이전 이미지 태그).
- **D4** 스모크/런북(`/health`, demo-login→실손 조회→에이전트 인용) + 장애 대응 메모.

### 잔여 결정 (권장값으로 진행 가능)
- 네트워크: Postgres 공용+방화벽+SSL(데모) ↔ VNet 프라이빗 엔드포인트(운영) — **데모는 공용+방화벽**.
- IaC: 포털 수동(빠름) ↔ Bicep/Terraform(재현성) — **A1에서 택1**.
- ChromaAdapter 제거 시점: 데모 후.

## 9. 검증 완료 기준
1. `https://<도메인>` 프론트 로드 + TLS 유효, `/api/v1` 200.
2. `ica verify` on Azure PG: 5문서·2189=2189·dim 4096·exact 검색 통과.
3. 라이브: demo-login(롯데 페르소나 p02)→실손 조회→에이전트가 롯데 약관 조 인용.
4. nginx 3 replica 분산 확인, 1개 죽여도 무중단.
5. GitHub push→자동 배포 1회 성공 + 롤백 1회 성공.
6. pytest 회귀 0(pgvector 통합테스트 포함), ruff 0.

## 10. 환경 분리 & CI/CD (확정 — VM 2대 완전 격리)

GitFlow 브랜치 → 환경 자동 배포. dev/prod 를 **별도 VM + 별도 Azure Postgres** 로 완전 격리(장애 전파 없음).

```
git push dev   ──GitHub Actions──►  [dev VM]   nginx→backend(1) → dev Postgres
git push main  ──GitHub Actions──►  [prod VM]  nginx→backend(1) → prod Postgres
                                     (prod 는 수동 승인 게이트 권장)
         공유: ACR(이미지 레지스트리) · 이미지 태그 <branch>-<sha>
```

**산출물(작성 완료)**
- `.github/workflows/deploy.yml` — `on: push [main,dev]` → 브랜치로 GitHub Environment(prod/dev) 선택 → 이미지 빌드·ACR 푸시 → 대상 VM SSH `compose pull && up -d`. migrate 가 배포마다 `alembic upgrade head` + seed.
- `docker-compose.prod.yml` — 로컬 postgres 제거(관리형 Azure PG), 이미지를 ACR 에서 pull, 백엔드 1 replica(§5.7 세션).

**환경별 GitHub Environment 시크릿** (Track A 후 등록): `ACR_LOGIN_SERVER/USERNAME/PASSWORD`, `VM_HOST/USER/SSH_KEY`, `DATABASE_URL`(환경별 Azure PG), `UPSTAGE_API_KEY`, `JWT_SECRET_KEY`, `PUBLIC_ORIGIN`.

**선행(Track A)**: dev/prod VM 2대(docker+compose, `/opt/ica/docker-compose.prod.yml` 배치) + Azure Postgres 2개(dev/prod) + ACR 1개. **워크플로/compose 는 준비됨 — VM·시크릿만 채우면 동작**.

**남은 항목**: 운영 도메인 + nginx TLS(certbot, 443) — Track D2.

## 11. 채택 구성 — 1환경 올인원 (비용 최소, 실제 배포본)

위 2-VM·관리형 PG 설계는 "정석"이나, **워크로드가 가볍고(외부 AI) 코퍼스 2188청크라** 대회 데모엔 과사양 → **VM 1대 올인원**으로 축소 채택.

| 항목 | 2-VM 설계(참고) | **올인원 채택** |
|:--|:--|:--|
| VM | B4ms ×2 | **B2s ×1** (2vCPU/4GB) |
| Postgres | 관리형 ×2 | **컨테이너 pgvector ×1** (VM 내, 볼륨 영속) |
| 환경 | dev/prod 격리 | **1환경** (main → VM) |
| 백엔드 replica | sticky/Redis 필요 | **1** (세션 affinity 이슈 없음) |
| 월 비용 | ~$370 | **~$35** (끄면 ~$2) |

- 산출물: `infra/azure/{vars,provision,set-github-secrets}.sh` + `cloud-init.yaml` + `docker-compose.prod.yml`(postgres 컨테이너 포함) + `.github/workflows/deploy.yml`(main 트리거).
- 비용 킬러: 데모 때만 켜고 평소 `az vm deallocate` → 컴퓨팅 과금 ~0.
- 확장 필요 시: 2-VM·관리형 PG 설계(§1~10)로 승급 — 어댑터/마이그레이션 동일(코드 무변경).
