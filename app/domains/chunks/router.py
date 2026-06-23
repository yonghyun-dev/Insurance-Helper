"""app.domains.chunks.router

파일 경로: app/chunks/router.py
목적: 약관 청크 HTTP 엔드포인트.

현재 상태:
    Sprint 1 — APIRouter 객체만 정의. 엔드포인트는 Sprint 2 에서 추가.

TODO (Sprint 2):
    - GET /documents/{document_id}/chunks  → service.list_chunks
    - GET /chunks/{chunk_id}               → 청크 단건 조회 (인용 원문)
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/chunks", tags=["chunks"])

# Sprint 2 에서 엔드포인트 추가 예정. 현재는 의도적으로 빈 router.
