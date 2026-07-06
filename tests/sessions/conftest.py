"""tests.sessions 공통 픽스처.

PM-34 — post_message 진입부에 classify_intent(LLM) 라우팅이 추가되면서, 기존
funnel(claim_diagnosis)을 검증하던 테스트들이 실제 LLM 분류에 의존하지 않도록
classify_intent 기본값을 claim_diagnosis 로 고정한다. 자유 질의(general_qa/
out_of_domain) 테스트는 이 setattr 를 다시 덮어써 override 한다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_intent_claim_diagnosis(monkeypatch):
    """모든 sessions 테스트의 classify_intent 기본을 claim_diagnosis 로 고정."""
    monkeypatch.setattr(
        "app.domains.sessions.service.llm.classify_intent",
        lambda *a, **kw: "claim_diagnosis",
    )
