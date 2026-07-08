"""tests.sessions.test_coverage_integration

PM-35 Phase 2 — post_message 진단 경로가 심볼릭 보장 판정(coverage.evaluate)을
산정해 generate_assessment 에 grounding 으로 주입하는지 검증.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.sessions.schemas import AssistantAssessment, Citation, SlotState
from app.domains.sessions.service import post_message
from app.domains.sessions.store import SessionStore


@pytest.fixture
def isolated_store(monkeypatch) -> SessionStore:
    store = SessionStore(ttl_seconds=1800)
    monkeypatch.setattr("app.domains.sessions.service.get_session_store", lambda: store)
    monkeypatch.setattr("app.domains.sessions.store.get_session_store", lambda: store)
    return store


def _assessment() -> AssistantAssessment:
    return AssistantAssessment(
        likelihood="중간",
        summary="테스트용 요약 문장입니다.",
        citations=[
            Citation(
                chunk_id="c1", insurer="삼성화재", product="실손의료보험", version="2026",
                doc_type="terms", clause="제4조", sub_no=None, text="약관 조항 본문.", page=5,
            )
        ],
    )


def _full_slots(**kw) -> SlotState:
    base = dict(
        area="accident_disease", insurer="삼성화재", insurer_id="samsung",
        product="실손의료보험", incident_date=date(2026, 3, 15),
        diagnosis="골절", hospitalization_days=5, outpatient_visits=2,
    )
    base.update(kw)
    return SlotState(**base)


def _wire(monkeypatch, captured: dict):
    monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
    monkeypatch.setattr(
        "app.domains.sessions.service.rag_service.retrieve",
        lambda *a, **kw: [{"id": "c1", "text": "약관", "score": 0.9, "metadata": {}}],
    )

    def cap(slots, chunks, coverage=None):
        captured["coverage"] = coverage
        return _assessment()

    monkeypatch.setattr("app.domains.sessions.service.llm.generate_assessment", cap)


class TestCoverageGrounding:
    def test_cosmetic_purpose_yields_excluded_decision(self, isolated_store, monkeypatch):
        captured: dict = {}
        _wire(monkeypatch, captured)
        session = isolated_store.create()
        session.slots = _full_slots(purpose="cosmetic")

        post_message(session.session_id, "미용 목적 시술을 받았어요")

        assert captured["coverage"] is not None
        assert captured["coverage"]["outcome"] == "excluded"
        assert any(h["rule_id"] == "exc_cosmetic" for h in captured["coverage"]["hits"])

    def test_treatment_inpatient_yields_covered_decision(self, isolated_store, monkeypatch):
        captured: dict = {}
        _wire(monkeypatch, captured)
        session = isolated_store.create()
        session.slots = _full_slots()  # purpose None → 치료 목적, 입원

        post_message(session.session_id, "골절로 입원했어요")

        assert captured["coverage"]["outcome"] == "covered"

    def test_unknown_generation_flags_needs_generation(self, isolated_store, monkeypatch):
        captured: dict = {}
        _wire(monkeypatch, captured)
        session = isolated_store.create()
        session.slots = _full_slots(generation=None)

        post_message(session.session_id, "골절로 입원했어요")

        assert captured["coverage"]["needs_generation"] is True
