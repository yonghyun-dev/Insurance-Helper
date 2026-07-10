"""tests.sessions.test_freeform_qa

PM-34 — 자유 질의응답(실손 한정) 라우팅 + 응답 생성 회귀.

- classify_intent 프리필터 (구체 상황 슬롯 → LLM 미호출)
- post_message 의도 분기: general_qa → answer / out_of_domain → ask / 검색 0건 → ask
- _build_answer 방어: 환각 chunk_id 필터
"""

from __future__ import annotations

import pytest
from app.domains.sessions import llm
from app.domains.sessions.schemas import (
    AssistantAnswer,
    Citation,
    SlotState,
)
from app.domains.sessions.service import post_message
from app.domains.sessions.store import SessionStore
from app.infrastructure.core.exceptions import SchemaViolationError


@pytest.fixture
def isolated_store(monkeypatch) -> SessionStore:
    store = SessionStore(ttl_seconds=1800)
    monkeypatch.setattr("app.domains.sessions.service.get_session_store", lambda: store)
    monkeypatch.setattr("app.domains.sessions.store.get_session_store", lambda: store)
    return store


def _citation(chunk_id: str = "c1") -> Citation:
    return Citation(
        chunk_id=chunk_id,
        insurer="삼성화재",
        product="실손의료보험",
        version="2026",
        doc_type="terms",
        clause="제3조",
        sub_no=None,
        text="보상하지 않는 사항 관련 약관 조항입니다.",
        page=5,
    )


def _chunks() -> list[dict]:
    return [{
        "id": "c1",
        "text": "실손 보상하지 않는 사항입니다.",
        "score": 0.9,
        "metadata": {
            "insurer_id": "samsung", "insurer_name": "삼성화재",
            "product_id": "samsung_silson", "product_name": "실손의료보험",
            "version_label": "2026", "doc_type": "terms",
            "clause_no": "제3조", "sub_no": None, "page_start": 5,
        },
    }]


class TestClassifyIntentPrefilter:
    """구체 상황 슬롯이 있으면 LLM 없이 claim_diagnosis 확정."""

    def test_diagnosis_slot_shortcircuits(self):
        assert llm.classify_intent("아무말", SlotState(diagnosis="충수염")) == "claim_diagnosis"

    def test_hospitalization_slot_shortcircuits(self):
        assert llm.classify_intent("x", SlotState(hospitalization_days=3)) == "claim_diagnosis"

    def test_outpatient_slot_shortcircuits(self):
        assert llm.classify_intent("x", SlotState(outpatient_visits=2)) == "claim_diagnosis"


class TestPostMessageIntentRouting:
    """post_message 진입부 의도 분기 (classify_intent 는 conftest 기본 override)."""

    def test_general_qa_returns_answer(self, isolated_store, monkeypatch):
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.classify_intent", lambda *a, **kw: "general_qa"
        )
        monkeypatch.setattr(
            "app.domains.rag.vectorstore.get_vector_store",
            lambda: type("V", (), {"query": lambda self, q, top_k=8: _chunks()})(),
        )
        answer = AssistantAnswer(
            message="실손의료보험은 실제 의료비를 보상하는 보험으로 안내드립니다.",
            citations=[_citation()],
            related_questions=["비급여 자기부담률은 얼마인가요?"],
            needs_policy=True,
        )
        gen_called = []
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_explanation",
            lambda *a, **kw: gen_called.append(True) or answer,
        )

        session = isolated_store.create()
        resp = post_message(session.session_id, "실손이 뭐야?")

        assert resp.assistant.type == "answer"
        assert resp.assistant.citations[0].insurer == "삼성화재"
        assert resp.assistant.related_questions
        assert gen_called == [True]

    def test_out_of_domain_returns_ask(self, isolated_store, monkeypatch):
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.classify_intent",
            lambda *a, **kw: "out_of_domain",
        )
        session = isolated_store.create()
        resp = post_message(session.session_id, "파이썬 코드 짜줘")

        assert resp.assistant.type == "ask"
        assert "실손" in resp.assistant.message

    def test_general_qa_no_chunks_returns_ask(self, isolated_store, monkeypatch):
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.classify_intent", lambda *a, **kw: "general_qa"
        )
        monkeypatch.setattr(
            "app.domains.sessions.service.rag_service.retrieve_freeform",
            lambda text, top_k=8, insurer_id=None: [],
        )
        gen_called = []
        monkeypatch.setattr(
            "app.domains.sessions.service.llm.generate_explanation",
            lambda *a, **kw: gen_called.append(True),
        )

        session = isolated_store.create()
        resp = post_message(session.session_id, "알쏭달쏭한질문")

        assert resp.assistant.type == "ask"  # 검색 0건 → 재질문
        assert gen_called == []  # 설명 생성은 호출되지 않음


class TestBuildAnswer:
    """_build_answer 방어 — 환각 chunk_id 필터."""

    def test_filters_hallucinated_chunk_id(self):
        raw = {
            "message": "실손 관련 안내드립니다.",
            "citations": [
                {"chunk_id": "c1", "insurer": "삼성화재", "product": "실손의료보험",
                 "version": "2026", "doc_type": "terms", "clause": "제3조", "sub_no": None,
                 "text": "약관 본문입니다.", "page": 5},
                {"chunk_id": "HALLUCINATED", "insurer": "x", "product": "y",
                 "version": "2026", "doc_type": "terms", "clause": "제9조", "sub_no": None,
                 "text": "존재하지 않는 청크.", "page": 1},
            ],
            "related_questions": [], "needs_policy": False,
        }
        answer = llm._build_answer(raw, valid_chunk_ids={"c1"})
        assert len(answer.citations) == 1
        assert answer.citations[0].chunk_id == "c1"

    def test_all_hallucinated_raises(self):
        raw = {
            "message": "안내드립니다.",
            "citations": [
                {"chunk_id": "GHOST", "insurer": "x", "product": "y", "version": "2026",
                 "doc_type": "terms", "clause": "제1조", "sub_no": None,
                 "text": "가짜 청크.", "page": 1},
            ],
            "related_questions": [], "needs_policy": False,
        }
        with pytest.raises(SchemaViolationError):
            llm._build_answer(raw, valid_chunk_ids={"c1"})
