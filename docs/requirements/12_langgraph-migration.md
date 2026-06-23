# REQ-12: Agent 오케스트레이션 LangGraph 전환

- 요청일: 2026-05-26
- 상태: 분석 완료, 설계 대기
- 스프린트: 13
- 출처: 챔피언 제안서 "AI Layer — LangGraph" 명세

## 요청 원문

> Agent 오케스트레이션을 LangGraph로 만들고

## 핵심 목표

Sprint 11 에서 자체 구현한 `AgentRunner` (`app/rag/agent.py`) 를 **LangGraph 워크플로우**로 마이그레이션. 노드/엣지/state 표준화로 시각화 + 유지보수성 + 챔피언 제안서 일치도 회복.

## 사용자 시나리오

(시스템 내부 마이그레이션 — 사용자 시나리오 변경 없음. 응답 형식·품질·latency 회귀 0 보장.)

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | LangGraph 의존성 도입 | 필수 | `pyproject.toml` 에 `langgraph` 추가 | 미시작 |
| F-2 | StateGraph 정의 | 필수 | SlotState + tool_calls + retrieved_chunks 통합 state | 미시작 |
| F-3 | 노드 정의 | 필수 | extract_slots / decide_action / next_question / retrieve / tool_call / generate_assessment | 미시작 |
| F-4 | 조건 엣지 | 필수 | 슬롯 충족 → retrieve / 부족 → next_question / partial → assessment | 미시작 |
| F-5 | tool 노드 | 필수 | 기존 8 tool dispatcher 를 LangGraph tool 노드로 wrap | 미시작 |
| F-6 | AgentRunner → LangGraph 대체 | 필수 | `app/rag/agent.py` 폐기 → `app/rag/graph.py` 신규 | 미시작 |
| F-7 | audit 통합 | 필수 | 각 노드 transition 을 audit_log llm_calls 에 기록 | 미시작 |
| F-8 | 회귀 0 보장 | 필수 | 898 + Sprint 12 신규 테스트 모두 통과 | 미시작 |
| F-9 | LangGraph 시각화 | 권장 | `graph.draw_mermaid()` 출력 → docs/design/diagrams/ | 미시작 |
| F-10 | RAG_REACT env 토글 유지 | 필수 | `RAG_REACT=true` 시에만 LangGraph 활성, false 시 직선 흐름 (기존 호환) | 미시작 |

## 기술 결정 (Sprint 13 진입 시 확정)

### 마이그레이션 전략

| 옵션 | 장점 | 단점 |
|:--|:--|:--|
| **빅뱅** — AgentRunner 즉시 폐기 + 전체 노드 한 번에 | 코드 단순 | 회귀 추적 어려움 |
| **점진** — AgentRunner 와 LangGraph 병행 → env 토글로 단계 전환 | 회귀 추적 쉬움, 비교 가능 | 일시적 2 경로 유지 부담 |

→ **점진 추천** — F-10 env 토글 유지로 양 경로 비교 후 LangGraph 안정화 시점에 AgentRunner 폐기.

### LangChain 과의 관계

- 현재 `app/rag/` 의 LangChain (GraphCypherQAChain) 은 유지 — LangGraph 가 그 위에 노드로 wrap
- LangGraph 는 LangChain 생태계 동일 → 호환성 OK

## 의존성

- Sprint 12 (pgvector) 완료 후 권장 — retrieve 노드가 pgvector 인터페이스로 바뀐 다음 LangGraph 노드화
- 기존 Tool Dispatcher (`app/tools/dispatcher.py`) 는 그대로 재사용 — LangGraph tool 노드의 backend

## 리스크

| 리스크 | 영향 | 대응 |
|:--|:--|:--|
| LangGraph state 정의 미스 → 노드 간 데이터 손실 | 중 | F-2 state TypedDict 명시 + 노드별 단위 테스트 |
| Sprint 11 AgentRunner 의 tool 중복 차단 로직 누락 | 중 | LangGraph state 에 visited_tools set 추가 |
| 마이그레이션 후 latency 증가 | 낮 | LangGraph 오버헤드 미미 (보고됨), 회귀 측정 |
| LangGraph 버전 업데이트로 API 깨짐 | 낮 | `pyproject.toml` 버전 pin |

## 비고

- 본 REQ 는 챔피언 제안서 "AI Layer — LangGraph" 의 직접 후속
- Sprint 11 결과물 (AgentRunner) 은 폐기 대신 LangGraph 노드 정의의 시드로 재활용
- Sprint 13 진입 시 PM 분석 문서 (PM-15) 별도 작성
