# 시퀀스 — 멀티턴 대화 (Sprint 2)

`POST /sessions/{id}/messages` 호출 시 어시스턴트가 정보 보강 질의(`ask`) 또는 최종 판단(`assessment`) 중 하나를 반환하는 흐름.

```mermaid
sequenceDiagram
    actor U as 사용자
    participant C as 클라이언트
    participant API as FastAPI
    participant SS as SessionStore
    participant LLM as OpenAI
    participant CH as Chroma
    participant DB as SQLite

    U->>C: "발목 골절로 입원했어요. 보험금?"
    C->>API: POST /sessions
    API->>SS: create_session(uuid, ttl=30m)
    SS-->>API: session
    API-->>C: 201 {session_id}

    C->>API: POST /sessions/{id}/messages {text}
    API->>SS: load session
    API->>LLM: extract_slots(history + text)
    LLM-->>API: partial slots {diagnosis, ...}
    API->>SS: update slots

    alt 필수 슬롯 부족
        API->>LLM: next_question(slots, missing)
        LLM-->>API: ask(message, expected_slots)
        API->>SS: status = gathering
        API-->>C: 200 {assistant.type=ask}
        C-->>U: 어시스턴트 질문 표시
        Note over C,API: 사용자 추가 응답 → 같은 흐름 반복
    else 필수 슬롯 충족
        API->>SS: status = analyzing
        API->>CH: similarity_search(query, filter=slots)
        CH-->>API: top-k chunks + meta
        API->>DB: hydrate citations(원문, 페이지)
        API->>LLM: generate_assessment(slots, chunks) with JSON Schema
        LLM-->>API: assessment(likelihood, satisfied, unsatisfied, citations)
        API->>SS: status = answered
        API-->>C: 200 {assistant.type=assessment, citations, disclaimer}
        C-->>U: 가능성 등급 + 인용 카드 표시
    end
```

요약:
- `extract_slots` 와 `next_question` 두 LLM function call로 정보 보강 루프를 만든다.
- 필수 슬롯이 다 차야 RAG 검색 → 최종 판단으로 넘어간다.
- 출력은 JSON Schema로 강제해 인용 누락을 방지한다.
