# 시스템 아키텍처

Sprint 1(데이터 적재 CLI) + Sprint 2~3(멀티턴 HTTP API)를 한 그림에 표시한다. 회색 점선 박스는 Sprint 2~3에서 추가되는 컴포넌트.

```mermaid
graph TD
    subgraph 입력
        RAW["data/raw/<br/>{보험사}/{영역}/{상품}/{버전}/*.pdf"]
    end

    subgraph "Sprint 1: 데이터 파이프라인 (CLI)"
        ING[ingest CLI]
        PRS["PDF Parser<br/>(pdfplumber + PyMuPDF)"]
        STR["Structure Recognizer<br/>(제N조/항/별표)"]
        CHK["Chunker<br/>(의미 단위)"]
        EMB[OpenAI Embedding<br/>text-embedding-3-small]
    end

    subgraph 저장소
        SQL[("SQLite<br/>app.db<br/>메타데이터")]
        CH[("Chroma<br/>insurance_clauses<br/>임베딩")]
    end

    subgraph "Sprint 2~3: 멀티턴 API"
        API[FastAPI]
        SESS["SessionStore<br/>인메모리 + TTL"]
        SVC[Assistant Service]
        LLM[OpenAI gpt-4o-mini]
        UI["웹 UI (Sprint 3)"]
    end

    RAW --> ING
    ING --> PRS --> STR --> CHK --> EMB
    CHK --> SQL
    EMB --> CH

    UI -.-> API
    API -.-> SESS
    API -.-> SVC
    SVC -.-> CH
    SVC -.-> SQL
    SVC -.-> LLM

    style UI stroke-dasharray: 5 5
    style API stroke-dasharray: 5 5
    style SESS stroke-dasharray: 5 5
    style SVC stroke-dasharray: 5 5
    style LLM stroke-dasharray: 5 5
```

요약:
- Sprint 1은 PDF → 청크 → SQLite + Chroma 로 적재하는 단방향 파이프라인.
- Sprint 2~3는 대화 세션을 메모리에 두고 Assistant Service가 Chroma 검색 + SQLite 메타 hydrate + LLM 호출로 응답.
- OpenAI는 임베딩(Sprint 1) + LLM(Sprint 2)에 모두 사용. 단일 API 키.
