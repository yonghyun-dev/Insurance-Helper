"""tests.search.test_search_schemas

app/search/schemas.py 단위 테스트.

테스트 대상:
    - SearchFilters.to_filter: None 값 제외, 단일/다중 필터 생성
      (Sprint 12: to_chroma_where → to_filter 메서드명 변경 — backend 추상화)
"""

from __future__ import annotations

import pytest
from app.domains.search.schemas import SearchFilters, SearchQuery

# ===========================================================================
# SearchFilters.to_filter
# ===========================================================================


class TestSearchFiltersToFilter:
    """to_filter 동작 검증."""

    def test_all_none_returns_none(self):
        # 모든 필드 None → None 반환 (벡터 backend 전체 검색)
        filters = SearchFilters()
        assert filters.to_filter() is None

    def test_single_filter_returns_dict(self):
        # 단일 필터 → {"insurer_id": "hanwha"} 형태
        filters = SearchFilters(insurer_id="hanwha")
        result = filters.to_filter()
        assert result == {"insurer_id": "hanwha"}

    def test_multiple_filters_returns_all_set_fields(self):
        # 여러 필터 동시 설정 → 해당 필드 모두 포함
        filters = SearchFilters(insurer_id="hanwha", area="auto", doc_type="terms")
        result = filters.to_filter()
        assert result == {
            "insurer_id": "hanwha",
            "area": "auto",
            "doc_type": "terms",
        }

    def test_none_fields_excluded_from_result(self):
        # None 필드는 결과에서 제외
        filters = SearchFilters(insurer_id="samsung", area=None, doc_type="summary")
        result = filters.to_filter()
        assert result is not None
        assert "area" not in result
        assert result["insurer_id"] == "samsung"
        assert result["doc_type"] == "summary"

    def test_version_id_included_when_set(self):
        # version_id 가 int 이면 포함
        filters = SearchFilters(version_id=42)
        result = filters.to_filter()
        assert result == {"version_id": 42}

    def test_product_id_filter(self):
        # product_id 필터
        filters = SearchFilters(product_id="hanwha_auto_standard")
        result = filters.to_filter()
        assert result == {"product_id": "hanwha_auto_standard"}

    def test_all_filters_set(self):
        # 모든 필드 설정 → 5개 필드 모두 포함
        filters = SearchFilters(
            insurer_id="ins",
            area="auto",
            product_id="prod",
            version_id=1,
            doc_type="terms",
        )
        result = filters.to_filter()
        assert result is not None
        assert len(result) == 5

    def test_zero_version_id_included(self):
        # version_id = 0 도 유효한 값으로 포함 (None 이 아니므로)
        filters = SearchFilters(version_id=0)
        result = filters.to_filter()
        # 0 은 falsy 이나 exclude_none 이므로 포함되어야 함
        assert result is not None
        assert "version_id" in result


# ===========================================================================
# SearchQuery 유효성 검증
# ===========================================================================


class TestSearchQuery:
    """SearchQuery 유효성 검증."""

    def test_valid_query_created(self):
        q = SearchQuery(text="보험금 지급 기준")
        assert q.text == "보험금 지급 기준"
        assert q.top_k == 8  # 기본값

    def test_empty_text_raises_validation_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SearchQuery(text="")

    def test_top_k_boundary_values(self):
        # top_k 경계값: 1 (최소), 50 (최대)
        q_min = SearchQuery(text="쿼리", top_k=1)
        q_max = SearchQuery(text="쿼리", top_k=50)
        assert q_min.top_k == 1
        assert q_max.top_k == 50

    def test_top_k_over_max_raises_error(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SearchQuery(text="쿼리", top_k=51)

    def test_filters_default_is_empty(self):
        q = SearchQuery(text="쿼리")
        # 기본 필터는 모든 필드 None
        assert q.filters.to_filter() is None
