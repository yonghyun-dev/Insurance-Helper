"""app.domains.rag

파일 경로: app/rag/__init__.py
목적: RAG 검색 채널 (Vector / Graph / Hybrid) 통합 진입점 도메인.

설계 참조: docs/design/rag-architecture.md, docs/design/graph-schema.md

공개 API:
    - service.retrieve(slots, top_k, mode=None, react=None) → list[RetrievalResult]
    - protocols.Retriever (Protocol)
    - protocols.RetrievalResult (TypedDict)

원칙:
    - sessions.service 는 본 도메인의 service.retrieve 만 호출
    - 모드 라우팅 + graceful fallback (Neo4j 다운→vector) 은 service.retrieve 책임
    - LangChain 의존은 본 도메인 내부에서만 import (다른 도메인 무변경)
"""
