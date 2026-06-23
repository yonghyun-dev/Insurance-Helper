# 기술 결정 기록

- 작성일: 2026-05-22
- 스프린트: 1 (PoC 데이터 파이프라인)
- 관련 요구사항: [REQ-01](../requirements/01_insurance_claim_assistant.md)

## 프로젝트 특성

- 사용자 규모: 내부 PoC / 시연 수준 (대국민 서비스 지향이지만 1차 배포는 PoC)
- 데이터 규모: 보험사 2곳 × 영역 2개 × 상품 1~2개 = 약관 PDF 약 10~30개로 시작. 점진 확장
- 서비스 유형: PoC → MVP (확장 여지 있는 구조로 시작)
- 핵심 도메인: 한국어 보험 약관 RAG (의미 검색 + 멀티턴 대화)

## 결정 사항 (요약 표)

| 카테고리 | 선택 | 이유 | 대안 | 대안을 선택하지 않은 이유 |
|:--|:--|:--|:--|:--|
| 개발 환경 | **venv (Python 3.11+)** | PoC 단계 혼자 개발, 빠른 시작. Docker 전환 비용 낮음 | Docker Compose | 추가 셋업 비용. PoC 단계 이득 적음 |
| 백엔드 | **FastAPI** | Python 기반(AI 라이브러리), 도메인 응집 구조와 호환, 빠른 개발 | Flask, Django | 비동기·타입 검증·문서화 자동화 측면 FastAPI 우위 |
| 메타데이터 DB | **SQLite** | PoC 적합, 파일 기반, 동시성 요구 낮음 | PostgreSQL | 운영 부담. PoC 단계 과설계 |
| 벡터 DB | **Chroma (로컬 영속화)** | 임베디드, 추가 서버 불필요, 메타데이터 필터링 지원 | Qdrant / Weaviate / FAISS | Qdrant/Weaviate는 별도 서버. FAISS는 메타필터링 약함 |
| 세션 저장 | **인메모리 (TTL)** | 세션 휘발성 요구. 서버 영구 저장 금지 | Redis | PoC에 과함. 단일 프로세스로 충분 |
| LLM | **OpenAI gpt-4o-mini** (필요시 gpt-4o로 업그레이드) | 한국어 무난, 비용 저렴, API 키 단일 | Claude / 로컬 Llama | 사용자 결정 (OpenAI) |
| 임베딩 | **OpenAI text-embedding-3-small** (1536-d) | LLM과 동일 제공자, API 키 통합. 한국어 품질 무난 | BGE-M3 로컬 | 로컬 임베딩 서버 운영 부담. PoC 단계 우선순위 낮음. Sprint 5+에서 품질 비교 검토 |
| PDF 파서 | **pdfplumber + PyMuPDF 조합** | pdfplumber: 표 추출 강함 / PyMuPDF: 텍스트 + 좌표 빠름 | unstructured.io | 의존성 무겁고 한국어 PDF 안정성 불확실. PoC에 과함 |
| 청킹 전략 | **구조 인식 청킹** (제N조/항/별표 경계 기반) | 단순 토큰 청킹 시 조항 단서 분리 → 면책 누락 위험 | 슬라이딩 윈도우 | 보험약관 도메인에서 치명적 품질 저하 |
| 인증 | **없음** (비로그인) | 요구사항 결정 (대국민 서비스 진입 장벽 최소화) | JWT, OAuth | PoC 단계 불필요. 개인정보 수집 최소화 |
| 캐싱 | **없음** (필요 시 인메모리 lru_cache) | PoC 트래픽 낮음. 임베딩 결과는 벡터 DB가 사실상 캐시 역할 | Redis | 단일 서버 PoC에 과함 |
| 배포 | **로컬 실행** | PoC/시연 수준 | 클라우드 배포 | PoC 단계 부적합 |
| 프론트엔드 | **Sprint 3에서 결정 → React + Vite + TS** | 빠른 PoC 채팅 UI. 사용자가 Claude 디자인으로 직접 생성 | Next.js / HTMX | Next.js 과함, HTMX = 컴포넌트 분해 약함 |
| 검색 채널 (Sprint 4) | **Vector + Graph + Hybrid** (env 토글 `RAG_MODE`) | Sprint 3 데모에서 단순 vector 한계 노출 — 약관 간 참조/계층 활용 위해 GraphRAG 추가. 기본 `vector` 로 회귀 0 | Vector only / Graph only | vector only = 참조 추적 불가 / graph only = 자연어 유사도 약함 |
| 그래프 DB (Sprint 4) | **Neo4j 5.x community** (Docker compose, 로컬) | langchain-neo4j 통합 + GraphCypherQAChain 자동 생성 + PoC 로컬 only 원칙 | Memgraph / Neo4j Aura | Aura = 외부 네트워크, 데이터 전송 우려 / Memgraph = 생태계 작음 |
| AI 프레임워크 (Sprint 4) | **LangChain 부분 도입** (`app/rag/` 안에서만) | 사용자 첨부 코드 패턴 + GraphCypherQAChain 같은 도구 재사용 | 전체 마이그레이션 / 직접 구현 | 전체 마이그 = 회귀 위험 ↑↑ / 직접 구현 = Cypher 자동생성 비용 큼 |
| Reasoning 패턴 (Sprint 4) | **ReAct** (opt-in, `RAG_REACT=true`, assessment 모드만) | 부족 정보 재검색 → 답변 정확도 ↑. max_iter=5 + score>0.92 조기 종료 | 단일 호출 / Chain-of-Thought | 단일 = 정보 부족 시 무답 / CoT = 검색 반복 없음 |

## 핵심 기술 결정 상세

### 1. PDF 파싱 + 청킹 전략 (Sprint 1 최대 리스크)

**우려**: 단순 토큰 청킹은 보험약관에서 치명적으로 실패한다.
- 조항 중간 절단 시 단서("단, 다음의 경우는 제외한다")가 다른 청크로 분리 → 면책 조건 누락
- 표 구조 손실
- 본문/특약/부록 위치 정보 손실

**전략**:

```
[Stage 1] PDF → 원시 텍스트 + 좌표 + 표
  - PyMuPDF: 페이지별 텍스트 + 좌표
  - pdfplumber: 표 추출 + 셀 단위 데이터

[Stage 2] 구조 인식 (정규식 + 휴리스틱)
  - 패턴: "제\s*\d+\s*조", "①②③", "1\.", "가\.", "별표\s*\d+"
  - 트리 구성: 문서 → 부 → 장 → 절 → 조 → 항 → 호 → 목
  - 페이지 헤더/푸터 제거 (반복 텍스트 검출)

[Stage 3] 의미 단위 청킹
  - 1청크 기본 단위 = 1개 조항(제N조)
  - 토큰 초과 시 항(①②) 단위로 분할
  - 단서/예외 절은 항상 부모 조항과 동일 청크 유지
  - 표는 별도 청크 + 캡션/주변 본문 컨텍스트 연결
  - 별표/부록은 본문에서 참조하는 조항과 cross-reference 메타데이터

[Stage 4] 메타데이터 풍부화
  - {보험사, 상품, 영역, 판매기간(version), 문서종류,
     조항번호, 항번호, 페이지, 청크유형, 부모조항, 참조조항}

[Stage 5] 임베딩 + 벡터 DB
  - text-embedding-3-small (1536-d)
  - Chroma collection: 영역(자동차/상해질병)별로 분리 검토
  - 메타데이터 인덱스: 보험사, 상품, 판매기간, 영역
```

**검증 의무**: Sprint 1의 **첫 task = 1~2개 PDF로 위 파이프라인 검증**. 핵심 조항이 의미 단위로 잘 분리되는지 수동 검수. 안 되면 전략 수정 (LLM 보조 청킹 검토).

### 2. 벡터 DB 선택 — Chroma

- **선택 이유**:
  - 임베디드(별도 서버 불필요) → PoC 셋업 빠름
  - 메타데이터 필터링 지원 (보험사/영역/판매기간 필터링 필수)
  - SQLite 기반 영속화 → 백업/이관 용이
  - Python 네이티브
- **확장 시 옵션**: 사용자 증가 시 Qdrant / pgvector로 마이그레이션 가능 (벡터 차원만 호환되면 데이터 이관 단순)

### 3. LLM 선택 — OpenAI gpt-4o-mini

- **선택 이유**: 사용자 결정. 한국어 품질 무난, 비용 저렴, API 키 단일화
- **업그레이드 경로**: 응답 품질 부족 시 gpt-4o로 모델만 교체 (코드 변경 최소)
- **임베딩 통합 이점**: text-embedding-3-small과 동일 키 사용 → 환경 변수 1개

### 4. 멀티턴 대화 — Function Calling 기반 (Sprint 2 디테일 확정)

- **전략**: LLM 이 사용자 입력에서 부족 정보를 식별하면 미리 정의된 함수 3종을 호출
- **함수 3종** (모두 `tool_choice` 로 강제):
  | 함수 | 호출 시점 | 입력 | 출력 |
  |:--|:--|:--|:--|
  | `extract_slots` | 매 사용자 메시지 직후 | history + 새 메시지 + 현재 slots | 갱신된 slots (부분 채움 허용) |
  | `next_question` | 필수 슬롯 부족 시 | slots + missing 필드 목록 | message, expected_slots, options(선택지) |
  | `generate_assessment` | 필수 슬롯 충족 시 | slots + RAG top-k 청크 | Structured Outputs(strict) — 가능성 등급 + 인용 + 면책 |
- **모델·온도**:
  - `extract_slots` / `next_question`: gpt-4o-mini, temperature 0.0 (재현성)
  - `generate_assessment`: gpt-4o-mini, temperature 0.2 (자연스러움 + 안정성 균형)
  - 응답 품질 미흡 시 gpt-4o 업그레이드 (모델명만 교체, 코드 변경 없음)
- **종료 조건**: `generate_assessment` 응답 후 사용자가 추가 메시지 보내면 슬롯 갱신 → 다시 분기
- **세션 상태**: 인메모리 `dict[session_id, Session]` + `last_activity_at` 기준 TTL 30분
  - lazy expiration: 매 조회 시 만료 검사 + 제거 (별도 cleanup 스레드 불필요, PoC 단순화)
- **race condition**: PoC 단일 사용자 가정. 같은 session_id 동시 메시지는 Sprint 5+ lock 추가

### 4-1. 영역별 필수 슬롯 정의 (Sprint 2 확정 — REQ-02 F-3·F-4 입력)

데이터 구조는 [data-model.md](data-model.md) 의 "영역별 필수 슬롯" 표 참조. 본 절은 채워야 하는 우선순위 + 의미를 정의.

**공통 (필수, 모든 영역)**: `insurer` `product` `version` `incident_date` `evidence(권장)`

**auto 추가 필수**: `incident_type` (추돌/단독/대물/대인) · `fault_ratio` · `damage_type` (자차/대물/대인)

**fire 추가 필수**: `loss_type` (전소/부분소실/도난/누수) · `damaged_items` (가전/가구/건물 등) · `cause` (원인)

**accident_disease 추가 필수**: `diagnosis` · `hospitalization_days` · `outpatient_visits`

**`next_question` 우선순위**:
1. 영역(`area`)이 미정이면 그것부터 — 다른 슬롯 판단 불가
2. `insurer` + `product` — RAG 필터에 직결, 없으면 검색 범위 비대
3. 영역별 추가 필수 슬롯 (자동차면 incident_type 등)
4. evidence 는 마지막에 권장 (보통 사용자가 안 갖고 시작)

한 번에 1~2개 슬롯만 질문 (사용자 피로 회피, 대화 자연성).

### 5. 응답 생성 전략

### 5. 응답 생성 전략

- 검색 결과 top-k(예: k=8) 조항 → LLM에 컨텍스트로 주입
- 출력 스키마(JSON) 강제:
  ```json
  {
    "likelihood": "높음 | 중간 | 낮음",
    "summary": "1~2 문장 요약",
    "satisfied": ["충족 항목 1", "..."],
    "unsatisfied": ["미충족 항목 1", "..."],
    "citations": [
      {"insurer": "...", "product": "...", "version": "...", "doc_type": "terms",
       "clause": "제15조", "sub_no": "①", "text": "원문 인용", "page": 12}
    ],
    "next_steps": ["추가로 준비할 서류/확인할 정보 1", "..."],
    "disclaimer": "본 결과는 참고용이며 ..."
  }
  ```
  (정식 JSON Schema는 [api-spec.md](api-spec.md) 의 Structured Outputs 절 참조)

## 환경 변수 (예정)

| 변수 | 용도 |
|:--|:--|
| `OPENAI_API_KEY` | LLM + 임베딩 |
| `CHROMA_DB_PATH` | 벡터 DB 영속 경로 (기본 `./data/chroma`) |
| `SQLITE_DB_PATH` | 메타 DB 경로 (기본 `./data/app.db`) |
| `RAW_DATA_PATH` | 원본 PDF 폴더 (기본 `./data/raw`) |
| `LLM_MODEL` | 모델명 (기본 `gpt-4o-mini`) |
| `EMBEDDING_MODEL` | 임베딩 모델명 (기본 `text-embedding-3-small`) |

## Sprint 2 추가 결정 — sessions 도메인 구조

- `app/sessions/` 5파일 신설 (domain-architecture 표준):
  - `router.py` — `POST /sessions`, `POST /sessions/{id}/messages`, `GET /sessions/{id}`, `DELETE /sessions/{id}`
  - `schemas.py` — pydantic: `SessionCreate`, `MessageRequest`, `AssistantResponseAsk`, `AssistantResponseAssessment`, `SlotState`, `Citation`
  - `service.py` — `create_session`, `post_message` (오케스트레이션 — extract/branch/RAG/generate)
  - `store.py` — 인메모리 `SessionStore` (dict + lazy TTL 만료)
  - `llm.py` — OpenAI Chat Completions + Function Calling 어댑터 (3종 함수 정의 + 호출)
- CLI 통합: `app/cli/app.py` 의 `ica chat` 명령이 `sessions.service.post_message` 를 직접 호출 (HTTP X)
- main.py 에 `sessions_router` include 추가 (`/api/v1/sessions/*`)

## [확인 필요] 항목 (Sprint 1 → Sprint 2 해소 추적)

- ~~보험사 2곳 최종 선정~~ → Sprint 1 완료 시 hanwha 1곳 + 자동차/화재 2개 상품으로 확정 (Sprint 2 도 동일 데이터 활용)
- ~~청크당 평균 토큰 길이 목표~~ → Sprint 1 검증 결과: 자동차 median 335 토큰, max 7000 (강제분할 적용). 합리적
- ~~멀티턴 슬롯 정의~~ → 본 문서 § 4-1 에서 확정
- LLM gpt-4o-mini 한국어 보험약관 응답 품질 — Sprint 2 T2~T4 초반 1~2회 실측으로 확인. 미흡 시 gpt-4o 업그레이드
- 세션 동시성 (race condition) — PoC 단일 사용자 가정. Sprint 5+ 시 asyncio.Lock 또는 외부 store

## 나중에 바꿀 수 있는 결정 vs 지금 잘 정해야 하는 결정

**나중에 바꿀 수 있음 (큰 비용 없음)**:
- LLM 모델 (gpt-4o-mini → gpt-4o, Claude 등)
- 임베딩 모델 (text-embedding-3-small → BGE-M3 등) — 단, 전체 재임베딩 필요
- 프론트엔드 프레임워크

**지금 잘 정해야 함**:
- **PDF 파싱 + 청킹 전략** — 데이터 품질의 근간. 잘못 정하면 RAG 전체 품질 저하
- **메타데이터 스키마** — 검색 정확도와 인용 정확도의 핵심
- **도메인 폴더 구조** — 나중에 갈아엎으면 비용 큼

---

## Sprint 4 추가 결정 — GraphRAG + Hybrid + ReAct

- 작성일: 2026-05-24
- 관련 요구사항: [REQ-04](../requirements/04_graphrag_react.md)
- 관련 설계: [graph-schema.md](graph-schema.md), [rag-architecture.md](rag-architecture.md)

### 1. 모듈 구조 — `app/rag/` 신규

**결정**: 새 도메인 `app/rag/` 추가. Vector/Graph/Hybrid 세 retrieval 채널을 공통 Protocol 로 추상화. 기존 `app/search/service.py` 는 ingestion 파이프라인 용도로 존치.

```
app/rag/
├── __init__.py
├── service.py        # retrieve(slots, top_k, mode) 단일 진입점 + fallback 로직
├── protocols.py      # Retriever Protocol (공통 인터페이스)
├── vector.py         # langchain_chroma 래퍼 (또는 기존 search 직접 호출)
├── graph.py          # langchain_neo4j.Neo4jGraph + GraphCypherQAChain
├── hybrid.py         # vector + graph 결과 합성
├── react.py          # ReAct loop (opt-in)
└── indexer.py        # SQLite → Neo4j 자동 인덱싱 ("ica graph-build")
```

**`sessions.service` 변경 범위**: `_search_chunks()` 내 `search_service.similarity_search()` 호출 1줄을 `rag_service.retrieve()` 로 교체. `generate_assessment` 입력 계약 (`list[dict]`) 무변경.

**이유**: 도메인 격리 + 단일 진입점 + 기존 코드 회귀 0 동시 달성. researcher 조사 결과 통합점이 단 1줄로 끝남.

### 2. LangChain 도입 범위

**결정**: `app/rag/` 내부만 LangChain (langchain, langchain-openai, langchain-chroma, langchain-neo4j, neo4j). 기존 `app/sessions/llm.py`, `app/embeddings/service.py`, `app/search/service.py` 는 openai SDK 직접 사용 유지.

**이유**:
- 전체 마이그레이션은 회귀 위험 ↑↑. PoC 단계에서 검증된 코드 재작성 비용 큼
- LangChain 과 openai SDK 는 양립 가능 (langchain-openai 가 내부적으로 openai SDK 래핑)
- 새 코드만 LangChain 패러다임 → 사용자 첨부 코드 패턴 직접 활용

### 3. Neo4j Docker compose 로 로컬 only

**결정**: `docker-compose.neo4j.yml` 추가. neo4j:5-community, 포트 7687(Bolt) + 7474(Browser). password 는 `.env` 의 `NEO4J_PASSWORD`. data volume 마운트 (`neo4j_data:/data`).

**이유**: PoC 로컬 only 원칙 유지. Aura cloud 는 외부 네트워크 + 데이터 전송 우려. Memgraph 는 생태계 작음.

**graceful fallback**: Neo4j 다운 / 연결 실패 시 RagService 가 자동 vector mode 로 폴백 + 로그 경고. 사용자 응답 끊김 없음.

### 4. RAG_MODE env 토글 — 기본 `vector`

**결정**: env 변수 `RAG_MODE=vector|graph|hybrid` 추가. 기본값 `vector` (Sprint 1~3 동작 보장). `RAG_REACT=true|false` 별도 토글 (기본 `false`).

**이유**:
- 기본값 vector → 회귀 0 보장 (Sprint 3 의 363 tests 무변경)
- graph / hybrid 는 명시 opt-in. Neo4j 미설치 환경에서도 정상 동작
- ReAct 는 비용 ~2.5배라 별도 토글로 A/B 가능

### 5. ReAct 적용 범위 — assessment 모드만, max_iter=5

**결정**:
- `next_question` (슬롯 수집) 단계는 ReAct X — 단순 LLM 호출 유지
- `generate_assessment` 단계에서만 ReAct loop 진입
- 종료 조건: max_iter=5 (하드) + LLM Finish 액션 + citations≥3 + 단일 score>0.92 중 하나
- 1턴당 LLM 호출 추가 평균 3회 → 전체 비용 ~2.5배

**이유**:
- 슬롯 수집은 사용자 정보 부족이라 retrieve 반복 무의미
- assessment 만 평가 정확도 중요 → ReAct 비용 정당화
- max_iter 강제로 비용 폭증 차단

### 6. 그래프 인덱싱 — 결정론 v0 + LLM 추출 백로그

**결정**:
- **v0 (Sprint 4 안)**: SQLite → Neo4j 결정론 변환. 5 노드 라벨 (Insurer/Product/Version/Document/Clause/SubClause) + 5 엣지 (SELLS/HAS_VERSION/HAS_DOCUMENT/CONTAINS/HAS_SUBCLAUSE). LLM 0회 호출
- **v1 (Sprint 5+)**: LLM 으로 Concept 노드 + REFERS_TO/COVERS/EXCLUDES 엣지 추출. 청크당 1회 LLM (739 × ~$0.0001 ≈ $0.07 일회성)

**이유**: v0 만으로도 "제3조의 부모/형제 조항" 같은 hierarchical 탐색이 vector 단독 대비 우위. LLM 추출은 품질·비용 미지수라 단계적 검증

### 비용 영향 (예측)

| 시나리오 | LLM 호출/턴 | 토큰 합계 | 비용/턴 (gpt-4o-mini) |
|:--|:--|:--|:--|
| 기존 (vector, no ReAct) | 2 (extract + generate) | ~2500 | $0.0003 |
| graph, no ReAct | 2 + Cypher 생성 1 | ~2800 | $0.0004 |
| hybrid, no ReAct | 3 (extract + vector/graph + 합성) | ~3500 | $0.0005 |
| hybrid + ReAct (max 5) | 3 + ReAct loop 평균 3 | ~5500 | $0.0008 |

PoC 시연 100턴 ≈ $0.03~$0.08. PoC 범위 내.

### 변경 안 한 것 (의도적)

- LLM 모델 (gpt-4o-mini 유지)
- 임베딩 모델 (text-embedding-3-small 유지)
- 벡터 DB (Chroma 유지 — langchain-chroma 가 기존 컬렉션 직접 재사용 가능)
- 세션 저장 (인메모리 TTL 유지)
- 인증 (없음 유지)

### [해소] 후속 결정 (2026-05-24 — 구현 시점 확정)

- ~~그래프 빌드 명령 이름~~ → **`ica graph-build`** (kebab-case, 기존 ingest/inspect/rebuild 와 일관). `--rebuild` 옵션으로 전체 삭제 후 재구축.
- ~~Neo4j 인덱스~~ → graph-schema.md § 5 DDL 에 확정. **6 unique 제약 + 3 검색 인덱스** (`clause_no`, `area`, `is_active`). 성능 측정은 Sprint 5+ 백로그.
- ~~Chroma collection_name~~ → 기존 `app/search/service.py` 의 `COLLECTION_NAME = "insurance_clauses"` 유지. **현재 VectorRetriever 는 기존 search.service 호출 (옵션 B 채택)** 이라 LangChain Chroma 래퍼 미사용. 추후 LangChain 래퍼 도입 시 동일 컬렉션명 명시.

---

## Sprint 5 추가 결정 — 인용 카드 PDF 페이지 캡처 렌더

- 작성일: 2026-05-24
- 관련 요구사항: [REQ-05](../requirements/05_pdf_page_render.md)

### 1. 변환 방식 — PyMuPDF lazy + 디스크 캐시

**결정**: 첫 요청 시점에 `page.get_pixmap(matrix=Matrix(1.5, 1.5))` 로 변환 후 `data/page_images/<doc_id>/<page:04d>.png` 저장. 이후 즉시.

**이유**: 사전 일괄 변환은 700+ 청크 × ~100ms = 시간/디스크 낭비. 시연에 첫 8건만 캐시되면 충분.

**대안**: 동적 endpoint (`GET /citations/{id}/image`) → 거부. StaticFiles 가 캐싱·서빙 자동 + 단순.

### 2. URL 주입 — backend hydrate (LLM 미관여)

**결정**: `Citation.page_image_url` + `pdf_url` 는 backend 가 `_build_assessment` 직후 채움. LLM 응답에는 없음.

**이유**:
- LLM 이 URL 생성 시 환각 위험 (실제 없는 chunk_id 의 URL 만들 수 있음)
- `_ASSESSMENT_RESPONSE_SCHEMA` 변경 불필요 (Sprint 4 schema 그대로 유지)
- chunks list 의 metadata 에 `document_id` 있어 SQLite lookup 1회로 file_path 확정

**구현**: `_hydrate_citation_urls(citations, chunks)` 가 chunk_id → document_id → file_path → URL 매핑. `Citation.model_copy(update={...})` 로 새 필드 주입.

### 3. StaticFiles 2개 마운트 — `/static/page_images` + `/static/raw`

**결정**: `app/main.py` 의 `add_middleware` 직후 + `include_router` 앞에 2 마운트.

**이유**: 페이지 캡처와 원본 PDF 둘 다 직접 노출 → 클릭 시 `#page=N` 점프. Starlette 가 path traversal 자동 차단.

### 4. Citation schema 확장 — optional 2 필드

**결정**: `Citation` 에 `page_image_url: str | None = None` + `pdf_url: str | None = None` 추가. 기존 9 필드 무변경.

**이유**: 회귀 0 보장. variant 또는 새 응답 모델 없이 hydrate 만으로 동작.

**호환**: `Citation` 의 `extra="forbid"` 와 충돌 없음 — pydantic 이 새 명시 필드를 허용.

### 5. frontend CitationItem — PM 직접 수정 (Claude 디자인 재호출 X)

**결정**: 3 파일 (`types/api.ts` + `CitationItem.tsx` + `index.css`) PM 직접. 사양서는 별도 갱신 (다음 Claude 디자인 호출 시 일관성).

**이유**: 변경이 작음 (~50줄). Claude 디자인 재호출은 사용자 부담. 사양서 갱신은 추후 일관성 유지.

### 6. 하이라이트 박스 (옵션 B) 는 Sprint 6+ 백로그

**결정**: 청크별 bbox 좌표 매핑은 chunker 파이프라인 변경 + 재적재 필요 → 본 sprint 범위 외.

### 비용 영향

| 항목 | 수치 |
|:--|:--|
| 변환 시간 | ~50~100ms / page (PyMuPDF) |
| 디스크 사용 | ~100KB / page × 4 PDF × ~50 page = ~20MB 일회성 |
| 첫 응답 지연 | citations 8건 모두 첫 호출이면 ~800ms. 이후 0 |
| LLM 비용 | 0 (URL 생성 LLM 미관여) |
| 회귀 | 0 (473 tests 그대로 통과) |

---

## Sprint 6 추가 결정 — 응답 품질 정책

- 작성일: 2026-05-24
- 관련 요구사항: [REQ-06](../requirements/06_response_quality.md)

### 1. "모름" 처리 — `SlotState.unknown_slots: list[str]`

**결정**: SlotState 에 `unknown_slots` 필드 추가 (default `[]`). extract_slots LLM 이 사용자 "모름"/"몰라"/"모르겠어" 입력 인식 → 해당 슬롯명 배열에 추가. `_compute_missing` 가 missing 에서 제외.

**이유**:
- 명시 신호로 무한 ask 루프 차단
- 슬롯 값 자체는 None 유지 (모름 = 값 없음). sentinel 값 회피 → validator 복잡도 ↓
- pydantic 직렬화 호환 (Set 대신 list)

**대안**:
- 슬롯 값에 "unknown" sentinel → 거부 (각 슬롯 타입과 충돌)
- 외부 dict → 거부 (캡슐화 깨짐)

### 2. partial assessment — `AssistantAssessment.confidence: Literal['partial','full']`

**결정**: `Literal["partial","full"] = "full"` optional 필드. JSON Schema `_ASSESSMENT_RESPONSE_SCHEMA` 의 required + enum 에 명시. LLM 이 직접 출력.

**이유**:
- Sprint 5 의 `page_image_url` 패턴 (optional 필드 추가, default 로 회귀 0) 과 동일
- partial 은 LLM 의 판단 (`unknown_slots` + 슬롯 충족도) 이므로 schema 노출 필수 (page_image_url 은 backend hydrate 라 schema 미노출 차이)

**대안**:
- 별도 응답 모드 `AssistantPartialAssessment` → 거부 (discriminator 복잡 + frontend 변경 ↑)

### 3. partial 진입 조건 3가지

**결정** (`_should_partial`):
1. `unknown_slots` 수 ≥ 2 — 사용자 명시 다수
2. ask 횟수 ≥ 3 — 무한 루프 방지
3. 사용자 입력에 "그냥"/"됐어"/"알려줘"/"그만"/"다 모름" 키워드

**이유**: 사용자 명시 (1, 3) + 자동 (2) 둘 다 안전망. PoC 단계 임계값 (2, 3) 은 보수적

### 4. partial 모드도 `citations ≥ 1` 강제

**결정**: schema `minItems=1` 그대로. RAG 검색 결과 0건 → 기존 `_build_no_match_ask` 폴백 유지.

**이유**: 인용 없는 partial = 환각 위험 ↑. PoC 단계는 "정보 부족하지만 약관 참조" 까지

### 5. LLM 프롬프트 4종 변경

| 함수 | 변경 |
|:--|:--|
| `extract_slots` | (a) tool schema 에 `unknown_slots` 배열 추가 (b) system 프롬프트 규칙 6-a/6-b 추가 ("모름"/negative) (c) area 단서 확장 ("넘어졌어/다쳤어/병원" → accident_disease) |
| `next_question` | (a) tool description 예시 한국어 (`['자동차','화재','사고질병']`) (b) system 프롬프트에 "options 영문 코드 금지" 강제 |
| `generate_assessment` | (a) JSON Schema 의 required + properties 에 `confidence` 추가 (b) system 규칙 6: partial 시 summary 첫 문장에 "정보가 일부 부족하여 추정 기반..." 포함 |
| `_build_assessment` (`app/sessions/llm.py`) | LLM Structured Output dict 를 `AssistantAssessment` 로 변환 시 `raw.get("confidence", "full")` 로 read + backward-compat default. logger 에도 confidence 출력 |

### 6. frontend AssessmentCard — partial badge (PM 직접)

**결정**: hero 영역에 조건부 `<span class="assess__partial-badge">(추정)</span>` + 노란 배경 stripe. PM 이 1 파일 (3줄) 수정 — Claude 디자인 재호출 X. 사양서 ui-spec.md 갱신 (다음 디자인 호출 시 일관성).

**이유**: 작은 변경 + 시연 가치. Sprint 5 의 CitationItem 패턴 그대로

### 비용 영향

| 항목 | 수치 |
|:--|:--|
| LLM 호출 추가 | 0 (프롬프트 변경만, 호출 횟수 무변경) |
| 토큰 증가 | 시스템 프롬프트 ~200 토큰 / extract_slots tool 정의 ~50 토큰 = 턴당 ~$0.0000X |
| schema 변경 회귀 | 0 (`confidence` 는 backward-compat default 'full') |
| frontend 변경 | 3 파일 (types/api.ts + AssessmentCard.tsx + index.css) |

---

## Sprint 7 추가 결정 — 응답 톤 정책

- 작성일: 2026-05-24
- 관련 요구사항: [REQ-07](../requirements/07_response_tone.md)

### 1. 톤 가이드 4 원칙 (모든 user-facing 응답에 적용)

| 원칙 | 금지 | 권장 |
|:--|:--|:--|
| (a) 능동적 안내 | "다시 확인해 주세요" / "정확히 알려주세요" | "정확한 안내를 위해 ... 정보를 알려주시면 정확하게 안내드리겠습니다" |
| (b) 책임 비전가 | "입력 정보가 부족합니다" (사용자 책임) | "현재 정보만으로는 일반적인 약관 기준에 따라 안내드리겠습니다" (시스템 능동) |
| (c) 정확성 vs 범용성 명시 | (구분 없음) | 정보 충족 → "정확하게 안내드립니다" / 부족 → "일반적인 기준으로 안내드립니다" |
| (d) 친절체 + 존댓말 | 명령형 / 반말 | "~드리겠습니다" / "~주시면 좋겠습니다" / "~안내드립니다" |

### 2. 적용 위치

| 함수 | 변경 |
|:--|:--|
| `app/sessions/service.py — _build_no_match_ask` | 하드코딩 메시지 재작성 — "다시 확인해 주세요" → "정확한 청구 가능성 판단에는 가입하신 보험사·상품 정보가 필요합니다. 알고 계신 정보가 있다면 알려주시면 정확하게 안내드리겠습니다" |
| `app/sessions/llm.py — _NEXT_QUESTION_SYSTEM` | 시스템 프롬프트 끝에 "톤 가이드" 절 — "정확한 안내를 위해 ... 정보를 확인하고 싶습니다" 식 친절체 강제. 사용자에게 책임 떠넘기는 어조 금지 |
| `app/sessions/llm.py — _ASSESSMENT_SYSTEM` (partial 모드) | 규칙 6 (Sprint 6) 보강 — "정보가 일부 부족하여 추정 기반" → "정확한 답변에는 ... 정보가 더 있으면 좋겠으나, 현재 정보로 일반적인 약관 기준에 따라 안내드리겠습니다" |
| `extract_slots` | 변경 없음 — tool args 만 반환 (user-facing 메시지 없음) |

### 3. RAG ≥ 1 강제 유지 (Sprint 6 결정 5 보존)

**결정**: 톤만 보완, citation 0 답변은 여전히 허용 X. RAG 0건 → `_build_no_match_ask` 로 폴백.

**이유**:
- citation 없는 답변 = LLM 일반지식 의존 = 환각 위험 ↑ + 법적 책임 ↑
- 사용자 경험 향상은 톤 보완으로도 충분 (Sprint 6 partial 모드 + Sprint 7 톤은 보완 관계)

### 비용 영향

| 항목 | 수치 |
|:--|:--|
| LLM 호출 추가 | 0 (시스템 프롬프트 텍스트만 추가) |
| 토큰 증가 | `_NEXT_QUESTION_SYSTEM` + `_ASSESSMENT_SYSTEM` 각 ~80 토큰 = 턴당 ~$0.00001 |
| schema 변경 | 0 |
| 회귀 | 0 (응답 구조 동일, 메시지 텍스트만 다름) |
| frontend 변경 | 0 |

---

## Sprint 8~11 추가 결정 — 대국민 서비스 전환

- 작성일: 2026-05-25
- 관련 요구사항: [REQ-08](../requirements/08_public_service_transition.md)
- 관련 설계: [agent-architecture.md](agent-architecture.md), [external-apis.md](external-apis.md)
- **중요 가정 변경**: Sprint 1 의 "사용자 규모: 내부 PoC / 시연 수준" **폐기**. 운영 단계 진입.

### 0. 전체 원칙 (모든 결정에 우선)

| 원칙 | 의미 |
|:--|:--|
| **신뢰성 우선** | 모르면 답하지 않는다 — RAG citation ≥ 1 강제 + 외부 검증 데이터 옆에 인용 |
| **추적 가능성** | 모든 응답에 response_id + LLM trace + citations 영구 보존 (분쟁 시 재현) |
| **법적 책임 한정** | 면책 + 약관 동의 (선택) + 책임 한정 멘트 모든 응답에 포함 |
| **개인정보 최소** | 사용자 PII 는 즉시 마스킹 → 로그/감사에 평문 미저장 |
| **장애 격리** | 외부 API 장애가 핵심 서비스 다운으로 전파되지 않음 (graceful degradation) |
| **접근성** | WCAG AA — 노인·장애인 포함 |

### 1. SLO 정의

| 메트릭 | 목표 | 측정 위치 |
|:--|:--|:--|
| API p95 응답시간 | < 5초 (LLM 호출 포함 — 5 tool call 최악) | FastAPI 미들웨어 |
| API p50 응답시간 | < 2초 | 동상 |
| 에러율 (5xx) | < 0.5% / 24h | 동상 |
| LLM 토큰 비용 | < $0.05 / 응답 (gpt-4o-mini 기준) | LLM 호출 wrapper |
| RAG 검색 latency p95 | < 1초 (Chroma + Neo4j 합산) | rag_service.retrieve |
| 외부 API 실패율 | < 5% (개별 API 별) — 초과 시 circuit breaker | external 어댑터 |

### 2. 감사 로그 (audit log)

**결정**: 별도 PostgreSQL 테이블 `audit_log`. 모든 응답에 대해 다음 record 작성.

```
audit_log
├── response_id (UUID, PK)
├── session_id (FK, nullable — 세션 삭제 후에도 보존)
├── turn (int)
├── created_at (timestamp)
├── masked_user_input (text — PII 마스킹 후)
├── llm_calls (jsonb — [{function_name, model, tokens, latency_ms}, ...])
├── retrieved_chunk_ids (text[] — RAG citation 추적)
├── external_api_calls (jsonb — [{api, endpoint, cached, latency_ms}, ...])
├── assistant_response_type (ask|assessment)
├── assistant_message_hash (sha256 — 무결성)
└── confidence (partial|full|null)
```

**보존 기간**: 7년 ([확인 필요] 법무 — 보험 분쟁 시효 기준).

**이유**: 분쟁 발생 시 특정 응답을 100% 재현해야 함. masked_user_input + llm_calls + retrieved_chunk_ids 면 충분.

### 3. PII 마스킹

**결정**: regex 기반 + `presidio` 라이브러리 옵션. 한국어 패턴 (주민번호, 휴대전화, 계좌번호, 카드번호, 이메일).

**적용 위치**:
- `app/sessions/service.post_message` 진입 직후 — user input 마스킹
- `app/core/logging` formatter — 모든 로그 출력 전 강제
- audit log 저장 전

**미마스킹 대상**: 진단명·과실비율·사고 경위 (분쟁 시 필수). 단 PostgreSQL `audit_log` 는 운영자 접근 권한 분리.

### 4. rate limit + circuit breaker

| 위치 | 정책 |
|:--|:--|
| API 진입 (slowapi) | per-IP 10 req/min, per-session 30 req/min |
| 외부 API call (각 어댑터) | 호출 횟수 추적 + 5xx/timeout 5회 연속 → 60초 circuit open → vector RAG 만으로 폴백 |
| LLM 호출 (OpenAI) | 비용 한도 — 일일 $50, 초과 시 503 (운영자 알림) |

**circuit breaker 라이브러리**: `pybreaker` 또는 자체 구현. 단순 카운터 + timestamp.

### 5. 면책 + 법적 책임 한정

| 위치 | 멘트 |
|:--|:--|
| 매 assessment 응답 (현재) | `_DEFAULT_DISCLAIMER` 유지 |
| 매 ask 응답 (신규) | "본 안내는 참고용입니다" 추가 |
| UI 헤더 (frontend) | 영구 표시 — "본 서비스는 청구 가능성 안내 도구이며, 최종 결정은 보험사에 있습니다" |
| 약관 동의 화면 (Sprint 11 — 선택) | 최초 접속 시 1회 동의 (선택) — 운영자 결정 사항 |

### 6. DB 전환 — SQLite → PostgreSQL

**결정**: Sprint 8 끝 또는 Sprint 9 시작 시점에 마이그레이션. alembic 으로 schema 이관.

**이유**: ① 동시 쓰기 (운영 트래픽) ② 감사 로그 영속 (7년) ③ JSONB 활용 (`llm_calls`, `external_api_calls`)

**대안**: SQLite 유지 → 거부 (운영 부적합, lock 경합)

**시점 결정**: Sprint 8 의 audit_log 모델 추가 시점에 함께 마이그레이션. 단 메타 데이터(documents/chunks) 는 별도 sprint 로 분리 가능. **[확인 필요]** alembic 마이그레이션 정책 (drop & recreate vs 데이터 이관)

### 7. 외부 API 호출 — Python `httpx` 직접 (MCP 미사용)

**결정**: `app/external/{law,hira,kidi,fss}/` 도메인 응집 구조. MCP 미사용.

**이유**:
- OpenAI 는 MCP 클라이언트가 아님 (LLM tool 은 Function Calling 으로 정의)
- 운영 장애점 회피
- 외부 API 모두 표준 REST — httpx 직접이 가장 단순·테스트 가능·감사 가능
- 캐싱·rate limit·circuit breaker 모두 Python 미들웨어로 직접 구현이 표준

**대안**: MCP server 도입 → 거부 (over-engineering)

### 8. 캐싱 정책 (외부 API)

| API | TTL | 이유 |
|:--|:--|:--|
| 법령정보센터 (조항 본문) | 30일 | 법령은 거의 안 바뀜 |
| HIRA (KCD 진단코드) | 7일 | 분기별 갱신 |
| 손보협회 표준 (과실비율) | 영구 (정적 데이터셋) | 연 단위 갱신 |
| 금감원 공시 (상품 메타) | 24시간 | 새 상품 빠른 반영 |

**구현**: 1단계 `cachetools` 인메모리. 2단계 (Sprint 10+) Redis.

### 9. 모니터링 — OpenTelemetry + Prometheus + Grafana

**결정**:
- Sprint 8: prometheus exposition endpoint (`/metrics`) — 메트릭 수집만
- Sprint 11: Grafana 대시보드 + OpenTelemetry tracing

**계측 대상**: SLO § 1 의 모든 메트릭 + LLM tool 호출 횟수 + audit_log 작성 ratio

### 10. 접근성 (WCAG AA)

| 영역 | 결정 |
|:--|:--|
| 폰트 크기 | 최소 16px + 사용자 토글 (대/중/소) |
| 색 대비 | 4.5:1 이상 (assess--high/mid/low 칩 색 재검증) |
| 키보드 only | Tab 순서 명시 + focus ring |
| 스크린리더 | aria-label / role / aria-live 전수 점검 (Sprint 11) |
| 모바일 | 기존 사양서 § 5.1 (320px~)  유지 |

### 11. 평가 셋 (eval set)

**결정**: `eval/` 디렉토리 신규. 초기 시나리오 10건 + 회귀 4건 (#C/#D/#E/#F).

```
eval/
├── scenarios/
│   ├── auto_low_fault.json     ← 입력 + 기대 슬롯 + 기대 confidence + 기대 citations
│   ├── fire_total_loss.json
│   └── ... (10 시나리오)
├── runner.py                   ← scenario 실행 → 결과 비교 → 메트릭 출력
└── README.md
```

**평가 방법**:
- 슬롯 추출 정확도 (extract_slots) — exact match
- 응답 종류 정확도 (ask vs assessment) — exact match
- citations 정확도 — chunk_id 중첩률
- 답변 품질 — LLM-as-judge (Sprint 11 옵션)

**CI 통합**: Sprint 11 — github actions 에서 PR 마다 eval 셋 실행

### 12. 운영 보안

| 영역 | 결정 |
|:--|:--|
| OpenAI API key | 환경 변수 + secret manager (Sprint 12+) |
| 사용자 인증 | 비로그인 유지 (REQ-01 결정 보존). 단 API rate limit 으로 abuse 차단 |
| HTTPS | 외부 배포 시 의무 (Sprint 12+) |
| SQL injection | SQLAlchemy ORM 사용 — 직접 SQL 없음 (확인) |
| XSS | frontend React 기본 escape + DOMPurify (외부 약관 텍스트 표시 시) |

### 13. 비용 영향 (Sprint 8~11 누계)

| 항목 | 수치 (월 1만 응답 가정) |
|:--|:--|
| LLM 호출 (ReAct 활성화 시) | 호출 ~3.5배 → $50~150/월 (gpt-4o-mini) |
| 외부 API 호출 (캐싱 후) | < 1만 req/일 (법령 70% 캐시 hit 가정) — 무료 또는 < $10/월 |
| PostgreSQL 호스팅 | ~$15~50/월 (운영자 결정) |
| Redis 호스팅 (Sprint 10+) | ~$10/월 |
| 모니터링 (Sprint 11) | ~$0~30/월 (self-hosted Grafana 0원) |
| 회귀 | 0 (Sprint 8 인프라 추가는 기존 흐름 무영향, 미들웨어만) |

### 14. 사양서 변경 영향

- `data-model.md` — audit_log 테이블 추가 + 마이그 정책
- `api-spec.md` — rate limit 응답 (429) + 외부 API 장애 응답 (503 Retry-After)
- `ui-spec.md` — 면책 헤더 + 접근성 토글 + WCAG AA 색 대비 재검증
- `ui-api-flow.md` — audit log 응답 ID 노출 여부 (디버그 모드만? 운영자 결정)
- `rag-architecture.md` — Sprint 11 ReAct 본격 활성화 후 갱신
- 신규: `agent-architecture.md` (전체 LLM agent 흐름) + `external-apis.md` (4 외부 API 명세)

---

## Sprint 8.6 추가 결정 — 옵션 노출 정책 (Claude Plan 모드 패턴)

- 작성일: 2026-05-25
- 관련 요구사항: [REQ-09](../requirements/09_trust_ux_polish.md)
- 관련 컴포넌트: [pages/options-panel.md](pages/options-panel.md)

### 1. 모든 ask 에 옵션 강제 X — 슬롯 성격별 분기

**결정**: `_NEXT_QUESTION_SYSTEM` 가 슬롯 성격을 보고 `options` 채움 / 빈 배열 결정. frontend `OptionsPanel` 은 `options.length > 0` 일 때만 visible (기존 동작 유지).

**이유**:
- 사용자 피드백 — "Claude Code Plan 모드도 매번 안 뜨는데, 모든 질문에 4 chip 강제는 UX 과잉"
- 자유 텍스트 슬롯 (보험사명, 진단명, 날짜) 에 강제 옵션 = 사용자 선택 제한 + UX 부담
- closed-ended (enum) 슬롯에만 옵션이 진짜 가치

**정책 — closed-ended 5종 (options 채움 + "모르겠습니다" 의무)**:

| 슬롯 | 옵션 예시 |
|:--|:--|
| `area` | `['자동차', '화재', '사고질병', '모르겠습니다']` |
| `incident_type` (auto) | `['추돌', '접촉', '주차사고', '단독사고', '기타', '모르겠습니다']` |
| `damage_type` (auto) | `['대물', '대인', '자기차량', '기타', '모르겠습니다']` |
| `loss_type` (fire) | `['전손', '부분손해', '도난', '기타', '모르겠습니다']` |
| `cause` (fire) | `['전기적 원인', '가스/조리 부주의', '방화', '자연재해', '기타', '모르겠습니다']` |

**정책 — open-ended (options 빈 배열, 자유 입력)**:

`insurer`, `product`, `incident_date`, `diagnosis`, `damaged_items`, `evidence`, `hospitalization_days`, `outpatient_visits`, `fault_ratio`

→ 자유 텍스트 슬롯에서도 사용자가 "모르겠습니다" 라고 직접 입력 가능. `extract_slots` 가 unknown_slots 머지 (Sprint 6).

**대안**:
- A. 모든 ask 에 옵션 강제 (이전 결정) → 거부 (UX 과잉, Claude Plan 모드 대비 부자연)
- B. frontend 가 슬롯 이름 화이트리스트로 OptionsPanel 분기 → 거부 (backend 책임 분산, 정책 분리 어려움)
- C. **backend system prompt 가 결정 (채택)** — 정책 단일 위치

### 2. "모르겠습니다" 노출 — closed-ended 만

**결정**: open-ended 슬롯에서는 "모르겠습니다" chip 노출 안 함 (panel 자체 미노출). 단 사용자가 자유 입력으로 "모르겠어요"/"몰라요" 입력 시 `extract_slots` 가 unknown_slots 머지 (Sprint 6 기존 동작).

**이유**: 자유 텍스트 슬롯에 "모르겠습니다" 단일 chip 만 노출하는 건 UX 어색.

### 3. 사양서 영향

- `ui-states.md § 9.5` — OptionsPanel 미노출 케이스 명시 (자유 텍스트 슬롯)
- `pages/options-panel.md § 5 동작 규칙` — `options.length === 0` 시 미표시 (이미 명시됨)
- 회귀 0 — frontend 변경 0 (이미 `options.length > 0` 분기)

## Sprint 12 추가 결정 — 벡터 DB pgvector 전환 (Chroma → PostgreSQL + pgvector)

- 작성일: 2026-05-26
- 관련 요구사항: [REQ-13](../requirements/13_pgvector-migration.md)
- 관련 분석: [PM-12](../pm/12_initial-concept-gap-analysis.md), [PM-13](../pm/13_sprint12-pgvector-analysis.md)

### 배경

챔피언 제안서 (`구현제안서_챔피언_디포커스AI.docx`) 의 "Data & Knowledge Layer (Storage): PostgreSQL, Neo4j, pgvector" 명세 회복. 운영 DB (메타 + 감사 로그) 와 벡터 임베딩을 단일 PostgreSQL 로 통합 → 운영 단순화 + ACID 일치 + 백업·복구 통합.

### 결정 요약 표

| 카테고리 | 선택 | 이유 | 대안 미선택 이유 |
|:--|:--|:--|:--|
| 벡터 DB | **pgvector (PostgreSQL 확장)** | 운영 DB 통합, 챔피언 제안서 일치 | Chroma — 별 backend 운영 부담 |
| Docker 이미지 | **`pgvector/pgvector:pg16`** | 공식 이미지, postgres 16 안정 | `ankane/pgvector` (비공식) |
| 인덱스 종류 | **HNSW (m=16, ef_construction=64)** | 정확도 우선, 739 청크 소규모 | IVFFlat — 정확도 낮음 |
| 거리 함수 | **cosine distance (`<=>`)** | Chroma 기본 cosine 과 동등 | L2/inner product — text-embedding-3-small 미정규화에 부적합 |
| 마이그레이션 전략 | **점진 (env 토글 `VECTOR_STORE`)** | 회귀 추적 + 동등성 측정 가능 | 빅뱅 — 롤백 어려움 |
| 어댑터 위치 | **`app/rag/vectorstore.py` 신규 단일 파일** (researcher 권장) | 어댑터 2개, 서브패키지 과함. 현재 `app/search/service.py` 단일 파일 패턴 일관 | 서브패키지 — 분리 과함 |
| 환경별 자동 선택 | **DATABASE_URL 기반 fallback** | 개발자 토글 부담 0 — SQLite=Chroma / PG=pgvector | 환경변수 강제 — 셋업 부담 |
| 숨은 결합 정리 | **`to_chroma_where` → `to_filter` 메서드명 변경 + CLI "Chroma 카운트" 일반화 + health() 어댑터 위임** | researcher 발견 3건, Sprint 12 진입의 깨끗한 정리 | 후순위 chore — 폐기 시점 다시 찾아야 함 |
| 테스트 real DB | **testcontainers-python (PostgreSQL+pgvector 컨테이너 spin-up)** | SQLite 에 pgvector 불가, 로컬 ↔ CI 일관성 | GitHub Actions services: postgres — 환경 구속 |
| Chroma 폐기 시점 | **Sprint 13 (LangGraph) 완료 후 별도 chore commit** | pgvector 안정 검증 + 한 번에 폐기 | Sprint 12 내 즉시 폐기 — 롤백 여지 0 |

### 1. 어댑터 인터페이스 (`app/rag/vectorstore.py` — 단일 파일)

```python
class VectorStoreAdapter(Protocol):
    def add(self, embeddings: list[list[float]], metadatas: list[dict], ids: list[str]) -> None: ...
    def query(self, embedding: list[float], n_results: int, where: dict | None = None) -> list[QueryResult]: ...
    def delete(self, ids: list[str]) -> None: ...
    def count(self) -> int: ...
    def health(self) -> bool: ...


def get_vector_store() -> VectorStoreAdapter:
    settings = get_settings()
    if settings.effective_vector_store == "pgvector":
        return PgVectorAdapter(settings.database_url)
    return ChromaAdapter(settings.chroma_db_path)
```

- `ChromaAdapter` — 기존 `app/search/service.py` thin wrap (similarity_search/upsert_chunks/delete_by_document/count/get_collection 호출)
- `PgVectorAdapter` — `psycopg` + `pgvector` 라이브러리, `clause_chunks.embedding` 컬럼 + HNSW 인덱스 사용
- `VectorRetriever.__init__` 에서 `get_vector_store()` 주입 → researcher 가 발견한 `vector.py:43-48` health() 의 Chroma 의존 제거

### 2. Alembic migration — `clause_chunks.embedding vector(1536)` 컬럼

```sql
-- 신규 revision: pgvector_embedding
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE clause_chunks ADD COLUMN embedding vector(1536);
CREATE INDEX clause_chunks_embedding_hnsw_idx
    ON clause_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

- SQLite dev 환경에서는 마이그레이션 skip (sqlite dialect 분기)
- PostgreSQL 운영에서만 실행

### 3. 환경별 자동 선택 로직 (`app/core/config.py`)

```python
@property
def effective_vector_store(self) -> Literal["chroma", "pgvector"]:
    if self.vector_store:                              # 명시 토글 우선
        return self.vector_store
    if self.database_url.startswith("postgresql"):    # PG 환경 → pgvector
        return "pgvector"
    return "chroma"                                    # SQLite 등 → chroma
```

### 4. 회귀 보장 — 동등성 테스트

- 동일 시드 청크 양 backend 적재 → 동일 질의 → **top-8 overlap ≥ 7/8** 요구
- 임베딩 동일 (OpenAI text-embedding-3-small) → 거리 계산 라이브러리만 다름 → 미세 차이 허용
- 7/8 미달 시 인덱스 파라미터 (ef_search) 조정 + 재검증

### 5. 사양서 영향

- `data-model.md` — `clause_chunks.embedding` 컬럼 추가 + HNSW 인덱스 명시
- `rag-architecture.md` — VectorStore 추상화 레이어 추가
- `usage_ops.md` — pgvector 전환 가이드 (Docker compose + alembic + ica reindex)

### 6. 숨은 결합 정리 (researcher 발견, Sprint 12 진입 시 동시 처리)

researcher 가 발견한 Chroma 명칭 결합 3건 — pgvector 전환 시 동시 정리하여 향후 Chroma 폐기 시점에 잔재 0:

1. **`SearchFilters.to_chroma_where()` → `to_filter()`** (`app/search/schemas.py:23`)
   - 메서드 반환은 dict 이라 어댑터 중립 — 이름만 정정
   - 영향: `tests/search/test_search_schemas.py` 19개 테스트 동시 갱신
2. **`app/cli/app.py:265-270` "SQLite 와 Chroma 카운트" UI 문자열** → "SQLite 와 벡터 DB 카운트"
3. **`app/rag/vector.py:43-48` `health()` 가 `search_service.get_collection()` 직접 호출** → `VectorStoreAdapter.health()` 호출로 위임

### 7. Chroma 폐기 (Sprint 13 완료 후)

- `pyproject.toml` 의 `chromadb` 제거
- `chroma_db/` 디렉터리 삭제 (data + 의존)
- `app/rag/vectorstore.py` 의 `ChromaAdapter` + 등록 정리
- `app/search/service.py` 정리 (PgVectorAdapter 단일 backend 시 search 도메인 자체 폐기 검토)
- 별도 chore commit 으로 분리

## Sprint 13 추가 결정 — Agent 오케스트레이션 LangGraph 전환 (AgentRunner → StateGraph)

- 작성일: 2026-05-26
- 관련 요구사항: [REQ-12](../requirements/12_langgraph-migration.md)
- 관련 분석: [PM-12](../pm/12_initial-concept-gap-analysis.md), [PM-14](../pm/14_sprint13-langgraph-analysis.md)

### 배경

챔피언 제안서 "AI Layer — LangGraph" 명세 회복. Sprint 11 자체 구현 `AgentRunner` 는 ReAct 의 모든 기능 (turn loop / tool_calls / dedup / max_iter / 영역별 system prompt) 을 동작시키나, 노드/엣지 표준화 부재로 시각화·유지보수성 부담. LangGraph 도입으로 표준 워크플로우 + XAI 시각화.

### 결정 요약 표

| 카테고리 | 선택 | 이유 | 대안 미선택 이유 |
|:--|:--|:--|:--|
| 마이그레이션 전략 | **점진 (env 토글 `RAG_BACKEND=agentrunner\|langgraph`)** | 양 backend 병행, 회귀 추적 | 빅뱅 — 롤백 어려움 |
| state 정의 | **`AgentState` TypedDict** | LangGraph 표준 + 가벼움 | pydantic BaseModel — 보일러플레이트 |
| 노드 구성 (실제) | **4 노드** (prepare / call_llm / execute_tools + should_continue 조건) | Sprint 13 범위: AgentRunner ReAct 만 LangGraph 화. 6 노드 (extract/decide/next_q/retrieve/tool/assess) 확장은 후속 Sprint 16+ | 단일 monolith — XAI 불가 |
| tool wrap 방식 | **단일 `tool_call` 노드 + 내부 dispatcher 분기** | 단순, 기존 dispatcher 재활용 | LangChain ToolNode — Tool 객체 래퍼 부담 |
| 조건 엣지 | **`decide_action` 반환 dict `next_action` 키 분기** | LangGraph add_conditional_edges 표준 | 노드 내부 if-else — XAI 시각화 약함 |
| audit 통합 | **AgentState.tool_calls → audit row tool_calls JSONB** | Sprint 11 audit 스키마 그대로 | 신규 컬럼 — 회귀 위험 |
| 시각화 | **`ica agent-graph` 신규 CLI + draw_mermaid()** | 챔피언 XAI 일치 + 디자인 자동화 | 수동 그림 — 코드와 drift |
| 테스트 전략 | **노드 단위 + StateGraph 통합 + RAG_BACKEND 양쪽 회귀** | 격리성 + 동등성 보장 | 통합만 — 회귀 추적 어려움 |
| AgentRunner 폐기 시점 | **Sprint 14~15 안정화 후 별도 chore commit** | LangGraph 안정 검증 | Sprint 13 내 즉시 — 롤백 0 |

### 1. AgentState (`app/rag/langgraph_agent.py`)

```python
class AgentState(TypedDict):
    slots: SlotState
    messages: list[dict[str, Any]]              # LLM 대화 이력
    tool_calls: list[dict[str, Any]]            # 호출 기록 (audit 용)
    retrieved_chunks: list[dict[str, Any]]      # RAG 결과 누적
    visited_tools: set[str]                     # dedup
    iter_count: int                             # max_iter 가드
    next_action: Literal["ask", "retrieve", "tool_call", "assessment", "end"]
```

### 2. 노드 구성 (실제 구현: 4 노드 — 2026-05-26 정정)

**Sprint 13 범위**: AgentRunner 의 ReAct loop 만 LangGraph 화 (sessions.service 의 extract/next/assess 흡수는 후속 Sprint 16+).

| 노드 | 책임 | 재사용 함수 |
|:--|:--|:--|
| `prepare` | 초기 system + user 메시지 구성 + state 초기화 | `_slot_summary` + `tools_for_area` |
| `call_llm` | OpenAI Function Calling 호출 → tool_calls 반환 또는 no_tool_call | OpenAI API (gpt-4o-mini) |
| `execute_tools` | tool_calls 반복 → dispatcher.invoke → tool 결과 누적 | `tools.dispatcher.invoke` (8 tool) + `_safe_invoke` |
| `should_continue` | (조건 엣지 함수) finish / max_iter 검사 → END or call_llm | — |

**조건 엣지 2종**:
- `call_llm` → `after_llm` 함수 → END (no_tool_call) 또는 `execute_tools`
- `execute_tools` → `should_continue` 함수 → END (finish/max_iter) 또는 `call_llm`

**후속 Sprint 확장 (선택)**: 6 노드 구조 (extract_slots / decide_action / next_question / retrieve / tool_call / generate_assessment) 로 sessions.service 흐름 전체 흡수 검토.

### 3. 조건 엣지 (실제 구현 — 2026-05-26 정정)

```python
# call_llm → execute_tools / END
def after_llm(state: AgentState) -> str:
    if state.get("finish_reason") == "no_tool_call":
        return END
    return "execute_tools"

graph.add_conditional_edges("call_llm", after_llm, {END: END, "execute_tools": "execute_tools"})

# execute_tools → call_llm (계속) / END (finish/max_iter)
def should_continue(state: AgentState) -> str:
    if state.get("finish_reason") == "finish":
        return END
    if state.get("iter_count", 0) >= state.get("max_iter", DEFAULT_MAX_ITER):
        return END
    return "call_llm"

graph.add_conditional_edges("execute_tools", should_continue, {END: END, "call_llm": "call_llm"})
```

### 4. env 토글 — 점진 마이그레이션

```python
# app/core/config.py
rag_backend: Literal["agentrunner", "langgraph"] = Field(
    default="agentrunner",
    description="RAG_REACT=true 시 사용할 agent backend",
)
```

`RAG_REACT=true RAG_BACKEND=langgraph` → LangGraph 호출 / 기본 (`agentrunner`) → 기존 AgentRunner.

### 5. 시각화 (`ica agent-graph`)

```bash
ica agent-graph                                # stdout 에 mermaid
ica agent-graph --out docs/design/diagrams/langgraph-flow.md  # 파일 저장
```

내부: `graph.compile().get_graph().draw_mermaid()` 또는 LangGraph 시각화 API.

### 6. 사양서 영향

- `agent-architecture.md` — § 3 ReAct loop → LangGraph StateGraph 노드 트리로 교체
- `usage_graphrag.md` — § 4 ReAct 절 → LangGraph backend 설명 추가
- `docs/design/diagrams/langgraph-flow.md` — 신규 (자동 생성)

### 7. AgentRunner 폐기 (Sprint 14~15 이후)

- `app/rag/agent.py` 제거
- `rag.service.run_agent` 제거 (LangGraph 버전만 유지)
- 별도 chore commit 으로 분리

## Sprint 14 추가 결정 — 마이데이터 + 로그인 시스템 (자체 JWT + DummyAdapter)

- 작성일: 2026-05-26
- 관련 요구사항: [REQ-10](../requirements/10_mydata-login.md)
- 관련 분석: [PM-12](../pm/12_initial-concept-gap-analysis.md), [PM-15](../pm/15_sprint14-mydata-login-analysis.md)

### 배경

챔피언 제안서 "Data Layer — 마이데이터·공공데이터 자동 수집" 명세 회복. 마이데이터 사업자 인증 (1~3개월 대기) 기간 동안 표준 API 응답 스키마 기반 더미 fixture 로 백엔드·UI·테스트 선행 구축. 본인 인증을 위한 자체 JWT 로그인 시스템 동시 도입. 비로그인 대국민 흐름 (Sprint 1~13) 회귀 0 보장.

### 결정 요약 표

| 카테고리 | 선택 | 이유 | 대안 미선택 이유 |
|:--|:--|:--|:--|
| 인증 방식 | **자체 JWT (python-jose + bcrypt)** | PoC 외부 의존 0, FastAPI 공식 패턴 | OAuth — 외부 앱 등록 부담 / 마이데이터 본인인증 — 실 API 발급 후 |
| 토큰 형식 | **HS256 access token only (60분 만료)** | PoC 단순화, 만료 후 재로그인 | refresh token + rotation — 후속 검토 |
| 토큰 저장 | **HttpOnly Secure Cookie** | XSS 차단, frontend 명시 | localStorage — XSS 노출 |
| 비로그인 호환 | **모든 sessions API 인증 옵셔널** | Sprint 1~13 비로그인 흐름 회귀 0 | 강제 로그인 — 대국민 진입 장벽 |
| 마이데이터 어댑터 | **`MydataAdapter` Protocol + Dummy/Real** | 실 API 교체 단일 인터페이스 | service 직접 호출 — 후속 교체 비용 |
| 더미 fixture | **3 시나리오 (단일/다수/만료 혼합)** | 슬롯 prefill 다양한 케이스 검증 | 1 시나리오 — 회귀 약함 |
| 신규 도메인 | **`app/auth/` + `app/users/` + `app/external/mydata/`** | 기존 도메인 응집 패턴 일관 | 단일 `app/auth/` 통합 — 책임 혼재 |
| prefill UX | **사용자 명시 선택 (prefill_candidates 카드)** | 자동 강제 X — 사용자 통제 | 자동 prefill — UX 부담 |

### 1. JWT 인증 (`app/auth/`)

```python
# app/auth/jwt.py
def create_access_token(user_id: int, *, expires_minutes: int = 60) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None

# app/auth/deps.py
def get_current_user_optional(token: str | None = Cookie(...)) -> User | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return users_service.get_by_id(user_id)
```

비로그인 호환: `Optional[User]` 반환 — 미인증 시 None.

### 2. Users 테이블 (Alembic)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- bcrypt
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE audit_log ADD COLUMN user_id INTEGER REFERENCES users(id);  -- nullable
```

기존 audit_log row 마이그레이션 0 (user_id NULL 허용).

### 3. MydataAdapter Protocol (`app/external/mydata/`)

```python
class MydataAdapter(Protocol):
    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        """가입 보험 목록. InsuranceDict = {insurer_id, product_name, policy_no, valid_from, valid_to}"""
        ...

class DummyAdapter:
    def __init__(self, fixture_path: Path):
        self._data = json.loads(fixture_path.read_text())
    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        return self._data.get(user_external_id, [])

class RealAdapter:
    def fetch_insurances(self, user_external_id: str) -> list[InsuranceDict]:
        raise MydataNotConfiguredError("RealAdapter 비활성 — 마이데이터 사업자 인증 대기")
```

env 토글: `MYDATA_BACKEND=dummy|real` (기본 dummy).

### 4. 더미 fixture 3 시나리오 (`tests/fixtures/mydata/users.json`)

```json
{
  "user-1": [{"insurer_id": "hanwha", "product_name": "개인용 자동차보험", "policy_no": "...", "valid_from": "2026-01-01", "valid_to": null}],
  "user-2": [...2건...],
  "user-3": [...1 만료 + 1 활성...]
}
```

### 5. sessions API 인증 옵셔널 — 비로그인 호환

```python
# app/sessions/router.py:create_session
@router.post("/sessions")
async def create_session(
    body: CreateSessionRequest,
    current_user: User | None = Depends(get_current_user_optional),
):
    session = service.create_session(initial_message=body.initial_message, user_id=current_user.id if current_user else None)
    if current_user:
        prefill = mydata_adapter.fetch_insurances(str(current_user.id))
        return {"session_id": session.id, "ttl_seconds": ..., "prefill_candidates": prefill}
    return {"session_id": session.id, "ttl_seconds": ...}
```

비로그인 흐름: 기존 응답 형식 그대로 (prefill_candidates 키 부재) — 회귀 0.

### 6. 슬롯 prefill UX (frontend)

1. 로그인 후 `POST /sessions` → `prefill_candidates: [...]` 응답
2. frontend: "내 보험 가져오기" 카드 노출 (chip 선택)
3. 사용자 chip 선택 → `POST /sessions/{id}/messages` 첫 user 메시지에 선택 보험 정보 동봉
4. backend: extract_slots → insurer/product/version 자동 채움

### 7. 비로그인 흐름 회귀 보장

| 회귀 영역 | 보장 방법 |
|:--|:--|
| 기존 sessions API 응답 형식 | prefill_candidates 키는 로그인 시에만 추가 — 비로그인 시 응답 동일 |
| audit_log.user_id 컬럼 추가 | nullable + 기존 row 그대로 |
| 인증 헤더 없는 기존 테스트 (959 tests) | `get_current_user_optional` 가 None 반환 — 기존 동작 동일 |
| Sprint 13 rag_react / rag_backend 분기 | sessions.service 변경 최소화 — prefill 흐름은 별도 endpoint |

### 8. frontend 외부 작업 명세

- `docs/design/pages/login-page.md` 신규 — 로그인/회원가입 폼 + 토큰 cookie
- `docs/design/pages/my-insurances.md` 신규 — 가입 보험 카드 + chip 선택
- 사용자 Claude 디자인 외부 작업 (Sprint 8.5 패턴 일관)

### 9. AgentRunner 폐기 시점 갱신

기존 "Sprint 14~15 이후" → Sprint 14 진행 중 / Sprint 15 OCR 완료 후 별도 chore commit.

## Sprint 15 추가 결정 — OCR 서류 처리 (OpenAI Vision + 슬롯 자동 매핑)

- 작성일: 2026-05-26
- 관련 요구사항: [REQ-11](../requirements/11_ocr-document.md)
- 관련 분석: [PM-12](../pm/12_initial-concept-gap-analysis.md), [PM-16](../pm/16_sprint15-ocr-analysis.md)

### 배경

챔피언 제안서 "Neural Layer — 비정형 문서 OCR + 핵심 정보 자동 추출" 명세 회복. 사용자가 사고 서류 (병원 진단서, 경찰 신고서, 보험 청구서, 영수증) 업로드 → OCR 텍스트 추출 → LLM 분류 + 슬롯 매핑 → 사용자 확인 후 슬롯 적용. 채팅 슬롯 입력 부담 감소.

### 결정 요약 표

| 카테고리 | 선택 | 이유 | 대안 미선택 이유 |
|:--|:--|:--|:--|
| OCR 엔진 | **OpenAI Vision (gpt-4o-mini multimodal)** | 현재 스택 일관, 한국어 OK, API key 0 | Upstage — Sprint 16 / Tesseract — 한국어 정확도 |
| 어댑터 인터페이스 | **`OcrAdapter` Protocol 단일 메서드** | 단순, backend 통일 | 다중 메서드 — 과한 분리 |
| 서류 유형 | **5종 (diagnosis/police_report/claim_form/receipt/other)** | 보험 청구 표준 | 더 많은 유형 — LLM 분류 정확도 ↓ |
| 슬롯 매핑 | **서류 유형별 기대 필드 매핑** | 정확도 ↑ | LLM 자유 추출 — 노이즈 ↑ |
| 첨부 저장 | **`data/uploads/{session}/{uuid}.{ext}` 24h TTL** | GDPR/개인정보보호 | 영구 저장 — 법적 위험 |
| TTL 관리 | **APScheduler 또는 startup task** | 자동화 | 수동 cleanup — 누락 위험 |
| PII 마스킹 | **OCR 직후 mask_pii → 마스킹 후 LLM 전달** | 원본 외부 전송 차단 | LLM 후 마스킹 — 이미 전송됨 |
| audit hash | **기존 external_api_calls JSONB 재사용** | 스키마 변경 0 | 신규 컬럼 — 회귀 위험 |
| UX 정책 | **사용자 확인 카드 후 명시 적용 (자동 X)** | OCR 오추출 안전망 | 자동 반영 — 잘못된 assessment 위험 |
| 신규 도메인 | **`app/attachments/` + `app/external/ocr/`** | 기존 도메인 응집 일관 | 단일 통합 — 책임 혼재 |

### 1. OcrAdapter (`app/external/ocr/adapter.py`)

```python
class OcrResult(TypedDict):
    text: str          # OCR 원본 텍스트 (마스킹 전 — 호출자 책임으로 mask_pii 적용 후 LLM 전달)
    confidence: float  # 0.0~1.0
    page_count: int    # 다중 페이지 PDF 지원 시

class OcrAdapter(Protocol):
    def extract_text(self, image_bytes: bytes, mime_type: str) -> OcrResult: ...

class OpenAiVisionAdapter:
    """gpt-4o-mini multimodal — image_url base64."""
    def extract_text(self, image_bytes: bytes, mime_type: str) -> OcrResult:
        b64 = base64.b64encode(image_bytes).decode()
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 이미지의 모든 텍스트를 추출하라. 줄바꿈 보존."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }],
        )
        return OcrResult(text=response.choices[0].message.content, confidence=0.9, page_count=1)

class UpstageAdapter:
    def extract_text(self, *_) -> OcrResult:
        raise OcrNotConfiguredError("Upstage OCR — Sprint 16 활성")
```

env 토글: `OCR_BACKEND=openai|upstage` (기본 openai).

### 2. 서류 유형 분류 LLM (`app/sessions/llm.py`)

```python
def classify_document(text: str) -> dict[str, Any]:
    """OCR 추출 텍스트 → 서류 유형 분류 (5종) + 신뢰도."""
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "보험 청구 관련 서류 분류기. 5 유형 중 하나 + 신뢰도."},
            {"role": "user", "content": text[:2000]},  # 토큰 가드
        ],
        tools=[CLASSIFY_DOCUMENT_TOOL],
        tool_choice={"type": "function", "function": {"name": "classify_document"}},
    )
    return json.loads(response.choices[0].message.tool_calls[0].function.arguments)
```

5 유형 + 신뢰도 < 0.7 시 `other` 폴백.

### 3. 슬롯 매핑 LLM

```python
def extract_slots_from_document(text: str, doc_type: str) -> dict[str, Any]:
    """서류 유형별 기대 필드 → SlotState 매핑."""
    expected_fields = SLOT_MAPPING[doc_type]  # {"diagnosis": ["diagnosis_name", "hospital", ...]}
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"서류 유형 {doc_type} 에서 {expected_fields} 추출"},
            {"role": "user", "content": text[:3000]},
        ],
        tools=[EXTRACT_SLOTS_TOOL],
        tool_choice="auto",
    )
    return json.loads(response.choices[0].message.tool_calls[0].function.arguments)
```

### 4. POST /sessions/{id}/documents endpoint

```python
@router.post("/{session_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(
    session_id: str,
    file: UploadFile = File(...),
):
    # 1) attachments service — 파일 저장
    attachment = await attachments_service.save(session_id, file)
    # 2) OCR 어댑터 호출
    ocr_result = ocr_adapter.extract_text(attachment.bytes, file.content_type)
    # 3) PII 마스킹
    masked_text = mask_pii(ocr_result.text)
    # 4) 분류 + 슬롯 매핑
    doc_type_info = classify_document(masked_text)
    extracted_slots = extract_slots_from_document(masked_text, doc_type_info["doc_type"])
    # 5) audit
    audit_ctx.external_api_calls.append({
        "type": "ocr_upload",
        "file_hash": attachment.sha256,
        "file_size": attachment.size,
        "doc_type": doc_type_info["doc_type"],
        "confidence": doc_type_info["confidence"],
    })
    # 6) 응답 — 사용자 확인 카드용
    return DocumentUploadResponse(
        attachment_id=attachment.id,
        doc_type=doc_type_info["doc_type"],
        doc_type_confidence=doc_type_info["confidence"],
        extracted_slots=extracted_slots,
        confidence_per_field={...},
    )
```

### 5. 사용자 확인 카드 적용 endpoint

```python
@router.post("/{session_id}/apply-extracted")
def apply_extracted_slots(session_id: str, payload: ApplyExtractedRequest):
    """사용자가 확인 카드에서 선택한 슬롯만 SlotState 에 적용."""
    session = sessions_service.get(session_id)
    session.slots.update(payload.confirmed_slots)
    return {"ok": True}
```

### 6. 24h TTL cleanup

```python
# app/main.py startup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(attachments_service.cleanup_expired, "interval", hours=1)

@app.on_event("startup")
async def start_scheduler():
    if settings.attachment_ttl_hours > 0:
        scheduler.start()
```

또는 별도 cron 분리 (운영 환경).

### 7. PII 마스킹 정책

- OCR 직후 `mask_pii(text)` 호출 → 마스킹 후 텍스트만 LLM 전달
- 원본 마스킹 전 텍스트는 audit_log 에도 저장 X (hash 만)
- 주민번호/카드번호/계좌 등 정규식 마스킹 그대로 적용 (Sprint 8 패턴)
- 진단명/과실비율 등 분쟁 시 필수 정보는 마스킹 제외 (기존 정책)

### 8. 사양서 영향

- `api-spec.md` — POST /sessions/{id}/documents + POST /sessions/{id}/apply-extracted 신규
- `data-model.md` — attachments 신규 (id, session_id, sha256, file_size, mime_type, created_at, expires_at)
- `usage_ocr.md` 신규 — OCR 활성화 + OCR_BACKEND env + 트러블슈팅
- `agent-architecture.md` — Neural Layer 절에 OCR 추가

### 9. Upstage OCR 전환 시점

Sprint 16 (LLM 스택 Upstage 전환) 시점에 동시 — OpenAI Vision → Upstage OCR + LLM 스택 일관성.
