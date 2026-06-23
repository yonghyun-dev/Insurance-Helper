# GraphRAG 사용 가이드

- 작성일: 2026-05-24 / 최종 갱신: 2026-05-25 (Sprint 13 LangGraph backend 추가)
- 스프린트: 4 (GraphRAG + Hybrid + ReAct) → 13 (LangGraph StateGraph)
- 관련 설계: [rag-architecture.md](design/rag-architecture.md), [graph-schema.md](design/graph-schema.md), [tech-decisions.md § Sprint 13](design/tech-decisions.md), [agent-architecture.md](design/agent-architecture.md)

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 1. 개요

### GraphRAG 가 무엇인가요?

기존에는 보험 약관 검색을 **벡터 검색(Vector)** 만으로 했습니다. 사용자 질문을 숫자(벡터)로 바꿔서 의미가 비슷한 조항을 찾는 방식입니다.

Sprint 3 데모에서 한계가 드러났습니다. 예를 들어 "제15조에서 참조하는 다른 조항까지 보여줘"라는 질문은 벡터 검색으로 처리하기 어렵습니다. 의미가 비슷한 청크를 찾는 것과, 조항 사이의 계층 관계나 참조 관계를 추적하는 것은 다른 문제이기 때문입니다.

**GraphRAG** 는 약관 데이터를 **지식 그래프(보험사 → 상품 → 약관 조항 → 항/호 계층)** 로 저장하고, 그 관계를 활용해 검색하는 방식입니다. Sprint 4에서 이 기능이 추가되었습니다.

### 3가지 검색 채널

환경변수 `RAG_MODE` 하나로 검색 방식을 선택할 수 있습니다.

---

## 2. 3가지 mode 비교

| mode | 검색 방법 | 잘 맞는 상황 | 느린 경우 |
|:--|:--|:--|:--|
| `vector` | 의미 유사도 (기본값) | "입원 의료비 보장 조항 찾아줘" 같은 자연어 질문 | 조항 계층/참조 추적 시 한계 |
| `graph` | Cypher 쿼리 자동 생성 + Neo4j 탐색 | "제6조의 모든 항/호", "한화 자동차 활성 약관" 같은 구조적 질의 | 자연어 의미 유사도는 약함 |
| `hybrid` | vector + graph 결과 합성 | 정확도를 최대한 높이고 싶을 때 | vector·graph 각각 호출하므로 응답 시간 약간 길어짐 |

**어떤 mode 를 쓰면 좋을까요?**

- 처음 시작할 때 또는 Neo4j 를 설치하지 않을 때 → **`vector`** (기본값)
- 조항 계층 탐색·참조 추적이 중요한 시연 → **`graph`** 또는 **`hybrid`**
- 검색 정확도와 다양성을 동시에 높이고 싶을 때 → **`hybrid`** (권장)

---

## 3. 빠른 시작

GraphRAG 기능을 사용하려면 Neo4j 를 먼저 실행해야 합니다. `vector` 모드만 쓸 예정이라면 이 단계를 건너뛰어도 됩니다.

### 1단계: Neo4j 실행

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

Neo4j 컨테이너가 올라오면 `http://localhost:7474` 에서 Neo4j Browser 로 접속할 수 있습니다.

### 2단계: 그래프 적재 (최초 1회)

약관 데이터를 Neo4j 에 적재합니다. SQLite 에 이미 적재된 데이터를 그래프로 변환합니다. LLM 호출 없이 결정론적으로 변환하므로 빠르게 완료됩니다.

```bash
ica graph-build
```

> **주의**: `ica ingest` 로 약관 PDF 를 먼저 적재한 후 실행해야 합니다. SQLite 에 데이터가 없으면 빈 그래프가 생성됩니다.

### 3단계: 서버 실행 (hybrid 모드)

```bash
RAG_MODE=hybrid uvicorn app.main:app --reload --port 8000
```

환경변수를 설정하지 않으면 기본값 `vector` 로 동작합니다.

---

## 4. 환경 변수 표

`.env` 파일에 추가하거나 실행 시 앞에 붙여서 사용합니다.

| 변수명 | 기본값 | 필수 | 설명 |
|:--|:--|:--|:--|
| `NEO4J_URI` | `bolt://localhost:7687` | graph/hybrid 모드 시 필요 | Neo4j Bolt 연결 주소 |
| `NEO4J_USERNAME` | `neo4j` | graph/hybrid 모드 시 필요 | Neo4j 사용자 이름 |
| `NEO4J_PASSWORD` | (없음) | graph/hybrid 모드 시 필요 | Neo4j 비밀번호 |
| `RAG_MODE` | `vector` | X | 검색 채널 선택. `vector` / `graph` / `hybrid` |
| `RAG_REACT` | `false` | X | ReAct 루프 활성화. `true` / `false`. 기본 `false` 로 회귀 0 보장 |
| `RAG_BACKEND` | `agentrunner` | X | ReAct 활성 시 사용할 agent backend. `agentrunner` (Sprint 11 자체 구현) / `langgraph` (Sprint 13 신규). `RAG_REACT=false` 시 무시 |

**`RAG_REACT=false` (기본값)** 는 ReAct 루프를 사용하지 않아 기존 동작과 동일합니다. `true` 로 바꾸면 assessment 단계에서 검색을 반복해 정확도를 높이지만 비용이 높아집니다.

`.env` 파일 예시:

```bash
# GraphRAG 설정 (Sprint 4)
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password-here

RAG_MODE=hybrid
RAG_REACT=false
# RAG_BACKEND=langgraph  # Sprint 13 LangGraph backend 사용 시 주석 해제
```

---

## 5. `ica graph-build` 사용법

SQLite 에 저장된 약관 데이터를 Neo4j 그래프로 변환합니다.

### 도움말 확인

```bash
ica graph-build --help
```

### 기본 실행 (신규 적재)

```bash
ica graph-build
```

이미 적재된 노드는 `MERGE` 방식으로 처리되므로 중복 없이 안전하게 재실행할 수 있습니다. (멱등 동작)

### 전체 재구축 (`--rebuild`)

```bash
ica graph-build --rebuild
```

기존 그래프를 모두 삭제하고 처음부터 다시 구축합니다. 스키마가 변경되었거나 데이터를 완전히 갱신해야 할 때 사용합니다.

### 통계 출력 예시

완료 후 적재된 노드·엣지 수를 출력합니다:

```
그래프 적재 완료
노드: Insurer 2 / Product 3 / Version 5 / Document 15 / Clause 241 / SubClause 498
엣지: SELLS 3 / HAS_VERSION 5 / HAS_DOCUMENT 15 / CONTAINS 241 / HAS_SUBCLAUSE 498
```

---

## 6. graceful fallback — Neo4j 다운 시 자동 전환

Neo4j 가 다운되거나 연결에 실패해도 **사용자 응답이 끊기지 않습니다**.

동작 흐름:

1. `graph` 또는 `hybrid` 모드에서 Neo4j 연결을 시도합니다
2. 연결 실패 시 로그에 경고를 남기고 **자동으로 `vector` 모드로 전환**합니다
3. 사용자는 응답을 그대로 받습니다 (검색 품질만 다소 달라질 수 있음)

로그 예시 (INFO 레벨):

```
WARNING  app.rag.service: Neo4j 연결 실패 → vector 모드로 fallback (mode=hybrid)
```

`graph` 모드에서 Cypher 쿼리 생성이 실패하더라도 동일하게 vector 결과만 사용합니다.

---

## 7. ReAct 토글 — `RAG_REACT=true` + backend 선택

ReAct(Reasoning + Acting)는 assessment(가능성 판단) 단계에서 검색을 여러 번 반복해 더 정확한 근거를 찾는 방식입니다.

**어떻게 다른가요?**

기본 동작(ReAct 꺼짐): 질문 → 검색 1회 → 판단

ReAct 켜짐: 질문 → 검색 → "이 정보로 충분한가?" → 부족하면 검색 반복 (최대 5회) → 판단

### 7.1 AgentRunner backend (Sprint 11 — 기본값)

```bash
RAG_REACT=true uvicorn app.main:app --reload --port 8000
```

또는 `.env` 파일에:

```bash
RAG_REACT=true
RAG_BACKEND=agentrunner  # 명시 또는 생략 — 동일
```

### 7.2 LangGraph backend (Sprint 13 신규)

Sprint 13에서 LangGraph StateGraph 기반 agent backend가 추가되었습니다. AgentRunner와 동등한 결과를 내면서 노드/엣지 구조가 명시적으로 시각화됩니다.

**활성화**:

```bash
RAG_REACT=true RAG_BACKEND=langgraph uvicorn app.main:app --reload --port 8000
```

또는 `.env` 파일에:

```bash
RAG_REACT=true
RAG_BACKEND=langgraph
```

**CLI 대화**:

```bash
RAG_REACT=true RAG_BACKEND=langgraph ica chat
```

**그래프 시각화**:

```bash
# stdout 에 Mermaid 출력
ica agent-graph

# 파일로 저장
ica agent-graph --out docs/design/diagrams/langgraph-flow.md
```

### 7.3 backend 비교

| 항목 | AgentRunner | LangGraph |
|:--|:--|:--|
| 구현 위치 | `app/rag/agent.py` | `app/rag/langgraph_agent.py` |
| 노드 시각화 | X | `ica agent-graph` 로 Mermaid 자동 생성 |
| 결과 동등성 | 기준 | AgentRunner 와 동등 (eval 10 시나리오 통과) |
| 폐기 시점 | Sprint 14~15 이후 | 점진 안정화 후 단독 backend 전환 |
| 활성화 env | `RAG_REACT=true` | `RAG_REACT=true RAG_BACKEND=langgraph` |

> Sprint 14~15 안정화 후 AgentRunner를 폐기하고 LangGraph를 단독 backend로 전환합니다. 현재는 양쪽 backend를 병행합니다.

### 7.4 주의 사항

- `RAG_REACT=true` 는 **assessment 모드에서만** 적용됩니다. 슬롯 수집(ask) 단계는 영향 없습니다
- LLM 호출이 평균 3회 추가되어 **비용이 기존 대비 약 2.5배** 높아집니다 (gpt-4o-mini 기준 턴당 $0.0003 → $0.0008)
- 응답 시간도 약 3~6초 길어집니다
- PoC 시연 100턴 기준 총 비용은 $0.03~$0.08 수준으로 감당 가능합니다

ReAct 를 사용하기 전에 기본 hybrid 모드로 먼저 시험해 보고, 검색 정확도가 부족하다고 느껴질 때 켜는 것을 권장합니다.

---

## 8. Neo4j Browser 활용

Neo4j Browser 에서 직접 그래프를 탐색하고 적재 현황을 확인할 수 있습니다.

### 접속

```
http://localhost:7474
```

처음 접속하면 로그인 화면이 나옵니다. `.env` 의 `NEO4J_USERNAME`, `NEO4J_PASSWORD` 로 로그인합니다.

### 적재 현황 확인 Cypher

**노드 종류별 개수 확인**:

```cypher
MATCH (n) RETURN labels(n) AS label, count(n) AS count;
```

예시 결과:

| label | count |
|:--|:--|
| Insurer | 2 |
| Product | 3 |
| Version | 5 |
| Document | 15 |
| Clause | 241 |
| SubClause | 498 |

**조항(Clause) 목록 확인** — 처음 5개:

```cypher
MATCH (c:Clause) RETURN c.clause_no, c.page_start LIMIT 5;
```

예시 결과:

| c.clause_no | c.page_start |
|:--|:--|
| 제1조 | 3 |
| 제2조 | 4 |
| 제3조 | 5 |
| 제4조 | 6 |
| 제5조 | 7 |

---

## 9. 트러블슈팅

### Neo4j 연결 실패

**증상**: `graph` 또는 `hybrid` 모드 실행 시 로그에 Neo4j 연결 실패 메시지가 보임

**확인**:

```bash
docker compose -f docker-compose.neo4j.yml ps
```

컨테이너가 `Up` 상태인지 확인합니다. 꺼져 있으면 다시 실행합니다:

```bash
docker compose -f docker-compose.neo4j.yml up -d
```

**동작**: 연결이 실패해도 서버는 자동으로 `vector` 모드로 전환합니다. 사용자 응답은 정상적으로 제공됩니다.

---

### GraphCypherQAChain Cypher 생성 실패

**증상**: graph/hybrid 모드에서 Cypher 생성 에러가 로그에 출력되고 vector 결과만 반환됨

**원인**: LLM 이 한국어 약관 도메인 질문을 Cypher 로 올바르게 변환하지 못한 경우입니다.

**동작**: `hybrid` 모드에서는 graph 검색 실패 시 vector 결과만 사용합니다. `graph` 모드에서는 빈 결과를 반환하고 서비스는 "추가 정보 필요" 안내로 분기합니다.

**권장 대응**: `hybrid` 모드 사용 시 이 케이스는 자동으로 처리됩니다. `graph` 단독 모드 사용 시 `hybrid` 로 전환하는 것을 권장합니다.

---

### `ica graph-build` 실행 시 ServiceUnavailable 에러

**증상**:

```
neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information
```

**원인**: Neo4j 컨테이너가 아직 기동 중이거나 내려가 있습니다.

**해결**:

```bash
docker compose -f docker-compose.neo4j.yml ps
```

상태가 `Up` 이 아니면:

```bash
docker compose -f docker-compose.neo4j.yml up -d
# 5~10초 대기 후 재시도
ica graph-build
```

---

### 적재된 청크가 그래프 스키마와 맞지 않음

**증상**: `ica graph-build` 완료 후 노드 수가 예상보다 적거나 0임

**원인**: `ica ingest` 를 먼저 실행하지 않았습니다. Neo4j 그래프는 SQLite 에 있는 데이터를 변환하므로, 약관 PDF 가 먼저 SQLite 에 적재되어 있어야 합니다.

**해결**: Sprint 1 적재 흐름 순서를 따릅니다.

```bash
# 1. PDF 를 data/raw/ 폴더에 배치 (README.md 4단계 참조)
# 2. SQLite 에 적재
ica ingest

# 3. Neo4j 그래프 구축
ica graph-build

# 4. 서버 실행
RAG_MODE=hybrid uvicorn app.main:app --reload --port 8000
```

---

## 참고 문서

- 세션 API 사용 방법: [`docs/usage_sessions.md`](usage_sessions.md)
- RAG 아키텍처 설계: [`docs/design/rag-architecture.md`](design/rag-architecture.md)
- Neo4j 그래프 스키마: [`docs/design/graph-schema.md`](design/graph-schema.md)
- 기술 결정 기록: [`docs/design/tech-decisions.md`](design/tech-decisions.md)
