"""tests.rag.conftest

RAG 테스트 공통 픽스처.

- SlotState 샘플 (area 별)
- RetrievalResult 샘플 빌더
- rag_service 캐시 초기화 픽스처
"""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.rag.protocols import RetrievalResult
from app.domains.sessions.schemas import SlotState

# ---------------------------------------------------------------------------
# SlotState 샘플 빌더
# ---------------------------------------------------------------------------


def make_auto_slot(
    *,
    insurer: str = "한화손해보험",
    product: str = "개인용자동차보험",
    incident_type: str = "추돌",
    damage_type: str = "자차",
    incident_date: date | None = date(2026, 3, 15),
) -> SlotState:
    """auto 영역 SlotState."""
    return SlotState(
        area="auto",
        insurer=insurer,
        product=product,
        incident_date=incident_date,
        incident_type=incident_type,
        damage_type=damage_type,
    )


def make_fire_slot(
    *,
    loss_type: str = "전소",
    cause: str = "전기 합선",
    damaged_items: list[str] | None = None,
) -> SlotState:
    """fire 영역 SlotState."""
    return SlotState(
        area="fire",
        insurer="삼성화재",
        product="주택화재보험",
        loss_type=loss_type,
        cause=cause,
        damaged_items=damaged_items or ["가전제품"],
    )


def make_accident_disease_slot(
    *,
    diagnosis: str = "골절",
    hospitalization_days: int = 5,
) -> SlotState:
    """accident_disease 영역 SlotState."""
    return SlotState(
        area="accident_disease",
        insurer="현대해상",
        product="상해보험",
        diagnosis=diagnosis,
        hospitalization_days=hospitalization_days,
    )


def make_empty_slot() -> SlotState:
    """모든 슬롯이 비어 있는 SlotState."""
    return SlotState()


def make_retrieval_result(
    chunk_id: str = "chunk_001",
    text: str = "보험금 지급 기준 조항입니다.",
    score: float = 0.85,
    source: str = "vector",
    clause_no: str = "제1조",
) -> RetrievalResult:
    """RetrievalResult 샘플 생성."""
    return {
        "id": chunk_id,
        "text": text,
        "score": score,
        "metadata": {
            "clause_no": clause_no,
            "insurer_name": "한화손해보험",
            "page_start": 1,
        },
        "source": source,  # type: ignore[typeddict-item]
    }


# ---------------------------------------------------------------------------
# pytest 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def auto_slot() -> SlotState:
    return make_auto_slot()


@pytest.fixture()
def fire_slot() -> SlotState:
    return make_fire_slot()


@pytest.fixture()
def accident_slot() -> SlotState:
    return make_accident_disease_slot()


@pytest.fixture()
def empty_slot() -> SlotState:
    return make_empty_slot()


@pytest.fixture(autouse=False)
def clear_rag_caches():
    """각 테스트 후 rag.service 의 lru_cache singleton 초기화.

    Sprint 12: vectorstore.clear_cache() 추가 — PgVectorAdapter/ChromaAdapter
    lru_cache 오염 방지.
    """
    import app.domains.rag.service as rag_service
    import app.domains.rag.vectorstore as vectorstore

    rag_service.clear_caches()
    vectorstore.clear_cache()
    yield
    rag_service.clear_caches()
    vectorstore.clear_cache()
