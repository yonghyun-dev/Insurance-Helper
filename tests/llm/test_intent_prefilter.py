"""classify_intent 결정론 프리필터 범위 검증 (PM-43 이후).

정책: **수집 단계(answered=False)에서 구체 슬롯이 있으면** LLM 없이 진단 흐름 확정.
판정 완료(answered=True) 후의 '재판정 vs 설명' 구분은 정규식 땜질을 제거하고
LLM 분류기(intent.md 규칙)에 맡긴다. 그래서 answered 경로는 전부 LLM 을 탄다.

sessions conftest 는 classify_intent 를 스텁으로 고정하므로 실함수 검증은 여기서 한다.
`_get_client` 를 예외로 막아 '프리필터가 LLM 호출 전에 반환했는가'를 판별한다.
"""

from __future__ import annotations

import pytest
from app.domains.sessions import llm
from app.domains.sessions.schemas import SlotState


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    def boom():
        raise RuntimeError("LLM 호출됨 — 프리필터가 반환하지 않음")

    monkeypatch.setattr(llm, "_get_client", boom)


class TestGatheringPrefilter:
    """수집 단계 — 구체 슬롯 존재 시 결정론으로 claim_diagnosis (LLM 미호출)."""

    def test_diagnosis_slot_shortcircuits(self):
        assert llm.classify_intent("아무말", SlotState(diagnosis="충수염")) == "claim_diagnosis"

    def test_hospitalization_slot_shortcircuits(self):
        assert llm.classify_intent("x", SlotState(hospitalization_days=3)) == "claim_diagnosis"


class TestAnsweredGoesToLlm:
    """판정 완료 후에는 재판정·설명 모두 LLM 분류기로 (정규식 프리필터 제거됨)."""

    def test_reassess_request_reaches_llm(self):
        s = SlotState(diagnosis="골절")
        with pytest.raises(RuntimeError):
            llm.classify_intent("그럼 이제 청구 가능성 알려주세요", s, answered=True)

    def test_explanation_reaches_llm(self):
        s = SlotState(diagnosis="골절")
        with pytest.raises(RuntimeError):
            llm.classify_intent("왜 판정이 중간이에요?", s, answered=True)
