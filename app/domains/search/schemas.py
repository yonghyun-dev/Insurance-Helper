"""app.domains.search.schemas

파일 경로: app/search/schemas.py
목적: 약관 검색 입력·출력 pydantic 모델. CLI/HTTP 양쪽이 같은 계약을 사용한다.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    """벡터 backend metadata 필터에 매핑되는 검색 조건.

    Sprint 12 (REQ-13) — backend 추상화로 Chroma 명칭 제거.
    Chroma 와 pgvector 양쪽에 동일 dict 형식으로 전달된다.
    """

    insurer_id: str | None = None
    area: str | None = None
    product_id: str | None = None
    version_id: int | None = None
    doc_type: str | None = None

    def to_filter(self) -> dict[str, Any] | None:
        """None 값을 제외한 필터 dict 를 만든다.

        반환 형식은 Chroma where 절과 pgvector SQL WHERE 양쪽에 호환 (어댑터가 변환).
        """
        data = self.model_dump(exclude_none=True)
        return data or None


class SearchQuery(BaseModel):
    """검색 요청."""

    text: str = Field(..., min_length=1, description="자연어 질의")
    top_k: int = Field(default=8, ge=1, le=50, description="반환 개수")
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchResultItem(BaseModel):
    """검색 결과 1건."""

    id: str = Field(..., description="청크 UUID")
    text: str = Field(..., description="청크 본문")
    score: float = Field(..., ge=0.0, le=1.0, description="유사도 (1 - cosine distance)")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """검색 응답 (HTTP 호환)."""

    query: str
    items: list[SearchResultItem]
    total: int = Field(..., ge=0)
