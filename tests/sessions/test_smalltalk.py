"""tests.sessions.test_smalltalk

PM-18 — small talk 가드 회귀.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from app.domains.sessions import _smalltalk
from app.domains.sessions.schemas import SlotState


class TestIsSmalltalk:
    @pytest.mark.parametrize(
        "text",
        [
            "안녕",
            "안녕!",
            "안녕하세요",
            "안녕하세요!",
            "반가워요",
            "하이",
            "hi",
            "Hello",
            "ㅎㅇ",
            "좋은 아침",
            "좋은아침",
            "test",
            "테스트",
        ],
    )
    def test_detects_greetings(self, text: str):
        assert _smalltalk.is_smalltalk(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "안녕 자동차 사고가 났어요",
            "어제 빙판에 미끄러져 발목 골절로 입원했어요",
            "한화손해보험 자동차보험인데요",
            "보험사가 어디인가요",
            "",
        ],
    )
    def test_does_not_match_real_inquiries(self, text: str):
        assert _smalltalk.is_smalltalk(text) is False


class TestShouldApply:
    def test_applies_when_slots_empty(self):
        assert _smalltalk.should_apply(SlotState(), "안녕") is True

    def test_skips_when_area_already_set(self):
        slots = SlotState(area="accident_disease")
        assert _smalltalk.should_apply(slots, "안녕") is False

    def test_skips_when_not_smalltalk(self):
        assert _smalltalk.should_apply(SlotState(), "발목 골절 청구") is False


class TestMakeSmalltalkAsk:
    def test_returns_greeting_with_insurer_options(self):
        ask = _smalltalk.make_smalltalk_ask()
        assert ask.type == "ask"
        assert "안녕하세요" in ask.message
        assert "\n\n" in ask.message  # 문단 호흡
        assert ask.expected_slots == ["insurer"]
        # 실손 전용 — 5개 손보사 (자동차/화재 없음)
        assert "삼성화재" in ask.options
        assert "자동차" not in ask.options and "화재" not in ask.options


class TestPostMessageSmalltalkGuard:
    """service.post_message 진입부에서 small talk 가드가 LLM 우회하는지."""

    def test_greeting_bypasses_llm_extract_and_next_question(self):
        from app.domains.sessions import service

        with (
            patch("app.domains.sessions.llm.extract_slots") as m_extract,
            patch("app.domains.sessions.llm.next_question") as m_next,
        ):
            session, first = service.create_session(initial_message="안녕")

        assert first is not None
        assert first.assistant.type == "ask"
        assert "안녕하세요" in first.assistant.message
        m_extract.assert_not_called()
        m_next.assert_not_called()

    def test_real_inquiry_does_not_trigger_guard(self):
        """일반 청구 질문은 평소대로 LLM 분기 — small talk 가드 영향 없음."""
        from app.domains.sessions import llm as llm_mod
        from app.domains.sessions import service
        from app.domains.sessions.schemas import AssistantAsk

        fake_ask = AssistantAsk(
            type="ask",
            message="어떤 보험사 보험이신가요?",
            expected_slots=["insurer"],
            options=[],
        )
        with (
            patch.object(llm_mod, "extract_slots", return_value={"area": "accident_disease"}),
            patch.object(llm_mod, "next_question", return_value=fake_ask) as m_next,
        ):
            session, first = service.create_session(
                initial_message="다쳐서 병원에 갔어요"
            )

        assert first is not None
        assert first.assistant.type == "ask"
        m_next.assert_called_once()
