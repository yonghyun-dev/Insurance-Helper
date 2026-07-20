"""프롬프트 버전 관리 로더 (하네스 5) — prompts/v1 정합 검증."""

from __future__ import annotations

import pytest
from app.infrastructure.llm.prompts import available_prompts, load_prompt

# 코드가 참조하는 프롬프트 전체 목록 — 파일 누락 시 여기서 즉시 실패
_REQUIRED = ["agent", "assessment", "explanation", "help", "intent", "next_question"]


class TestPromptLoading:
    def test_all_required_prompts_exist(self):
        assert available_prompts("v1") == _REQUIRED

    @pytest.mark.parametrize("name", _REQUIRED)
    def test_prompt_nonempty_korean(self, name):
        text = load_prompt(name)
        assert len(text) > 100, f"{name} 프롬프트가 비정상적으로 짧음"
        assert any(k in text for k in ("당신은", "너는", "다음"))  # 한국어 지시문

    def test_unknown_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("no_such_prompt")

    def test_constants_wired_to_files(self):
        """llm 모듈 상수가 파일 본문과 동일 — 인라인 회귀 방지."""
        from app.domains.rag import langgraph_agent
        from app.domains.sessions import llm

        assert load_prompt("assessment") == llm._ASSESSMENT_SYSTEM
        assert load_prompt("intent") == llm._INTENT_SYSTEM
        assert load_prompt("agent") == langgraph_agent._SYSTEM_PROMPT
