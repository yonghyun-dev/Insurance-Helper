# 백엔드 디렉터리 트리 (`app/`)

> 갱신: 2026-06-23 · `__pycache__`/`*.pyc` 제외
> **4계층 아키텍처** (2026-06-23 재구성): `domains`(비즈니스) / `infrastructure`(외부 시스템) / `shared`(횡단) / `interfaces`(진입점).
> import 경로: `from app.domains.<X>...`, `from app.infrastructure.<X>...`, `from app.shared.<X>...`, `from app.interfaces.<X>...`
> 라우터는 각 도메인에 유지(응집 보존). main.py·__main__.py 는 app/ 루트.

```
app/
├── __init__.py                 # 버전 + SQLAlchemy 모델 등록(forward ref 보장)
├── __main__.py                 # python -m app 진입점
├── main.py                     # FastAPI 앱 · lifespan · 라우터 등록 · /health · /metrics
│
├── domains/                    # ── 비즈니스 도메인 (router→service→crud→models/schemas) ──
│   ├── auth/                   # 자체 JWT 인증
│   │   ├── deps.py  jwt.py  router.py  schemas.py
│   ├── users/                  # User ORM + 서비스
│   │   ├── models.py  schemas.py  service.py
│   ├── documents/              # 보험사/상품/버전/문서 메타 (SQLite SoT)
│   │   ├── crud.py  models.py  router.py  schemas.py  service.py
│   ├── chunks/                 # 약관 PDF → 구조 인식 청킹
│   │   ├── chunker.py  crud.py  models.py  parser.py  router.py  schemas.py  service.py  structure.py
│   ├── attachments/            # OCR 첨부 업로드 (multipart)
│   │   ├── router.py  schemas.py  service.py
│   ├── search/                 # Chroma 벡터 검색
│   │   ├── router.py  schemas.py  service.py
│   ├── sessions/               # 멀티턴 대화 오케스트레이션 (핵심 진입점)
│   │   ├── _smalltalk.py  llm.py  router.py  schemas.py  service.py  store.py
│   ├── rag/                    # RAG 3채널 + ReAct/LangGraph 에이전트
│   │   ├── _slots.py  agent.py  graph.py  hybrid.py  indexer.py  langgraph_agent.py
│   │   ├── prompts.py  protocols.py  react.py  service.py  vector.py  vectorstore.py
│   └── ingestion/              # 적재 파이프라인 오케스트레이션
│       ├── schemas.py  service.py
│
├── infrastructure/             # ── 외부 시스템 / 기반 ──
│   ├── llm/                    # 추론·임베딩 LLM 중앙 팩토리 (Upstage 전용·폴백 없음)
│   │   └── client.py
│   ├── embeddings/             # Upstage solar-embedding 4096 (query/passage)
│   │   ├── schemas.py  service.py
│   ├── pdfimage/               # PDF 페이지 캡처 렌더 (인용 썸네일)
│   │   └── service.py
│   ├── core/                   # 설정 · DB · 예외 · 로깅
│   │   ├── config.py  database.py  exceptions.py  logging.py
│   └── external/               # 외부 API 어댑터 모음
│       ├── _common.py          # 공용 circuit breaker + TTL 캐시
│       ├── fss/                # 금융감독원 (스텁)
│       ├── health_data/        # 건강보험 진료내역 (더미 + Real skeleton)
│       │   ├── adapter.py  mapper.py  router.py
│       ├── hira/               # 심평원 진단코드 (스텁)
│       ├── kidi/               # 보험개발원 (활성, 정적 데이터)
│       ├── law/                # 국가법령정보센터 (스텁)
│       ├── mydata/             # 마이데이터 (더미 + Real skeleton)
│       └── ocr/                # OCR (OpenAI Vision + Upstage Document OCR)
│
├── shared/                     # ── 횡단 관심사 ──
│   ├── audit/                  # 감사 로그 (service 레이어에서 호출)
│   │   ├── models.py  service.py
│   ├── security/               # PII 마스킹 (로그/감사 — LLM 입력은 원문)
│   │   └── pii.py
│   └── tools/                  # 뉴로심볼릭 도구 (계산기 · 정의 · dispatcher)
│       ├── calc.py  definitions.py  dispatcher.py
│
└── interfaces/                 # ── 진입점 ──
    └── cli/                    # Typer `ica` CLI
        └── app.py
```

> 각 패키지에는 `__init__.py` 가 있으나 위 트리에서는 생략(가독성). 계층 폴더(domains/infrastructure/shared/interfaces)도 각각 `__init__.py` 보유.

## 계층 요약

| 계층 | 패키지 | 역할 |
|:--|:--|:--|
| **domains** | auth · users · documents · chunks · attachments · search · sessions · rag · ingestion | 비즈니스 로직 (router+service+crud+models 응집) |
| **infrastructure** | llm · embeddings · pdfimage · core · external(7 어댑터) | 외부 시스템·기반(설정/DB/LLM/벡터/외부 API) |
| **shared** | audit · security · tools | 횡단 관심사 |
| **interfaces** | cli | 진입점(CLI). HTTP 진입점 main.py 는 app/ 루트 |

> 라우터 등록(`app/main.py`, `/api/v1`): documents · chunks · search · sessions · auth · attachments · health_data
> 재구성 시 `__file__` 상대경로 3곳(kidi/mydata/health_data 데이터·픽스처) 깊이 +1 보정.
