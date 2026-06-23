# 보험청구심사 어시스턴트

RAG(약관 검색) 기반으로 보험 청구 가능성을 어시스턴트 톤으로 안내하는 대국민 서비스 도구입니다.

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 🚀 처음 오셨나요? (START HERE)

**새 세션/합류자는 여기부터.** (Claude에게 "README 먼저 읽고 프로젝트 파악해줘"라고 하면 이 절에서 출발합니다.)

- **무슨 프로젝트?** — 자연어로 보험 청구 상황을 말하면, 가입 약관을 근거로 **「가능성 등급(높음/중간/낮음) + 근거 조항 원문 인용 + 충족/미충족 + 다음 행동」**을 제시하는 **설명가능 뉴로심볼릭 RAG 어시스턴트**. **국내 AI 챔피언 대회 출품작** (팀 디포커스 AI).
- **어디까지 됐나?** — **Sprint 18 완료, 1100+ 테스트.** RAG 3채널(Vector/Graph/Hybrid) + ReAct/LangGraph 에이전트 + pgvector + OCR + 마이데이터/건강보험(더미) + JWT 백엔드 + React 프론트.
- **지금 할 작업은?** — **Sprint 16: 국내 전용 LLM 마이그레이션.** [하드 제약: 제품 전 영역 국내 AI 모델만, OpenAI/Bedrock 배제]
  - **▶ 제일 먼저 = 1a (LLM)** — provider 추상화 + **Upstage Solar** 헤드라인 → 그 다음 **1b 임베딩**(Upstage 4096-d **전체 재인덱싱**) → **1c OCR**(Upstage)

### 📂 문서 지도 (이 순서로 읽으면 빠름)

| 순서 | 문서 | 용도 |
|:--|:--|:--|
| 1 | `CLAUDE.md` | **START HERE** — 작업/진척/시작점 한눈에 (Claude 자동 로드) |
| 2 | `docs/PRD.md` | 제품 정의·14기능·국내전용 LLM 스택·로드맵(1a/1b/1c) |
| 3 | `docs/sprint.md` | "▶ 현재 작업 = Sprint 16" 완료기준+시작점 + 전체 이력 |
| 4 | `docs/context/session_handoff.md` | 최신 인수인계 (확정 결정 + 다음 할 일) |
| 5 | `docs/infra/llm-access.md` | LLM 인프라 접속·키 변수·능력검증 |
| 6 | `docs/pm/23_champion-audit.md` | 전체 코드 감사 (강점/리스크/제안서 정렬) |

> 🔑 비밀키는 `.env`(gitignore)에만. **국내 모델만 사용** — OpenAI/AWS Bedrock 제품 배제(Bedrock=오프라인 eval 대조군만). 확정 결정: 헤드라인 **Upstage Solar** / 임베딩 **Upstage 4096-d**(재인덱싱) / 보조 **EXAONE**.

---

## 이 프로젝트는 뭔가요?

보험금을 청구할 수 있을지 직접 확인하기 어려울 때, 보험사의 약관 PDF를 미리 적재해 두고 "발목 골절로 입원했는데 보험금 받을 수 있나요?" 같은 자연어 질문에 답해 주는 도구입니다.

"된다 / 안된다"를 단정하지 않고, **가능성이 높다 / 중간 / 낮다** 수준으로 판단하면서 근거가 되는 약관 조항을 직접 인용합니다. 사용자가 최종 판단을 직접 내릴 수 있도록 충족 항목과 미충족 항목도 함께 보여줍니다.

---

## 현재 상태 — Sprint 18 완료, 다음 Sprint 16 (국내 전용 LLM 전환)

> **단계**: PoC → 대국민 서비스 전환 + 챔피언 제출 준비. **Sprint 18까지 완료**(건강보험 API 더미 어댑터 + 진료내역 자동 prefill, 1100+ 테스트). 현재 LLM·임베딩·OCR은 OpenAI 기반이며, **다음 작업 Sprint 16에서 국내 AI 모델(Upstage Solar + Upstage 임베딩 + Upstage OCR, 보조 LG EXAONE)로 전환**합니다 — 제품 전 영역 국내 모델만 사용(해외 모델 배제). 상세는 위 [START HERE](#-처음-오셨나요-start-here) 및 `docs/PRD.md`.

| 기능 | 상태 |
|:--|:--|
| 약관 PDF 적재 파이프라인 (ingest) | 완료 |
| 구조 인식 청킹 + 임베딩 | 완료 |
| 약관 검색 CLI (search) | 완료 |
| 적재 현황 조회 / 청크 상세 검수 | 완료 |
| HTTP API — 세션 생성·조회·종료 | 완료 |
| 멀티턴 대화 + 슬롯 추출 (LLM Function Calling) | 완료 |
| 가능성 등급 판단 + 약관 조항 인용 응답 | 완료 |
| CLI `ica chat` (터미널 멀티턴 대화) | 완료 |
| CORS 미들웨어 (브라우저 호출 허용) | 완료 |
| GET /documents/products + /insurers 엔드포인트 | 완료 |
| 웹 UI 사양서 3종 (ui-spec / ui-api-flow / ui-states) | 완료 |
| `frontend/` 폴더 스캐폴드 | 완료 |
| `app/rag/` 도메인 — Vector/Graph/Hybrid Retriever | 완료 |
| Neo4j 그래프 적재 (`ica graph-build`) | 완료 |
| `RAG_MODE` env 토글 (vector / graph / hybrid) | 완료 |
| ReAct 루프 (`RAG_REACT=true`, assessment 모드만) | 완료 |
| graceful fallback (Neo4j 다운 시 vector 자동 전환) | 완료 |
| 인용 카드 PDF 페이지 캡처 렌더 (`app/pdfimage/`) | 완료 |
| "모름" 슬롯 인식 + partial assessment 모드 | 완료 |
| 응답 톤 정책 — 능동적 안내 + 친절체 강제 | 완료 |
| 감사 로그 (`app/audit/` + `audit_log` 테이블) | 완료 |
| PII 마스킹 (`app/security/` + `PiiMaskingFilter`) | 완료 |
| rate limit (slowapi 미들웨어) | 완료 |
| circuit breaker (RAG 호출 보호, pybreaker) | 완료 |
| 면책 강화 (`_DEFAULT_DISCLAIMER` 강화) | 완료 |
| 평가 셋 골격 (`eval/` — 시나리오 4건 + runner) | 완료 |
| Prometheus `/metrics` 엔드포인트 | 완료 |
| PostgreSQL 전환 옵션 (`docker-compose.postgres.yml`) | 완료 |
| **pgvector 어댑터 + HNSW 인덱스** (`app/rag/vectorstore.py`) | **완료 (Sprint 12)** |
| **`VECTOR_STORE` env 토글** (chroma / pgvector / 자동) | **완료 (Sprint 12)** |
| **`ica reindex` — pgvector 재임베딩** | **완료 (Sprint 12)** |
| **LangGraph StateGraph agent backend** (`app/rag/langgraph_agent.py`) | **완료 (Sprint 13)** |
| **`RAG_BACKEND` env 토글** (agentrunner / langgraph) | **완료 (Sprint 13)** |
| **`ica agent-graph` — LangGraph 시각화 CLI** | **완료 (Sprint 13)** |
| **OCR 서류 업로드** (`POST /sessions/{id}/documents`, multipart) | **완료 (Sprint 15)** |
| **서류 유형 분류 LLM** (5종: 진단서/신고서/청구서/영수증/기타) | **완료 (Sprint 15)** |
| **슬롯 자동 매핑 LLM** (`app/sessions/llm.py` — classify_document + extract_slots_from_document) | **완료 (Sprint 15)** |
| **첨부 파일 24h TTL** (APScheduler + `app/attachments/`) | **완료 (Sprint 15)** |
| **PII 마스킹 — OCR 직후 적용** (LLM 전달 전) | **완료 (Sprint 15)** |
| 데모용 채팅 UI 구현 | 사용자 영역 (Claude 디자인 서비스) |

---

## 주요 기능

- **약관 PDF 적재**: 보험사 약관 PDF를 폴더에 넣으면 자동으로 파싱·청킹·임베딩해서 벡터 DB에 저장합니다
- **구조 인식 청킹**: "제N조" / 항 / 표 단위로 의미를 유지하며 분할합니다. 단순 토큰 절단으로 인한 면책 조건 누락을 방지합니다
- **약관 검색**: 자연어 질의로 관련 조항 상위 N개를 즉시 반환합니다 (RAG 파이프라인 검증용)
- **적재 현황 관리**: 보험사·상품·버전·문서·청크 단위로 현황을 조회하고 청킹 품질을 검수합니다
- **멀티턴 대화**: "발목 골절로 입원했는데 보험금 받을 수 있나요?" 같은 자연어 질문으로 시작하면, 어시스턴트가 부족한 정보를 단계적으로 수집하고 충분해지면 가능성 판단을 내립니다
- **가능성 판단 + 조항 인용**: 높음/중간/낮음 등급과 함께 판단 근거가 된 약관 조항 원문을 직접 인용합니다. 출처 없는 단정을 하지 않습니다

---

## 기술 스택

| 분류 | 기술 | 역할 |
|:--|:--|:--|
| 언어 | Python 3.11+ | 전체 백엔드 |
| HTTP 프레임워크 | FastAPI 0.110+ | REST API (Sprint 2부터 본격 사용) |
| CLI | Typer + Rich | 데이터 파이프라인 명령어 도구 |
| 메타데이터 DB | SQLite / PostgreSQL (선택) (SQLAlchemy + Alembic) | 보험사·상품·문서·청크·감사로그 관리. `DATABASE_URL` 로 전환 |
| 벡터 DB | Chroma (로컬 영속화) / pgvector (Sprint 12, 운영 권장) | 청크 임베딩 저장 + 유사도 검색. `VECTOR_STORE` env로 선택 |
| 그래프 DB | Neo4j 5.x community (Docker) | 약관 계층 그래프 저장 + Cypher 검색 (Sprint 4부터) |
| AI 프레임워크 | LangChain (app/rag/ 안에서만) | GraphCypherQAChain, langchain-neo4j 활용 |
| LLM / 임베딩 | OpenAI gpt-4o-mini / text-embedding-3-small | 임베딩 생성, 응답 생성 (Sprint 2부터) |
| PDF 파서 | pdfplumber + PyMuPDF | 텍스트 추출 + 표 구조 파싱 + 페이지 이미지 변환 |
| 설정 관리 | pydantic-settings | `.env` 파일 기반 환경 변수 |
| rate limit | slowapi | per-IP / per-session 요청 한도 (Sprint 8부터) |
| circuit breaker | pybreaker | RAG 호출 장애 자동 우회 (Sprint 8부터) |
| 모니터링 | prometheus_client | `/metrics` 엔드포인트 (Sprint 8부터) |

---

## 시작하기

### 필요한 것

- Python 3.11 이상
- OpenAI API 키 ([platform.openai.com](https://platform.openai.com) 에서 발급)

### 1단계: 가상 환경 생성 및 패키지 설치

```bash
# 프로젝트 루트에서 실행
python -m venv .venv

# 가상 환경 활성화 (macOS / Linux)
source .venv/bin/activate

# 가상 환경 활성화 (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 패키지 설치 (편집 가능 모드)
pip install -e .
```

### 2단계: 환경 변수 설정

```bash
# .env.example 을 복사해서 .env 파일 생성
cp .env.example .env
```

`.env` 파일을 열고 `OPENAI_API_KEY` 에 발급받은 키를 입력합니다:

```
OPENAI_API_KEY=sk-...
```

나머지 항목은 기본값으로 동작합니다. 경로를 바꾸고 싶을 때만 수정하세요.

### 3단계: DB 초기화

```bash
alembic upgrade head
```

프로젝트 루트에 `app.db` (SQLite) 파일이 생성됩니다.

### 4단계: PDF 파일 배치

약관 PDF를 아래 규칙에 맞는 경로에 넣어 주세요.

```
data/raw/<보험사 코드>/<영역 코드>/<상품 코드>/<판매기간>/<문서종류>.pdf
```

**예시**:

```
data/raw/
  hanwha/
    auto/
      personal_auto_joint/
        2026-03-01_present/
          summary.pdf      ← 상품요약
          business.pdf     ← 사업방법
          terms.pdf        ← 약관확인
  samsung/
    accident_disease/
      long_term_health/
        2025-07-01_present/
          summary.pdf
          terms.pdf
```

**코드 규칙 (모두 영문 소문자 + 언더스코어)**:

| 항목 | 코드 | 설명 |
|:--|:--|:--|
| 영역 코드 (area) | `auto` | 자동차보험 |
| 영역 코드 (area) | `accident_disease` | 상해·질병(장기보험) |
| 영역 코드 (area) | `fire` | 화재보험 |
| 문서종류 (doc_type) | `summary` | 상품요약서 |
| 문서종류 (doc_type) | `business` | 사업방법서 |
| 문서종류 (doc_type) | `terms` | 약관확인서 |
| 보험사 코드 (insurer) | 자유 지정 | 예: `hanwha`, `samsung`, `kb` |
| 상품 코드 (product) | 자유 지정 | 예: `personal_auto_joint` |
| 판매기간 (version) | `YYYY-MM-DD_present` 또는 `YYYY-MM-DD_YYYY-MM-DD` | 현재 판매 중이면 `present` 사용 |

한글 이름(보험사명, 상품명)은 적재 시 메타데이터로 자동 등록됩니다. 폴더명에는 영문 코드만 사용하세요.

### 5단계: PDF 적재

```bash
ica ingest
```

전체 `data/raw/` 폴더를 스캔해서 PDF를 파싱·청킹·임베딩한 뒤 DB에 저장합니다.

처음 실행하면 OpenAI API 를 호출해서 임베딩을 생성하므로 PDF 수에 따라 수 분이 걸릴 수 있습니다. 이후에는 SHA-256 해시로 변경 여부를 확인해서 변경된 파일만 재처리합니다.

```bash
# 특정 보험사만 적재
ica ingest --insurer hanwha

# 특정 영역만 적재
ica ingest --area auto

# 실제 적재 없이 처리 대상만 미리 확인
ica ingest --dry-run
```

### 6단계: 검색으로 동작 확인

```bash
ica search "발목 골절 입원 보험금"
```

### 7단계: HTTP API 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

서버가 실행되면 `http://localhost:8000/api/v1` 에서 API를 사용할 수 있습니다.
Swagger UI: `http://localhost:8000/docs`

터미널 대화는 서버 없이 바로 사용할 수 있습니다:

```bash
ica chat
```

세션 API 사용 방법: [`docs/usage_sessions.md`](docs/usage_sessions.md)

### (선택) Neo4j 실행 — graph / hybrid 모드 사용 시

`vector` 모드만 쓸 예정이라면 이 단계를 건너뛰어도 됩니다. `graph` 또는 `hybrid` 모드를 사용하려면 Docker 가 필요합니다.

```bash
# Neo4j 컨테이너 실행
docker compose -f docker-compose.neo4j.yml up -d

# Neo4j 에 약관 그래프 적재 (최초 1회)
ica graph-build

# hybrid 모드로 서버 실행
RAG_MODE=hybrid uvicorn app.main:app --reload --port 8000
```

Neo4j Browser: `http://localhost:7474`

GraphRAG 상세 안내: [`docs/usage_graphrag.md`](docs/usage_graphrag.md)

---

## CLI 명령 전체 목록

### `ica ingest` — PDF 적재

`data/raw/` 폴더를 스캔해서 신규·변경된 PDF를 파싱·청킹·임베딩합니다. 멱등 동작(같은 파일을 두 번 실행해도 결과가 동일합니다).

```bash
ica ingest [--insurer <코드>] [--area <코드>] [--dry-run] [--force]
```

| 옵션 | 기본값 | 설명 |
|:--|:--|:--|
| `--insurer` | (전체) | 특정 보험사만 처리. 예: `hanwha` |
| `--area` | (전체) | 특정 영역만 처리. `auto` / `accident_disease` / `fire` |
| `--dry-run` | False | 실제 적재 없이 처리 대상 목록만 출력 |
| `--force` | False | 해시가 동일해도 강제 재처리 |

### `ica search` — 약관 검색

자연어 질의를 임베딩해서 가장 관련 있는 약관 청크를 반환합니다. RAG 파이프라인 동작 확인용입니다.

```bash
ica search "질의문" [--top-k 8] [--insurer <코드>] [--area <코드>] [--product <코드>] [--doc-type <종류>]
```

```bash
# 예시
ica search "입원의료비 보장 한도"
ica search "면책 사항 자해" --insurer hanwha --area accident_disease
ica search "대물배상 한도" --top-k 5 --doc-type terms
```

| 옵션 | 기본값 | 설명 |
|:--|:--|:--|
| `--top-k` | 8 | 반환할 결과 개수 |
| `--insurer` | (전체) | 보험사 필터 |
| `--area` | (전체) | 영역 필터 |
| `--product` | (전체) | 상품 필터 |
| `--doc-type` | (전체) | 문서종류 필터. `summary` / `business` / `terms` |

### `ica list` — 적재 현황 조회

DB에 적재된 데이터를 범위별로 조회합니다.

```bash
ica list [--scope <범위>] [--insurer <코드>] [--area <코드>]
```

```bash
# 예시
ica list                          # 상품 목록 (기본)
ica list --scope insurers         # 보험사 목록
ica list --scope chunks           # 청크 수 (SQLite ↔ Chroma 정합성 포함)
ica list --scope versions --product personal_auto_joint
```

| `--scope` 값 | 설명 |
|:--|:--|
| `products` | 상품 목록 (기본값) |
| `insurers` | 보험사 목록 |
| `versions` | 판매기간 버전 목록 (`--product` 필수) |
| `documents` | 등록된 문서 수 |
| `chunks` | 청크 수 (SQLite / Chroma 각각 표시) |

### `ica inspect` — 청크 상세 조회

특정 청크의 본문, 메타데이터, 부모 조항, 형제 조항을 출력합니다. 청킹 품질을 수동으로 검수할 때 사용합니다.

```bash
ica inspect <청크 UUID> [--show-parent] [--show-siblings]
```

```bash
# 예시 (청크 ID 는 ica search 결과에서 확인 가능)
ica inspect 3f8a1c2e-4b5d-...
ica inspect 3f8a1c2e-4b5d-... --show-parent --show-siblings
```

### `ica rebuild` — 강제 재처리

파서 버전 업그레이드 등으로 모든 데이터를 다시 처리해야 할 때 사용합니다. `ica ingest --force` 와 동일하게 동작하되 필터를 적용할 수 있습니다.

```bash
ica rebuild [--insurer <코드>] [--area <코드>]
```

```bash
# 예시
ica rebuild
ica rebuild --insurer hanwha
```

### `ica chat` — 멀티턴 대화

터미널에서 어시스턴트와 직접 대화합니다. HTTP 서버 없이 서비스 레이어를 직접 호출합니다.

```bash
ica chat
```

자연어로 보험 청구 시나리오를 입력하면 어시스턴트가 부족한 정보를 질문으로 보강하고, 충분해지면 가능성 등급 + 약관 조항 인용 응답을 제공합니다.

`/quit` 또는 `Ctrl+C` 로 종료합니다. 종료 시 세션이 자동으로 폐기됩니다.

---

## 환경 변수

`.env` 파일 (`.env.example` 복사해서 사용)

| 변수명 | 기본값 | 필수 | 설명 |
|:--|:--|:--|:--|
| `OPENAI_API_KEY` | (없음) | **O** | OpenAI API 키. LLM + 임베딩 공용 |
| `LLM_MODEL` | `gpt-4o-mini` | X | 응답 생성용 모델 (Sprint 2부터 사용) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | X | 임베딩 모델 |
| `SQLITE_DB_PATH` | `./app.db` | X | SQLite DB 파일 경로. `DATABASE_URL` 설정 시 무시됨 |
| `CHROMA_DB_PATH` | `./chroma_db` | X | Chroma 벡터 DB 폴더 경로. `VECTOR_STORE=pgvector` 사용 시 무시됨 |
| `VECTOR_STORE` | (없음 — 자동) | X | 벡터 DB backend. `chroma` / `pgvector` / 빈 값(자동). `DATABASE_URL`이 PostgreSQL이면 pgvector 자동 선택 (Sprint 12) |
| `RAW_DATA_PATH` | `./data/raw` | X | 원본 PDF 폴더 경로 |
| `SESSION_TTL_SECONDS` | `1800` | X | 대화 세션 유지 시간(초). Sprint 2부터 사용 |
| `LOG_LEVEL` | `INFO` | X | 로그 레벨. `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `NEO4J_URI` | `bolt://localhost:7687` | X | Neo4j Bolt 주소. graph/hybrid 모드 시 필요 |
| `NEO4J_USERNAME` | `neo4j` | X | Neo4j 사용자 이름 |
| `NEO4J_PASSWORD` | (없음) | X | Neo4j 비밀번호. graph/hybrid 모드 시 필요 |
| `RAG_MODE` | `vector` | X | 검색 채널. `vector` / `graph` / `hybrid` |
| `RAG_REACT` | `false` | X | ReAct 루프. `true` 시 비용 ~2.5배. assessment 모드만 적용 |
| `RAG_BACKEND` | `agentrunner` | X | ReAct 활성(`RAG_REACT=true`) 시 사용할 agent backend. `agentrunner` (Sprint 11) / `langgraph` (Sprint 13) |
| (`page_images_path`) | `./data/page_images` | — | PDF 페이지 캡처 캐시 경로. `Settings.page_images_path` 기본값 그대로 사용. 별도 환경 변수 불필요 |
| `DATABASE_URL` | (없음) | X | DB 연결 URL. 빈 값이면 SQLite 사용. PostgreSQL 예: `postgresql+psycopg://ica:pw@localhost:5433/ica_db` |
| `RATE_LIMIT_ENABLED` | `true` | X | slowapi rate limit 활성화. 테스트 환경은 `false` |
| `RATE_LIMIT_PER_IP` | `10/minute` | X | IP당 분당 최대 요청 수 |
| `RATE_LIMIT_PER_SESSION` | `30/minute` | X | 세션당 분당 최대 요청 수 |
| `CIRCUIT_BREAKER_FAIL_MAX` | `5` | X | 연속 실패 횟수. 초과 시 circuit open |
| `CIRCUIT_BREAKER_RESET_SECONDS` | `60` | X | circuit open 후 자동 복구까지 대기 시간(초) |
| `AUDIT_ENABLED` | `true` | X | 감사 로그 기록 활성화. 테스트 환경은 `false` |
| `PII_MASKING_ENABLED` | `true` | X | 로그·감사 기록 시 PII 마스킹. 테스트 환경은 `false` |
| `PROMETHEUS_ENABLED` | `true` | X | `/metrics` 엔드포인트 노출 여부 |
| `OCR_BACKEND` | `openai` | X | OCR 엔진. `openai` (기본, gpt-4o-mini Vision) / `upstage` (Sprint 16 예정) |
| `ATTACHMENT_STORAGE_PATH` | `./data/uploads` | X | 업로드 파일 임시 저장 경로. 24h TTL 적용 |
| `ATTACHMENT_TTL_HOURS` | `24` | X | 첨부 파일 자동 삭제 기준 시간(시). 0이면 자동 삭제 비활성 |
| `ATTACHMENT_MAX_SIZE_MB` | `10` | X | 업로드 허용 최대 파일 크기(MB) |

---

## 프론트엔드

### 역할 분담

Sprint 3 에서 채팅 웹 UI 구현은 **사용자가 Claude 디자인 서비스로 직접 진행**한다. PM(Claude Code)은 아래 3가지까지만 책임진다.

1. 백엔드 정비 (CORS 미들웨어 + documents 엔드포인트 추가)
2. `frontend/` 폴더 스캐폴드 (작업 공간 + README)
3. 사양서 3종 작성 (Claude 디자인 서비스 입력으로 사용)

### `frontend/` 폴더

Claude 디자인 산출물(컴포넌트, 빌드 설정 등)을 배치할 빈 자리다. 상세 안내는 [`frontend/README.md`](frontend/README.md) 참조.

### 사양서 3종

| 문서 | 역할 |
|:--|:--|
| [`docs/design/ui-spec.md`](docs/design/ui-spec.md) | 화면 명세 + 컴포넌트 분해 + props/state + 와이어프레임 |
| [`docs/design/ui-api-flow.md`](docs/design/ui-api-flow.md) | API 호출 시퀀스 + TypeScript 타입 정의 + fetch 헬퍼 |
| [`docs/design/ui-states.md`](docs/design/ui-states.md) | 에러 / 로딩 / 빈 상태 UX 패턴 |

Claude 디자인 서비스에 위 문서를 입력으로 주면 컴포넌트 코드를 생성한다. 분량이 길면 `ui-spec.md` 부터 시작해서 문서별로 순차 입력한다.

### 로컬 실행 (UI 포함)

백엔드와 프론트엔드를 터미널 2개에서 각각 실행한다.

```bash
# 터미널 1 — 백엔드
uvicorn app.main:app --reload --port 8000

# 터미널 2 — 프론트엔드 (Claude 디자인 산출물 배치 후)
cd frontend
npm install
npm run dev   # 기본 http://localhost:5173
```

CORS 화이트리스트는 `http://localhost:5173`, `http://localhost:3000` 으로 설정되어 있다. 다른 포트를 사용하려면 `.env` 에 `CORS_ALLOW_ORIGINS=http://localhost:<포트>` 를 추가한다.

---

## 프로젝트 구조

```
insurance-claim-assistant/
├── app/                        # 메인 패키지
│   ├── main.py                 # FastAPI 앱 진입점. /api/v1 라우터 등록
│   ├── __main__.py             # python -m app 진입점
│   ├── core/                   # 공통 인프라 (DB, 설정, 로깅, 예외)
│   │   ├── config.py           # 환경 변수 기반 설정 (pydantic-settings)
│   │   ├── database.py         # SQLAlchemy 세션 관리
│   │   ├── exceptions.py       # 공통 예외 클래스
│   │   └── logging.py          # 로거 팩토리
│   ├── documents/              # 보험사·상품·버전·문서 도메인
│   │   ├── models.py           # SQLAlchemy ORM 모델
│   │   ├── schemas.py          # Pydantic 스키마
│   │   ├── crud.py             # DB CRUD
│   │   ├── service.py          # 비즈니스 로직
│   │   └── router.py           # FastAPI 라우터
│   ├── chunks/                 # 청크 파싱·저장 도메인
│   │   ├── models.py           # clause_chunks ORM 모델
│   │   ├── schemas.py          # Pydantic 스키마
│   │   ├── crud.py             # DB CRUD
│   │   ├── service.py          # 청크 관련 서비스
│   │   ├── parser.py           # PDF 파서 (pdfplumber + PyMuPDF)
│   │   ├── chunker.py          # 구조 인식 청킹 로직
│   │   ├── structure.py        # 조항 구조 인식 (정규식 + 휴리스틱)
│   │   └── router.py           # FastAPI 라우터
│   ├── embeddings/             # 임베딩 생성 도메인
│   │   ├── schemas.py          # 임베딩 관련 스키마
│   │   └── service.py          # OpenAI 임베딩 호출
│   ├── search/                 # 벡터 검색 도메인
│   │   ├── schemas.py          # 검색 필터·결과 스키마
│   │   ├── service.py          # Chroma 유사도 검색
│   │   └── router.py           # FastAPI 라우터
│   ├── ingestion/              # 적재 파이프라인 오케스트레이션
│   │   ├── schemas.py          # 적재 작업 스키마
│   │   └── service.py          # 폴더 스캔 + 적재 흐름 조율
│   ├── sessions/               # 멀티턴 대화 세션 도메인 (Sprint 2)
│   │   ├── schemas.py          # Session·SlotState·응답 스키마
│   │   ├── service.py          # 세션 생성·메시지 처리·슬롯 추출
│   │   ├── store.py            # 인메모리 세션 저장소 (TTL 포함)
│   │   ├── llm.py              # OpenAI Function Calling 래퍼
│   │   └── router.py           # FastAPI 라우터 (POST/GET/DELETE /sessions)
│   ├── rag/                    # GraphRAG + Agent 도메인 (Sprint 4, 11, 13)
│   │   ├── service.py          # retrieve() + run_agent / run_agent_langgraph 진입점
│   │   ├── protocols.py        # Retriever 공통 인터페이스
│   │   ├── vector.py           # VectorRetriever (Chroma)
│   │   ├── graph.py            # GraphRetriever (Neo4j + LangChain)
│   │   ├── hybrid.py           # HybridRetriever (vector + graph 합성)
│   │   ├── react.py            # ReActRunner (opt-in, assessment 모드만)
│   │   ├── agent.py            # AgentRunner — Sprint 11 자체 구현 (Sprint 14~15 폐기 예정)
│   │   ├── langgraph_agent.py  # LangGraph StateGraph agent (Sprint 13 신규)
│   │   ├── vectorstore.py      # VectorStoreAdapter (Chroma / pgvector — Sprint 12)
│   │   ├── indexer.py          # build_graph() — SQLite → Neo4j 변환
│   │   └── prompts.py          # Cypher few-shot + ReAct 프롬프트
│   ├── pdfimage/               # PDF 페이지 캡처 도메인 (Sprint 5)
│   │   └── service.py          # PyMuPDF lazy 변환 + 디스크 캐시 + URL 헬퍼
│   ├── audit/                  # 감사 로그 도메인 (Sprint 8)
│   │   ├── models.py           # AuditLog SQLAlchemy 모델 (audit_log 테이블)
│   │   └── service.py          # begin/complete/fail — try/finally 결합
│   ├── security/               # 보안 도메인 (Sprint 8)
│   │   └── pii.py              # PII 마스킹 (주민번호·전화·계좌·이메일) + PiiMaskingFilter
│   ├── attachments/            # 첨부 파일 도메인 (Sprint 15)
│   │   ├── schemas.py          # AttachmentMeta 스키마
│   │   └── service.py          # 저장/조회/삭제 + cleanup_expired (24h TTL)
│   ├── external/               # 외부 API 어댑터 (Sprint 9~15)
│   │   ├── ocr/                # OCR 어댑터 (Sprint 15)
│   │   │   └── adapter.py      # OcrAdapter Protocol + OpenAiVisionAdapter + UpstageAdapter(skeleton)
│   │   ├── law/                # 법령정보센터
│   │   ├── hira/               # HIRA 진단코드
│   │   ├── kidi/               # 손보협회 과실비율
│   │   └── fss/                # 금감원 공시 (Sprint 10)
│   └── cli/
│       └── app.py              # Typer CLI 진입점 (ica 명령)
├── eval/                       # 평가 셋 (Sprint 8)
│   ├── scenarios/              # 시나리오 JSON 파일 (초기 4건)
│   └── runner.py               # 시나리오 실행 + 결과 비교 (python -m eval.runner)
├── alembic/                    # DB 마이그레이션
│   ├── env.py                  # Alembic 환경 설정
│   ├── versions/               # 마이그레이션 파일 (afc2f2f931bf: audit_log 추가)
│   └── script.py.mako
├── alembic.ini                 # Alembic 설정
├── data/
│   ├── raw/                    # 원본 PDF 폴더 (gitignore)
│   │   └── <insurer>/<area>/<product>/<version>/<doc_type>.pdf
│   ├── page_images/            # PDF 페이지 캡처 캐시 (Sprint 5, gitignore)
│   │   └── <document_id>/<page:04d>.png
│   ├── uploads/                # 업로드 첨부 파일 임시 저장 (Sprint 15, gitignore)
│   │   └── <session_id>/<uuid>.{jpg|png|pdf}   ← 24h TTL 후 자동 삭제
│   └── (chroma_db/, app.db 는 실행 후 자동 생성)
├── docs/                       # 설계·요구사항 문서
│   ├── requirements/           # 요구사항
│   └── design/                 # 기술 결정·데이터 모델·API 명세·UI 사양서
├── frontend/                   # 웹 UI 작업 공간 (Claude 디자인 산출물 배치)
│   └── README.md               # 시작 가이드 + 검증 체크리스트
├── tests/                      # 테스트
├── docker-compose.neo4j.yml    # Neo4j 컨테이너 (graph/hybrid 모드 시 필요)
├── docker-compose.postgres.yml # PostgreSQL 컨테이너 (운영 DB 전환 시)
├── .env.example                # 환경 변수 템플릿
├── pyproject.toml              # 프로젝트 메타데이터 + 의존성
└── README.md
```

---

## 도메인 응집 구조

각 도메인 폴더(`documents/`, `chunks/`, `embeddings/`, `search/`, `ingestion/`)는 다음 파일 패턴을 따릅니다:

| 파일 | 역할 |
|:--|:--|
| `models.py` | SQLAlchemy ORM 테이블 정의 |
| `schemas.py` | Pydantic 요청·응답·내부 스키마 |
| `crud.py` | DB 읽기·쓰기 함수 (순수 DB 작업만) |
| `service.py` | 비즈니스 로직 (crud 와 외부 의존성 조합) |
| `router.py` | FastAPI 엔드포인트 (Sprint 2부터 본격 사용) |

호출 방향: `router → service → crud → models`. 반대 방향이나 계층 건너뛰기는 하지 않습니다. 다른 도메인 코드가 필요할 때는 `service` 레벨에서만 import 합니다.

---

## 개발 가이드

### 개발용 추가 패키지 설치

```bash
pip install -e ".[dev]"
```

### 린터 / 포매터 실행

```bash
ruff check app/
ruff format app/
```

### 타입 검사

```bash
mypy app/
```

### 테스트 실행

```bash
pytest
pytest --cov=app
```

### DB 마이그레이션 추가 (모델 변경 시)

```bash
alembic revision --autogenerate -m "변경 내용 설명"
alembic upgrade head
```

---

## GraphRAG 채널 선택

Sprint 4 에서 검색 채널이 3가지로 늘었습니다. 환경변수 `RAG_MODE` 로 선택합니다.

| RAG_MODE | 설명 | 권장 상황 |
|:--|:--|:--|
| `vector` | 의미 유사도 검색 (기본값) | Neo4j 없이 바로 시작. 회귀 0 보장 |
| `graph` | Neo4j Cypher 쿼리 자동 생성 | 조항 계층·참조 관계 추적 |
| `hybrid` | vector + graph 결과 합성 | 정확도 최대화 (권장) |

```bash
# hybrid 모드로 실행하는 예시
RAG_MODE=hybrid uvicorn app.main:app --reload --port 8000
```

상세 안내 (빠른 시작, 환경변수, 트러블슈팅): [`docs/usage_graphrag.md`](docs/usage_graphrag.md)

---

## 인용 카드 — PDF 페이지 캡처

Sprint 5에서 assessment 응답의 각 인용 카드에 약관 PDF 해당 페이지 이미지가 함께 표시됩니다.

### 동작 방식

- assessment 응답이 생성되면 인용된 청크의 PDF 페이지를 이미지로 변환해서 인용 카드에 바로 노출합니다.
- 이미지를 클릭하면 원본 PDF 가 새 탭에서 열리면서 해당 페이지로 바로 이동합니다 (`#page=N` 점프).
- **LLM 이 관여하지 않습니다.** 서버가 `chunk_id → document_id → file_path` 를 추적해서 URL 을 직접 주입합니다. 환각이 발생하지 않습니다.

### 캐시 정책

첫 번째 요청 시점에 PyMuPDF 로 페이지를 변환해서 디스크에 저장합니다. 이후에는 저장된 이미지를 즉시 반환합니다.

```
data/page_images/{document_id}/{page:04d}.png
```

디스크 사용량: 약 20MB (PDF 4개 × 약 50페이지 × 100KB).

### 신뢰성 의미

인용 카드에 약관 원문 페이지 이미지가 동시에 노출되므로, LLM 이 잘못된 조항을 인용했는지 즉시 육안으로 확인할 수 있습니다.

### graceful 처리

PDF 파일이 없거나 변환에 실패하면 `page_image_url` 이 `null` 로 반환됩니다. UI 는 이미지 없이 원문 발췌 텍스트만 표시하며 정상 동작합니다.

---

## 응답 품질 정책 (Sprint 6)

Sprint 6에서 사용자가 보험 가입 정보를 잘 모르거나 무한 질문 루프에 빠지는 상황을 방지하는 정책이 추가되었습니다.

### "모름" 인식

사용자가 "보험사 몰라요", "과실 비율 모르겠어요" 같이 명시적으로 모른다고 답하면 어시스턴트가 이를 인식해서 같은 질문을 반복하지 않습니다. 해당 슬롯은 `SlotState.unknown_slots` 목록에 기록되고 이후 필수 슬롯 계산에서 제외됩니다.

### partial 모드 — "추정" 배지

정보가 충분하지 않더라도 아래 세 조건 중 하나를 충족하면 어시스턴트가 추정 기반 판단을 제공합니다. 응답 카드에 노란색 "(추정)" 배지가 표시됩니다.

| 조건 | 내용 |
|:--|:--|
| unknown_slots ≥ 2 | 사용자가 "모름"을 명시한 슬롯이 2개 이상 |
| ask 횟수 ≥ 3 | 어시스턴트가 이미 3번 이상 추가 정보를 요청한 경우 |
| 명시 키워드 | "그냥", "됐어", "알려줘", "그만", "다 모름" 입력 시 |

- partial 모드도 약관 인용(RAG citation) 최소 1건은 반드시 포함합니다. 검색 결과가 없으면 partial 대신 ask로 분기합니다.
- `AssistantAssessment.confidence` 필드가 `'partial'`일 때 UI에 "(추정)" 배지가 노출됩니다. 기본값은 `'full'`이므로 기존 응답은 변경 없습니다.

상세 안내: [`docs/usage_response_quality.md`](docs/usage_response_quality.md)

---

## 응답 톤 정책 (Sprint 7)

Sprint 7에서 모든 user-facing 응답에 일관된 톤 가이드가 적용되었습니다. 사용자에게 책임을 떠넘기거나 명령형 어조를 쓰는 대신, 시스템이 능동적으로 안내하는 방향으로 바뀌었습니다.

### 톤 4원칙

| 원칙 | 금지 | 권장 |
|:--|:--|:--|
| 능동적 안내 | "다시 확인해 주세요" / "정확히 알려주세요" | "정확한 안내를 위해 ... 정보를 확인하고 싶습니다" |
| 책임 비전가 금지 | "입력 정보가 부족합니다" (사용자 책임) | "현재 정보만으로는 일반적인 약관 기준에 따라 안내드리겠습니다" |
| 정확성·범용성 명시 | (구분 없음) | 정보 충족 → "정확하게 안내드립니다" / 부족 → "일반적인 기준으로 안내드립니다" |
| 친절체 + 존댓말 | 명령형 / 반말 | "~드리겠습니다" / "~주시면 좋겠습니다" / "~안내드립니다" |

### 적용 위치

| 위치 | 변경 내용 |
|:--|:--|
| RAG 0건 응답 (`_build_no_match_ask`) | "다시 확인해 주세요" → "알고 계신 정보가 있다면 알려주시면 정확하게 안내드리겠습니다" |
| 추가 정보 요청 (`_NEXT_QUESTION_SYSTEM`) | 시스템 프롬프트 끝에 "톤 가이드" 절 추가 — 친절체 강제 |
| partial 판단 (`_ASSESSMENT_SYSTEM`) | partial 시 summary 톤 — "정확한 답변에는 ... 현재 정보로 일반적인 약관 기준에 따라 안내드리겠습니다" |

Sprint 6 partial 모드(정보가 있을 때 추정 판단)와 Sprint 7 톤 정책(정보가 없을 때 부드러운 안내)은 보완 관계입니다. citation 없는 답변은 Sprint 6 결정에 따라 여전히 허용되지 않습니다.

상세 안내: [`docs/usage_response_quality.md`](docs/usage_response_quality.md)

---

## 운영 인프라 (Sprint 8)

Sprint 8에서 PoC 단계를 졸업하고 대국민 서비스 운영 기반을 갖췄습니다. 각 기능의 상세 사용법은 [`docs/usage_ops.md`](docs/usage_ops.md) 를 참조하세요.

| 기능 | 모듈 | 한 줄 설명 |
|:--|:--|:--|
| 감사 로그 | `app/audit/` | 모든 응답에 `response_id` + LLM trace + 인용 청크 ID 영구 기록. 분쟁 시 100% 재현 가능 |
| PII 마스킹 | `app/security/pii.py` | 주민번호·전화·계좌·이메일을 로그·감사 기록 전에 자동 마스킹. LLM 입력은 원문 유지 |
| rate limit | slowapi (`app/main.py`) | per-IP 10회/분, per-session 30회/분. `RATE_LIMIT_ENABLED=false` 로 테스트에서 비활성화 |
| circuit breaker | pybreaker (`app/rag/service.py`) | RAG 연속 실패 5회 → 60초 circuit open → vector 폴백. 외부 API 장애가 핵심 서비스로 전파되지 않음 |
| 면책 강화 | `app/sessions/llm.py` | `_DEFAULT_DISCLAIMER` — "참고용" 키워드 포함 + 보험사·손해사정사 문의 안내 |
| 평가 셋 | `eval/` | 시나리오 JSON 4건 + runner. `python -m eval.runner --all` 로 전체 회귀 측정 |
| `/metrics` | `app/main.py` | Prometheus exposition 엔드포인트. `PROMETHEUS_ENABLED=false` 로 비활성화 |
| `DATABASE_URL` | `app/core/database.py` | 비어 있으면 SQLite 사용, 값이 있으면 PostgreSQL 등 지정 DB 사용. 코드 변경 없이 전환 |
| PostgreSQL Docker | `docker-compose.postgres.yml` | `docker compose -f docker-compose.postgres.yml up -d` 로 운영 DB 실행 |

---

## 벡터 DB backend (Sprint 12)

Sprint 12에서 벡터 DB 전환이 시작되었습니다. 기본값은 Chroma이며 `VECTOR_STORE=pgvector`로 pgvector를 활성화할 수 있습니다.

| backend | 설정 | 특징 |
|:--|:--|:--|
| Chroma (기본) | `VECTOR_STORE=chroma` 또는 미설정 | 파일 기반, Docker 불필요. Sprint 13 이후 폐기 예정 |
| pgvector (운영 권장) | `VECTOR_STORE=pgvector` 또는 `DATABASE_URL=postgresql://...` | PostgreSQL 통합, ACID, 백업 통합. `ica reindex` 필요 |

pgvector 활성화 방법 (4단계): [`docs/usage_ops.md § 7`](docs/usage_ops.md)

---

## Agent backend (Sprint 13)

Sprint 13에서 LangGraph StateGraph 기반 agent backend가 추가되었습니다. `RAG_REACT=true` 로 ReAct 모드를 활성화한 뒤 `RAG_BACKEND` 로 구현을 선택합니다.

| backend | env 설정 | 특징 |
|:--|:--|:--|
| AgentRunner (기본) | `RAG_BACKEND=agentrunner` 또는 미설정 | Sprint 11 자체 구현. Sprint 14~15 이후 폐기 예정 |
| LangGraph (Sprint 13) | `RAG_BACKEND=langgraph` | StateGraph 노드/엣지 명시화 + `ica agent-graph` 시각화 지원 |

```bash
# LangGraph backend로 서버 실행
RAG_REACT=true RAG_BACKEND=langgraph uvicorn app.main:app --reload --port 8000

# CLI 대화 (LangGraph backend)
RAG_REACT=true RAG_BACKEND=langgraph ica chat

# LangGraph 노드 구조 시각화 (Mermaid 출력)
ica agent-graph

# 파일로 저장
ica agent-graph --out docs/design/diagrams/langgraph-flow.md
```

상세 안내: [`docs/usage_graphrag.md § 7`](docs/usage_graphrag.md)

---

## OCR 서류 처리 (Sprint 15)

Sprint 15에서 사고 관련 서류를 업로드해 슬롯을 자동 입력하는 기능이 추가되었습니다. 사용자가 병원 진단서, 경찰 신고서, 보험 청구서, 영수증을 이미지(JPEG/PNG/WebP) 또는 PDF로 업로드하면, OpenAI Vision(`gpt-4o-mini multimodal`)이 텍스트를 추출하고 LLM이 서류 유형을 분류해 슬롯을 자동 매핑합니다.

### 5 유형 분류

| doc_type | 한국어 명칭 | 추출 슬롯 |
|:--|:--|:--|
| `diagnosis` | 병원 진단서 | 진단명, 병원명, 치료기간, 입원일수 |
| `police_report` | 경찰 신고서 | 사고일시, 사고유형, 사고장소, 과실비율 |
| `claim_form` | 보험 청구서 | 증권번호 |
| `receipt` | 영수증 | 손해액 |
| `other` | 기타 | 없음 (신뢰도 < 0.7 시 폴백) |

### 빠른 사용 예시

```bash
# 세션 생성 후 서류 업로드
SESSION_ID=$(curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" -d '{}' | jq -r .session_id)

curl -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/documents" \
  -F "file=@diagnosis.jpg;type=image/jpeg"
```

추출된 슬롯은 자동 반영되지 않습니다. 사용자가 UI 확인 카드에서 검토 후 `POST /sessions/{id}/apply-extracted`로 명시 적용합니다.

상세 안내: [`docs/usage_ocr.md`](docs/usage_ocr.md)

---

## 다음 스프린트 안내

**Sprint 16 — 국내 전용 LLM 마이그레이션** (다음 작업, [START HERE](#-처음-오셨나요-start-here) 참조)

제품 전 영역을 국내 AI 모델로 전환합니다(해외 모델 배제). 순서: **1a LLM**(provider 추상화 + Upstage Solar 헤드라인) → **1b 임베딩**(Upstage 4096-d + 전체 재인덱싱 + 벡터 스키마 변경) → **1c OCR**(UpstageAdapter 구현). 확정 결정·완료기준은 `docs/sprint.md` "▶ 현재 작업", `docs/PRD.md` §8.

**Sprint 9 (진행 중) — 외부 read-only tool 다발**

법령·진단코드·표준 과실비율 외부 API를 추가해서 LLM이 약관 검색 외에도 실시간 법령 조항과 의료 코드를 참조할 수 있게 합니다.

| tool | 외부 API | 우선순위 |
|:--|:--|:--|
| `lookup_law_clause` | 국가법령정보센터 OpenAPI (무료) | P0 |
| `get_disease_code` | HIRA 건강보험심사평가원 (공공데이터포털) | P1 |
| `get_fault_ratio_standard` | 손해보험협회 표준 과실비율 (정적 데이터셋) | P2 |

외부 API 명세: [`docs/design/external-apis.md`](docs/design/external-apis.md)

세션 API 사용 방법: [`docs/usage_sessions.md`](docs/usage_sessions.md)

GraphRAG 사용 방법: [`docs/usage_graphrag.md`](docs/usage_graphrag.md)

운영자 가이드: [`docs/usage_ops.md`](docs/usage_ops.md)

API 명세: [`docs/design/api-spec.md`](docs/design/api-spec.md)

웹 UI 사양서: [`docs/design/ui-spec.md`](docs/design/ui-spec.md)

RAG 아키텍처: [`docs/design/rag-architecture.md`](docs/design/rag-architecture.md)

Agent 아키텍처 (Sprint 8~11): [`docs/design/agent-architecture.md`](docs/design/agent-architecture.md)

외부 API 명세 (Sprint 9~10): [`docs/design/external-apis.md`](docs/design/external-apis.md)

---

## 라이선스 및 면책

Sprint 8부터 대국민 서비스 운영 단계로 전환합니다.

**본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.** 보험금 청구 여부의 최종 판단은 해당 보험사 또는 전문 손해사정사에게 문의하시기 바랍니다.

운영자 가이드 (감사 로그 / PII / rate limit / PostgreSQL 전환 / 평가 셋): [`docs/usage_ops.md`](docs/usage_ops.md)
