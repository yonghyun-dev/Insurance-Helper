# REQ-04: GraphRAG + Hybrid RAG + ReAct

- 요청일: 2026-05-24
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 4

## 요청 원문

> "GraphRAG도 추가하자. 첨부한 코드(RagService/GraphRagService/HybridRagService)를 파악해서 노드/라벨 스키마 적용해서 자동화 사이클 돌려줘. 옵션 잘 뺄 수 있도록 해줘. ReAct 방식을 고려해서 실제로 쿼리를 받고 결과를 확인하도록 진행하자. 설계를 진행해서 해줘."

첨부 코드는 LangChain 기반:
- `RagService` — Chroma MMR retriever + ChatOpenAI
- `GraphRagService` — Neo4jGraph + GraphCypherQAChain (질문 → Cypher 자동 생성)
- `HybridRagService` — Vector + Graph 동시 호출 후 LLM 합성

## 핵심 목표

- 약관 검색 채널을 **3가지로 확장**: vector / graph / hybrid — env 토글로 런타임 선택
- 약관 도메인 지식 그래프 (Neo4j) 구축 — Insurer/Product/Document/Clause/Concept 등 노드 + 참조 관계
- **ReAct 방식 reasoning** — 단발 retrieve → answer 가 아니라 "질문 → retrieve → evaluate → (부족하면) refine query → retrieve 반복 → answer"
- 옵션 모듈화 — 새 채널 추가/제거 비용 최소 (`app/rag/` 도메인 신규 + Service 추상화)
- Sprint 3 의 응답 품질 이슈 (placeholder 옵션, "모름" 무시 등) 중 일부는 ReAct + Hybrid 로 자연 해소 기대. 남은 정책 변경 (partial mode 등) 은 Sprint 5

## 사용자 시나리오 (개선 대상)

1. "길가다 넘어졌는데 보험청구 어떻게해?" → ReAct 1차 retrieve (낙상/상해) → 결과 빈약 평가 → 2차 refine ("상해보험 보장 사고 정의") → Graph 에서 Clause/Concept 노드 + Coverage 엣지로 보강 → 종합 답변
2. "한화 종합보험인데 약관에 뭐가 있어?" → Graph 가 (Insurer)-[:SELLS]->(Product)-[:HAS_DOCUMENT]->(Document)-[:CONTAINS]->(Clause) 순회 → 적재된 상품 list 동적 응답
3. "제15조에 따른 보장은?" → Graph 의 (Clause)-[:REFERS_TO]->(Clause) 엣지로 다단계 hop (Vector 단독으로는 어려움)

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | `app/rag/` 도메인 신규 + Service 추상화 | 필수 | Vector/Graph/Hybrid 공통 인터페이스 (Protocol). 옵션 토글의 기반 | 설계 진행 중 |
| F-2 | VectorRagService 마이그레이션 | 필수 | 기존 search.service 를 LangChain Chroma 래퍼로 재구현 (MMR 활용) | 설계 진행 중 |
| F-3 | Neo4j 인덱서 (SQLite → Graph 적재, v0 결정론) | 필수 | clause_chunks + documents 기반 매핑. LLM 0회. Concept/COVERS/EXCLUDES/REFERS_TO 등 LLM 추출은 Sprint 5+ 백로그 | 설계 진행 중 |
| F-4 | GraphRagService (Cypher 자동 생성 + 실행) | 필수 | langchain_neo4j.GraphCypherQAChain. 응답에 생성 Cypher 포함 (감사) | 설계 진행 중 |
| F-5 | HybridRagService (Vector + Graph 합성) | 필수 | 두 결과를 컨텍스트로 묶어 LLM 종합 답변 | 설계 진행 중 |
| F-6 | ReAct loop | 필수 | LangGraph 또는 자체 구현 — max_iter / 정보 충분 판단 / 종료 조건 | 설계 진행 중 |
| F-7 | `RAG_MODE` env 토글 (`vector`/`graph`/`hybrid`) + `RAG_REACT=true` | 필수 | sessions.service 는 mode 결정 후 적절 service 호출 | 설계 진행 중 |
| F-8 | Neo4j Docker compose 설정 | 필수 | 로컬 실행 (포트 7687/7474). dev 시작 안내 | 설계 진행 중 |
| F-9 | sessions.service 통합 | 필수 | generate_assessment 가 새 RagService 인터페이스 호출 | 설계 진행 중 |
| F-10 | 테스트 + playwright 회귀 | 필수 | mode 별 동작 + 사용자 시연 시나리오 자동 검증 | 설계 진행 중 |
| F-11 | UI 에서 mode 선택 노출 (디버그용) | 권장 | SlotInspector 옆에 mode 표시 + 강제 변경 | 백로그 |

## 비기능 요구사항

- **로컬 실행 유지** — Neo4j 도 Docker compose 로 로컬 only
- **회귀 0** — 기존 363 tests 통과 유지. RAG_MODE 미설정 시 기본=`vector` (기존 동작)
- **graceful fallback** — Neo4j 다운 / Cypher 실패 시 자동으로 vector mode 로 폴백, 사용자 응답 끊김 X
- **비용** — ReAct loop 의 `max_iter=5` (하드 리밋). 평균 3회 반복 예상. 조기 종료 조건(citations≥3 / score>0.92 / LLM Finish) 으로 평균 비용 ~2.5배 유지. 무한 루프는 max_iter 강제로 차단
- **감사 추적** — graph 모드 응답에 생성 Cypher 포함. hybrid 응답에 vector/graph 양쪽 결과 + 합성 결과 모두 노출 가능
- **Sprint 5 분리** — "모름" 처리, partial assessment, 옵션 동적 생성 같은 LLM 정책 변경은 본 sprint 범위 외

## PoC 범위

- Neo4j 단일 인스턴스 (Docker, password env)
- 그래프 인덱싱 — 적재된 4 PDF / 739 청크에 대해 1회 (수동 실행 `ica graph-build`)
- mode 토글 = env 만 (UI 노출은 백로그 F-11)
- ReAct = LangGraph 또는 자체 loop (의존성 가벼운 쪽 선택)

## 기술 결정 (요약 — 상세는 tech-decisions.md)

- **새 의존성**: `langchain`, `langchain-openai`, `langchain-chroma`, `langchain-neo4j`, `neo4j` (Python driver), 선택 `langgraph`
- **LangChain 도입 범위**: 새 `app/rag/` 안에서만. 기존 `app/sessions/llm.py` / `app/search/service.py` 는 점진 마이그레이션 (Sprint 4 안에서 search 만 마이그)
- **Neo4j**: Docker compose. v5.x community edition
- **schema 적재 정책**: 결정론적 (LLM 없이 SQL/메타 기반) 노드/엣지 = Insurer/Product/Version/Document/Clause/SubClause. LLM 추출 노드 = Concept/Coverage/Exclusion (Sprint 4 안에서 시도, 품질 낮으면 백로그)

## 리스크

1. **Neo4j 의존 추가** — Docker 미설치 환경에서 실패 가능. graceful fallback (vector mode) 으로 완화
2. **Cypher 자동 생성 품질** — GraphCypherQAChain 이 비표준 스키마/한국어 라벨에 약함. enhanced_schema=True + few-shot 예시로 완화
3. **ReAct 비용** — loop 반복 시 LLM 호출 ↑. max_iter=2 강제 + 평균 토큰 모니터링
4. **마이그레이션 충돌** — search.service 와 새 app/rag/vector 가 중복. Sprint 4 내에 search.service 를 vector rag service 의 thin wrapper 로 변경, 호출자는 점진 이전
5. **그래프 인덱싱 비용** — LLM 으로 Concept 추출 시 청크당 1회 LLM 호출 (739 청크 × $0.0001 ~ $0.07 일회성). 결정론 매핑 먼저, LLM 추출은 추후

## 가정 (auto mode 진행, 추후 검증 필요)

- Neo4j Docker compose 채택 (로컬 PoC 적합)
- LangChain 도입 (사용자 첨부 코드 패턴 따라)
- 응답 품질 정책 (모름/partial) 은 Sprint 5 로 분리
- RAG_MODE 기본값 `vector` (기존 동작 유지, 회귀 0)

위 가정 중 변경 원하시면 알려주세요. 본 문서 갱신 후 진행.

## 비고

- Sprint 4 완료 시 시연 시나리오 (Sprint 3 의 playwright 시나리오) 가 새 mode 별로 모두 통과 — 회귀 + 개선 동시 확인
- Sprint 5 (응답 품질 정책) 는 Sprint 4 결과 본 뒤 우선순위 재평가
