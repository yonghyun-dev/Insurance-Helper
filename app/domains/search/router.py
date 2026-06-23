"""app.domains.search.router

파일 경로: app/search/router.py
목적: 약관 검색 HTTP 엔드포인트.

현재 상태:
    Sprint 1 — APIRouter 객체만 정의. 엔드포인트는 Sprint 2 에서 추가.

TODO (Sprint 2):
    - POST /search → service.similarity_search(SearchQuery) → SearchResponse
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/search", tags=["search"])

# Sprint 2 에서 엔드포인트 추가 예정. 현재는 의도적으로 빈 router.
