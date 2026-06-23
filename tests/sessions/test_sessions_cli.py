"""tests.sessions.test_sessions_cli

app/cli/app.py chat 명령 + _render_assistant 단위 테스트.

테스트 대상:
    - chat --help: 도움말 출력 확인
    - _render_assistant ask 모드: message / options 출력 확인
    - _render_assistant assessment 모드: likelihood / summary / citations / disclaimer 출력 확인

mock 정책:
    - chat 명령은 typer.testing.CliRunner 사용
    - sessions.service 함수는 monkeypatch 로 교체
    - _render_assistant 는 rich Console 캡처로 출력 검증
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.domains.sessions.schemas import (
    AssistantAsk,
    AssistantAssessment,
    Citation,
)
from app.interfaces.cli.app import _render_assistant
from app.interfaces.cli.app import app as cli_app
from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# 픽스처 / 헬퍼
# ---------------------------------------------------------------------------


runner = CliRunner()


def _make_session_stub(session_id: str = "test-session-id"):
    stub = MagicMock()
    stub.session_id = session_id
    return stub


def _make_ask() -> AssistantAsk:
    return AssistantAsk(
        message="보험사 이름을 알려주세요.",
        expected_slots=["insurer"],
        options=["한화", "삼성"],
    )


def _make_assessment() -> AssistantAssessment:
    cite = Citation(
        chunk_id="c1",
        insurer="한화손해보험",
        product="개인용자동차보험",
        version="2026",
        doc_type="terms",
        clause="제3조",
        sub_no="①",
        text="보험금 지급 기준 관련 약관 조항 내용입니다.",
        page=5,
    )
    return AssistantAssessment(
        likelihood="높음",
        summary="자동차 사고로 인한 보험금 청구 가능성이 높습니다.",
        satisfied=["사고 유형 확인"],
        unsatisfied=["증거 미제출"],
        citations=[cite],
        next_steps=["청구 서류 준비"],
        disclaimer="본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다.",
    )


# ===========================================================================
# chat --help
# ===========================================================================


class TestChatHelp:
    """chat 명령 도움말 출력 검증."""

    def test_chat_help_exits_zero(self):
        # --help → exit code 0
        result = runner.invoke(cli_app, ["chat", "--help"])
        assert result.exit_code == 0

    def test_chat_help_contains_description(self):
        # 도움말에 'chat' 관련 설명 포함
        result = runner.invoke(cli_app, ["chat", "--help"])
        output = result.output
        # 명령 설명 또는 Usage 포함
        assert "chat" in output.lower() or "Usage" in output


# ===========================================================================
# _render_assistant — ask 모드
# ===========================================================================


class TestRenderAssistantAsk:
    """_render_assistant ask 모드 출력 검증."""

    def _capture_render(self, assistant, *, status: str = "gathering", turn: int = 1) -> str:
        """_render_assistant 출력을 문자열로 캡처한다.

        `import app.interfaces.cli.app as cli_module` 은 app 패키지의 cli 서브모듈 내 app 속성
        (Typer 인스턴스)을 반환하므로, importlib 으로 모듈 객체를 명시적으로 가져온다.
        """
        import importlib
        import io

        from rich.console import Console

        buf = io.StringIO()
        cli_module = importlib.import_module("app.interfaces.cli.app")

        original_console = cli_module.console
        try:
            cli_module.console = Console(file=buf, highlight=False, markup=False)
            _render_assistant(assistant, status=status, turn=turn)
        finally:
            cli_module.console = original_console
        return buf.getvalue()

    def test_ask_mode_outputs_message(self):
        # ask 메시지가 출력에 포함됨
        ask = _make_ask()
        output = self._capture_render(ask)
        assert "보험사 이름을 알려주세요" in output

    def test_ask_mode_outputs_options_when_present(self):
        # options 가 있으면 출력에 포함
        ask = _make_ask()
        output = self._capture_render(ask)
        assert "한화" in output
        assert "삼성" in output

    def test_ask_mode_no_options_section_when_empty(self):
        # options 없으면 options 섹션 출력 안 함
        ask = AssistantAsk(
            message="사고 날짜를 알려주세요.",
            expected_slots=["incident_date"],
            options=[],
        )
        output = self._capture_render(ask)
        # 옵션이 없으므로 '옵션:' 텍스트 없음
        assert "옵션:" not in output

    def test_ask_mode_shows_turn(self):
        # 턴 번호가 출력에 포함
        ask = _make_ask()
        output = self._capture_render(ask, turn=3)
        assert "3" in output


# ===========================================================================
# _render_assistant — assessment 모드
# ===========================================================================


class TestRenderAssistantAssessment:
    """_render_assistant assessment 모드 출력 검증."""

    def _capture_render(self, assistant, *, status: str = "answered", turn: int = 2) -> str:
        import importlib
        import io

        from rich.console import Console

        buf = io.StringIO()
        cli_module = importlib.import_module("app.interfaces.cli.app")

        original_console = cli_module.console
        try:
            cli_module.console = Console(file=buf, highlight=False, markup=False)
            _render_assistant(assistant, status=status, turn=turn)
        finally:
            cli_module.console = original_console
        return buf.getvalue()

    def test_assessment_mode_outputs_likelihood(self):
        # likelihood 값이 출력에 포함
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "높음" in output

    def test_assessment_mode_outputs_summary(self):
        # summary 가 출력에 포함
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "자동차 사고로 인한 보험금" in output

    def test_assessment_mode_outputs_citation(self):
        # citation 정보 (insurer, product) 가 출력에 포함
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "한화손해보험" in output
        assert "개인용자동차보험" in output

    def test_assessment_mode_outputs_disclaimer(self):
        # disclaimer 가 출력에 포함
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "참고용" in output

    def test_assessment_mode_outputs_satisfied_items(self):
        # satisfied 항목 출력
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "사고 유형 확인" in output

    def test_assessment_mode_outputs_unsatisfied_items(self):
        # unsatisfied 항목 출력
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "증거 미제출" in output

    def test_assessment_mode_outputs_next_steps(self):
        # next_steps 출력
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "청구 서류 준비" in output

    def test_assessment_mode_outputs_citation_page(self):
        # 인용 page 번호 출력
        assessment = _make_assessment()
        output = self._capture_render(assessment)
        assert "5" in output  # page=5
