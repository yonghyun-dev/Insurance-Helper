"""tests.sessions.test_comparison — 다중 실손 판정+비교 오케스트레이션 (Sprint 33 L3)."""

from __future__ import annotations

from datetime import date

import pytest
from app.domains.sessions.schemas import AssistantAssessment, Citation, PolicyRef, SlotState
from app.domains.sessions.service import post_message
from app.domains.sessions.store import SessionStore


@pytest.fixture
def isolated_store(monkeypatch) -> SessionStore:
    store = SessionStore(ttl_seconds=1800)
    monkeypatch.setattr("app.domains.sessions.service.get_session_store", lambda: store)
    monkeypatch.setattr("app.domains.sessions.store.get_session_store", lambda: store)
    return store


def _full_slots() -> SlotState:
    return SlotState(
        area="accident_disease", insurer="삼성화재", insurer_id="samsung",
        product="실손의료보험", incident_date=date(2026, 3, 15),
        diagnosis="골절", hospitalization_days=5, outpatient_visits=2,
    )


def _assessment(insurer: str) -> AssistantAssessment:
    return AssistantAssessment(
        likelihood="높음", summary=f"{insurer} 기준 판정입니다.",
        citations=[Citation(
            chunk_id=f"c-{insurer}", insurer=insurer, product="실손의료보험",
            version="2026", doc_type="terms", clause="제3조", sub_no=None,
            text="약관 조항 본문.", page=5,
        )],
    )


def _wire(monkeypatch):
    monkeypatch.setattr("app.domains.sessions.service.llm.extract_slots", lambda *a, **kw: {})
    monkeypatch.setattr(
        "app.domains.sessions.service.rag_service.retrieve",
        lambda *a, **kw: [{"id": "c1", "text": "약관", "score": 0.9, "metadata": {}}],
    )
    # generate_assessment 는 slots.insurer 에 따라 다른 요약 반환
    monkeypatch.setattr(
        "app.domains.sessions.service.llm.generate_assessment",
        lambda slots, chunks, coverage=None, notes=None, on_delta=None: _assessment(slots.insurer),
    )


class TestComparison:
    def test_two_policies_yield_comparison(self, isolated_store, monkeypatch):
        _wire(monkeypatch)
        session = isolated_store.create()
        session.slots = _full_slots()
        session.policies = [
            PolicyRef(insurer_id="samsung", insurer="삼성화재", product="실손의료보험",
                      policy_no="P1", generation=4),
            PolicyRef(insurer_id="hyundai", insurer="현대해상", product="실손의료보험",
                      policy_no="P2", generation=3),
        ]
        resp = post_message(session.session_id, "골절로 입원했어요")
        assert resp.assistant.type == "comparison"
        assert len(resp.assistant.policies) == 2
        insurers = {p.insurer for p in resp.assistant.policies}
        assert insurers == {"삼성화재", "현대해상"}
        # 세대별 자기부담률이 다르게 반영 (4세대 비급여 0.3 vs 3세대 0.2)
        by_ins = {p.insurer: p.deductible for p in resp.assistant.policies}
        assert by_ins["삼성화재"].non_covered_rate == 0.3
        assert by_ins["현대해상"].non_covered_rate == 0.2
        # 추천은 자기부담 낮은 3세대(현대) — policy_no P2
        assert resp.assistant.recommended_policy_no == "P2"

    def test_single_policy_stays_single_assessment(self, isolated_store, monkeypatch):
        _wire(monkeypatch)
        session = isolated_store.create()
        session.slots = _full_slots()
        session.policies = [
            PolicyRef(insurer_id="samsung", insurer="삼성화재", product="실손의료보험",
                      policy_no="P1", generation=4),
        ]
        resp = post_message(session.session_id, "골절로 입원했어요")
        assert resp.assistant.type == "assessment"  # 단일 → 하위호환

    def test_no_policies_stays_single(self, isolated_store, monkeypatch):
        _wire(monkeypatch)
        session = isolated_store.create()
        session.slots = _full_slots()
        resp = post_message(session.session_id, "골절로 입원했어요")
        assert resp.assistant.type == "assessment"

    def test_per_policy_citations_carried(self, isolated_store, monkeypatch):
        _wire(monkeypatch)
        session = isolated_store.create()
        session.slots = _full_slots()
        session.policies = [
            PolicyRef(insurer_id="samsung", insurer="삼성화재", product="실손의료보험",
                      policy_no="P1", generation=4),
            PolicyRef(insurer_id="hyundai", insurer="현대해상", product="실손의료보험",
                      policy_no="P2", generation=2),
        ]
        resp = post_message(session.session_id, "골절로 입원했어요")
        for p in resp.assistant.policies:
            assert p.assessment.citations[0].insurer == p.insurer
