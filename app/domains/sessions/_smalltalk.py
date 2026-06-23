"""app.domains.sessions._smalltalk

파일 경로: app/sessions/_smalltalk.py
목적: 사용자 메시지가 인사/잡담(small talk) 인 경우 LLM 호출 없이 결정적 환영 응답을 만든다.

설계 참고:
    - PM-18 § 결정 1 — 옵션 A (코드 규칙) 채택
    - LLM 호출 0, latency 0, 결정적 동작

사용처:
    `app/sessions/service.py:post_message` 진입부에서, 세션이 비어있고 (slots 빈 상태) 사용자
    입력이 small talk 일 때 `make_smalltalk_ask()` 결과를 그대로 반환.
"""

from __future__ import annotations

import re

from app.domains.sessions.schemas import AssistantAsk, SlotState

# ---------------------------------------------------------------------------
# 패턴
# ---------------------------------------------------------------------------

# 짧고 의미 있는 슬롯 정보가 거의 없는 인사/잡담 입력만 매칭.
# 부분 일치가 아니라 "전체 (공백 정규화 후)" 일치만 인정 — 회귀 방지.
# Ex: "안녕하세요 자동차 사고" 같은 입력은 매칭 안 됨 (뒤에 실 슬롯 정보).
_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p) for p in (
        r"^안녕(하세요|하셈)?[!?.~]*$",
        r"^반가워(요)?[!?.~]*$",
        r"^하이[!?.~]*$",
        r"^hi[!?.~]*$",
        r"^hello[!?.~]*$",
        r"^ㅎㅇ[!?.~]*$",
        r"^좋은\s?(아침|점심|저녁|밤|하루)(\s?(입니다|이에요))?[!?.~]*$",
        r"^테스트[!?.~]*$",
        r"^test[!?.~]*$",
    )
)


def is_smalltalk(text: str) -> bool:
    """입력이 인사/잡담 패턴에 정확히 매칭되면 True."""
    normalized = text.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return any(p.match(normalized) for p in _PATTERNS)


# ---------------------------------------------------------------------------
# 응답
# ---------------------------------------------------------------------------

# 친근하고 짧게. 두 단락으로 호흡. options 는 area 4개 (영문 X — 사용자가 보는 한글).
_GREETING_MESSAGE = (
    "안녕하세요!\n\n"
    "어떤 청구 상황이신지 자유롭게 말씀해 주세요.\n"
    "사고 분야(자동차·화재·상해)나 보험사 이름을 함께 알려주시면 더 정확하게 도와드릴 수 있어요."
)


def make_smalltalk_ask() -> AssistantAsk:
    """인사/잡담 입력에 대한 환영 ask 응답."""
    return AssistantAsk(
        type="ask",
        message=_GREETING_MESSAGE,
        expected_slots=["area"],
        options=["자동차", "화재", "사고질병", "모르겠습니다"],
    )


def should_apply(slots: SlotState, text: str) -> bool:
    """가드 적용 조건: 슬롯이 전부 비어있고 (첫 turn 의도) + small talk 패턴 매칭."""
    if not is_smalltalk(text):
        return False
    # 이미 area 가 채워졌다면 진행 중인 대화 — 인사로 끊지 않는다
    return slots.area is None
