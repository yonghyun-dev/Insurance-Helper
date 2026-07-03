"""tests.claims.test_claims_service

app/domains/claims/service.py 단위 테스트 — Sprint 22 (규칙 기반 체크리스트/요약/접수).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.domains.claims import service as cs
from app.domains.sessions.schemas import (
    AssistantAssessment,
    Citation,
    Session,
    SlotState,
)


def _session(**slot_kw) -> Session:
    return Session(
        session_id="s1abcd",
        created_at=datetime.now(UTC),
        last_activity_at=datetime.now(UTC),
        slots=SlotState(**slot_kw),
    )


class TestChecklist:
    def test_common_always_present(self):
        ids = {i.id for i in cs.build_checklist(SlotState()).items}
        assert {"claim_form", "id_copy", "bankbook"} <= ids

    def test_accident_disease_docs(self):
        ids = {i.id for i in cs.build_checklist(SlotState(area="accident_disease")).items}
        assert "diagnosis" in ids and "receipt_detail" in ids

    def test_hospitalization_adds_admission_cert(self):
        ids = {
            i.id
            for i in cs.build_checklist(
                SlotState(area="accident_disease", hospitalization_days=3)
            ).items
        }
        assert "admission_cert" in ids

    def test_no_hospitalization_no_admission(self):
        ids = {
            i.id
            for i in cs.build_checklist(
                SlotState(area="accident_disease", hospitalization_days=0)
            ).items
        }
        assert "admission_cert" not in ids

    def test_required_flag_on_common(self):
        items = cs.build_checklist(SlotState()).items
        assert all(i.required for i in items if i.id in {"claim_form", "id_copy", "bankbook"})


class TestSummary:
    def test_summary_without_assessment(self):
        sm = cs.build_summary(
            _session(area="accident_disease", insurer="한화손해보험", product="실손의료보험")
        )
        assert sm.insurer == "한화손해보험"
        assert sm.product == "실손의료보험"
        assert sm.likelihood is None
        assert sm.satisfied == [] and sm.next_steps == []
        assert len(sm.checklist) >= 3

    def test_summary_with_assessment(self):
        s = _session(area="accident_disease", insurer="삼성화재")
        s.last_assessment = AssistantAssessment(
            likelihood="높음",
            summary="청구 가능성이 높은 것으로 확인됩니다.",
            satisfied=["진단서 확보"],
            unsatisfied=["영수증 미제출"],
            citations=[
                Citation(
                    chunk_id="c1",
                    insurer="삼성화재",
                    product="실손보험",
                    version="2026",
                    doc_type="terms",
                    clause="제1조",
                    sub_no=None,
                    text="보장 내용 본문",
                    page=1,
                )
            ],
            next_steps=["진단서 제출", "영수증 첨부"],
        )
        sm = cs.build_summary(s)
        assert sm.likelihood == "높음"
        assert sm.satisfied == ["진단서 확보"]
        assert sm.unsatisfied == ["영수증 미제출"]
        assert sm.next_steps == ["진단서 제출", "영수증 첨부"]


class TestSubmit:
    def test_receipt_shape(self):
        r = cs.submit_claim(_session(insurer="한화손해보험"))
        assert r.receipt_no.startswith("CLM-")
        assert r.status == "접수완료"
        assert r.insurer == "한화손해보험"
        assert r.estimated_days == 5
        assert "접수" in r.message

    def test_receipt_no_insurer(self):
        r = cs.submit_claim(_session())
        assert r.insurer is None
        assert "보험사" in r.message
