"""app.domains.search

파일 경로: app/search/__init__.py
목적: Chroma 벡터 검색 어댑터.
"""

from app.domains.search.schemas import SearchFilters, SearchQuery, SearchResponse, SearchResultItem
from app.domains.search.service import (
    COLLECTION_NAME,
    count,
    delete_by_document,
    get_collection,
    similarity_search,
    upsert_chunks,
)

__all__ = [
    "COLLECTION_NAME",
    "SearchFilters",
    "SearchQuery",
    "SearchResponse",
    "SearchResultItem",
    "count",
    "delete_by_document",
    "get_collection",
    "similarity_search",
    "upsert_chunks",
]
