# 보험청구심사 어시스턴트

가입 약관(RAG 검색)을 근거로 보험 청구 가능성을 **어시스턴트 톤**으로 안내하는 설명가능 뉴로심볼릭 RAG 서비스입니다.

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다. 최종 판단은 해당 보험사 또는 전문 손해사정사에게 문의하시기 바랍니다.

---

## 이 프로젝트는 뭔가요?

보험금을 청구할 수 있을지 직접 확인하기 어려울 때, 보험사의 약관 PDF를 미리 적재해 두고 *"발목 골절로 입원했는데 보험금 받을 수 있나요?"* 같은 자연어 질문에 답해 주는 도구입니다.

"된다/안된다"를 단정하지 않고, **가능성이 높다 / 중간 / 낮다** 수준으로 판단하면서 근거가 되는 **약관 조항 원문을 직접 인용**합니다. 사용자가 최종 판단을 내릴 수 있도록 충족 항목과 미충족 항목, 다음 행동도 함께 보여줍니다.

**3원칙** — ① 단정 금지(어시스턴트 톤) ② 환각 차단(약관 원문 인용 강제) ③ 개인정보 보호(PII 마스킹).
국내 AI 모델(Upstage)만으로 동작하도록 설계되어, 추론·임베딩·OCR 전 영역이 국내 LLM 기반입니다.

---

## 주요 기능

- **약관 PDF 적재**: 보험사 약관 PDF를 폴더에 넣으면 자동으로 파싱·청킹·임베딩해 벡터 DB에 저장
- **구조 인식 청킹**: "제N조"/항/표 단위로 의미를 유지하며 분할 — 토큰 절단으로 인한 면책 조건 누락 방지
- **멀티턴 대화**: 자연어 질문으로 시작하면 부족한 정보를 단계적으로 수집하고, 충분해지면 가능성 판단
- **가능성 판단 + 조항 인용**: 높음/중간/낮음 등급 + 판단 근거 약관 조항 원문 인용 + 충족/미충족 + PDF 페이지 캡처
- **RAG 3채널**: Vector(임베딩) / Graph(Neo4j Cypher) / Hybrid(합성) — `RAG_MODE`로 선택
- **에이전트**: ReAct / LangGraph 기반 도구 호출(법령·진단코드·과실비율·계산기) — `RAG_REACT`로 opt-in
- **OCR 서류 처리**: 진단서·신고서·청구서·영수증 업로드 → 텍스트 추출 + 유형 분류 + 슬롯 자동 매핑
- **운영 기반**: 감사 로그 · PII 마스킹 · rate limit · circuit breaker · `/metrics`(Prometheus)

---

## 기술 스택

| 분류 | 기술 |
|:--|:--|
| 언어 / 프레임워크 | Python 3.11+ · FastAPI · Typer(CLI) |
| 추론 LLM | **Upstage Solar** (`solar-pro2`) — Function Calling + Structured Outputs |
| 임베딩 | **Upstage solar-embedding** (query/passage, 4096-d) |
| OCR | **Upstage Document OCR** |
| 메타데이터 DB | SQLite / PostgreSQL (SQLAlchemy + Alembic) |
| 벡터 DB | Chroma(기본) / pgvector — `VECTOR_STORE`로 선택 |
| 그래프 DB | Neo4j 5.x (graph/hybrid 모드) + LangChain |
| PDF 파서 | pdfplumber + PyMuPDF |
| 프론트엔드 | React 18 + Vite + TypeScript |

> 추론·임베딩·OCR의 provider는 `LLM_PROVIDER` / `EMBEDDING_PROVIDER` / `OCR_BACKEND` 환경변수로 토글합니다(기본 `upstage`). 오프라인 평가용으로 `openai` 옵션이 있으나 제품 기본 경로는 국내 모델입니다.

---

## 아키텍처 (4계층)

백엔드는 도메인 응집 + 4계층으로 구성됩니다. 상세 트리는 [`docs/app-structure.md`](docs/app-structure.md) 참조.

```
app/
├── main.py · __main__.py        # FastAPI 앱 / 모듈 진입점
├── domains/                     # 비즈니스 (router→service→crud→models)
│   ├── auth users documents chunks attachments search sessions rag ingestion
├── infrastructure/              # 외부 시스템 / 기반
│   ├── llm embeddings pdfimage core external(ocr·mydata·health_data·law·hira·kidi·fss)
├── shared/                      # 횡단 (audit · security · tools)
└── interfaces/                  # 진입점 (cli)
```

- 각 도메인은 `router → service → crud → models/schemas` 호출 방향을 지킵니다. 다른 도메인은 `service` 레벨에서만 import.
- import 경로 예: `from app.domains.sessions.service import post_message`

---

## 시작하기

### 사전 준비
- Python 3.11+
- Upstage API 키 ([console.upstage.ai](https://console.upstage.ai))

### 1. 설치
```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -e .                   # 개발용: pip install -e ".[dev]"
```

### 2. 환경 변수
```bash
cp .env.example .env
```
`.env`에서 `UPSTAGE_API_KEY`를 설정합니다(추론·임베딩·OCR 공용). 나머지는 기본값으로 동작합니다.
```
LLM_PROVIDER=upstage
UPSTAGE_API_KEY=...
```

### 3. DB 초기화
```bash
alembic upgrade head               # 프로젝트 루트에 app.db(SQLite) 생성
```

### 4. 약관 PDF 배치
```
data/raw/<보험사>/<영역>/<상품>/<판매기간>/<문서종류>.pdf
```
- 영역(area): `auto` · `accident_disease` · `fire`
- 문서종류(doc_type): `summary` · `business` · `terms`
- 판매기간: `YYYY-MM-DD_present` 또는 `YYYY-MM-DD_YYYY-MM-DD`
- 폴더명은 영문 소문자+언더스코어. 한글 보험사명·상품명은 적재 시 메타데이터로 등록.

### 5. 적재 + 검색
```bash
ica ingest                         # data/raw 스캔 → 파싱·청킹·임베딩
ica search "발목 골절 입원 보험금"   # 동작 확인
```

### 6. 서버 / 대화
```bash
uvicorn app.main:app --reload --port 8000     # http://localhost:8000/docs (Swagger)
ica chat                                       # 서버 없이 터미널 멀티턴 대화
```

### (선택) Neo4j — graph/hybrid 모드
```bash
docker compose -f docker-compose.neo4j.yml up -d
ica graph-build
RAG_MODE=hybrid uvicorn app.main:app --reload --port 8000
```
상세: [`docs/usage_graphrag.md`](docs/usage_graphrag.md)

---

## 프론트엔드 (React + Vite)

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```
`vite.config.ts`가 `/api`·`/static`을 백엔드(`localhost:8001`)로 프록시합니다. 백엔드 포트를 바꾸면 프록시 타깃도 함께 조정하세요.

---

## CLI 명령

```bash
ica ingest  [--insurer <코드>] [--area <코드>] [--dry-run] [--force]   # PDF 적재
ica search  "질의문" [--top-k 8] [--insurer] [--area] [--product] [--doc-type]
ica list    [--scope products|insurers|versions|documents|chunks]      # 적재 현황
ica inspect <청크 UUID> [--show-parent] [--show-siblings]              # 청크 검수
ica rebuild [--insurer] [--area]                                      # 강제 재처리
ica reindex [--reset]                                                 # 임베딩 재생성(차원 변경 시 --reset)
ica chat                                                              # 터미널 멀티턴 대화
ica graph-build                                                       # SQLite → Neo4j 그래프 적재
ica agent-graph [--out <path>]                                        # LangGraph 노드 구조 시각화
```

---

## 환경 변수 (주요)

`.env` (`.env.example` 복사). 전체 목록은 `.env.example` 참조.

| 변수 | 기본값 | 설명 |
|:--|:--|:--|
| `LLM_PROVIDER` | `upstage` | 추론 provider. `upstage`(Solar) / `openai`(오프라인 평가 전용) |
| `UPSTAGE_API_KEY` | (없음) | Upstage API 키 — 추론·임베딩·OCR 공용 **(필수)** |
| `SOLAR_MODEL` | `solar-pro2` | Upstage 추론 모델 |
| `EMBEDDING_PROVIDER` | `upstage` | 임베딩 provider |
| `OCR_BACKEND` | `upstage` | OCR 엔진. `upstage` / `openai` |
| `VECTOR_STORE` | (자동) | 벡터 backend. `chroma` / `pgvector` / 빈 값(자동) |
| `DATABASE_URL` | (없음) | 빈 값이면 SQLite. PostgreSQL 예: `postgresql+psycopg://user:pw@host:5432/db` |
| `RAG_MODE` | `vector` | 검색 채널. `vector` / `graph` / `hybrid` |
| `RAG_REACT` | `false` | ReAct 에이전트 루프 (assessment 모드만, 비용↑) |
| `RAG_BACKEND` | `agentrunner` | ReAct backend. `agentrunner` / `langgraph` |
| `NEO4J_URI` / `NEO4J_PASSWORD` | `bolt://localhost:7687` / (없음) | graph/hybrid 모드 시 |
| `JWT_SECRET_KEY` | (없음) | 인증 토큰 서명 키(HS256) |
| `RATE_LIMIT_ENABLED` · `AUDIT_ENABLED` · `PII_MASKING_ENABLED` · `PROMETHEUS_ENABLED` | `true` | 운영 기능 토글(테스트는 false) |

---

## 개발

```bash
pip install -e ".[dev]"
ruff check app tests              # 린트
ruff format app                   # 포매팅
pytest                            # 테스트 (1100+)
pytest --cov=app
alembic revision --autogenerate -m "변경 설명"   # 모델 변경 시 마이그레이션
```

---

## 문서

| 문서 | 내용 |
|:--|:--|
| [`docs/PRD.md`](docs/PRD.md) | 제품 정의 · 기능 · 로드맵 |
| [`docs/app-structure.md`](docs/app-structure.md) | 백엔드 4계층 디렉터리 트리 |
| [`docs/design/api-spec.md`](docs/design/api-spec.md) | API 명세 |
| [`docs/design/rag-architecture.md`](docs/design/rag-architecture.md) · [`agent-architecture.md`](docs/design/agent-architecture.md) | RAG / 에이전트 아키텍처 |
| [`docs/usage_sessions.md`](docs/usage_sessions.md) · [`usage_graphrag.md`](docs/usage_graphrag.md) · [`usage_ocr.md`](docs/usage_ocr.md) · [`usage_ops.md`](docs/usage_ops.md) | 기능별 사용 가이드 |

---

## 라이선스 및 면책

**본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.** 보험금 청구 여부의 최종 판단은 해당 보험사 또는 전문 손해사정사에게 문의하시기 바랍니다.
