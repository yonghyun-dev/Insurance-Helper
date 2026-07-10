"""app.domains.sessions.llm

파일 경로: app/sessions/llm.py
목적: OpenAI-호환 Chat Completions + Function Calling / Structured Outputs 어댑터.
      (Sprint 16 1a — 추론 클라이언트/모델은 app.infrastructure.llm.client 중앙 팩토리에 위임. provider=upstage(Solar) 기본)

함수 3종 (api-spec.md § Sprint 2 디테일 확정):
    - extract_slots(history, user_msg, current_slots) -> dict (갱신할 슬롯)
        Function Calling, tool_choice 로 강제
    - next_question(slots, missing) -> AssistantAsk
        Function Calling, expected_slots 는 SlotState 필드 enum 강제
    - generate_assessment(slots, chunks) -> AssistantAssessment
        Structured Outputs (response_format=json_schema, strict=True)

설계 메모:
    - 모델: 추론 provider 의 effective_llm_model via get_chat_model() (기본 Upstage solar-pro2)
    - 온도: extract/next_question 0.0 (재현성), generate 0.2 (자연스러움)
    - 재시도: tenacity 3회 (네트워크 일시 오류), 응답 schema 위반은 별도 1회 재시도
    - missing 슬롯 계산은 서비스 레이어 책임 — 본 모듈은 LLM 호출만
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import openai
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.domains.sessions.schemas import (
    AssistantAnswer,
    AssistantAsk,
    AssistantAssessment,
    Citation,
    Message,
    SlotState,
)
from app.infrastructure.core.exceptions import LLMError, SchemaViolationError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.llm.client import get_chat_client, get_chat_model

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 클라이언트
# ---------------------------------------------------------------------------


def _get_client() -> OpenAI:
    """추론 LLM 클라이언트 — 중앙 팩토리(app.infrastructure.llm.client)에 위임.

    제품 추론은 Upstage Solar 전용(provider=upstage 기본), OpenAI 폴백 없음.
    이 심볼명은 유지한다 — 테스트가 본 함수를 패치한다. 캐시는 팩토리가 담당.
    """
    return get_chat_client()


# ---------------------------------------------------------------------------
# 공통 - tool 정의 + 메시지 변환
# ---------------------------------------------------------------------------


_SLOT_FIELD_ENUM = [
    # 공통
    "area", "insurer", "product", "version", "incident_date", "evidence",
    # accident_disease (실손 전용, PM-33 — auto/fire 필드 제거)
    "diagnosis", "hospitalization_days", "outpatient_visits",
    # Sprint 17 — 청구서 표준 필드 (필수 X, OCR/마이데이터 prefill 친화)
    "hospital", "diagnosis_code", "treatment_period",
    "policy_no", "claim_amount", "incident_location",
    # Sprint 17 — 자유 메타 (LLM 이 추출한 SlotState 매핑 외 정보)
    "document_metadata",
]
"""SlotState 의 필드명. next_question.expected_slots enum 으로 사용.

Sprint 17 — 6 신규 필드 추가 (hospital/diagnosis_code/treatment_period/policy_no/claim_amount/incident_location).
이 필드들은 _compute_missing 정책에서 필수 X (메타 — 청구 가능성 판단 보조).
"""


def _messages_for_llm(
    history: list[Message],
    *,
    system_prompt: str,
    new_user_msg: str | None = None,
) -> list[dict[str, str]]:
    """history + system 프롬프트를 OpenAI chat messages 포맷으로 변환."""
    msgs: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for m in history:
        msgs.append({"role": m.role, "content": m.content})
    if new_user_msg is not None:
        msgs.append({"role": "user", "content": new_user_msg})
    return msgs


_RETRYABLE_EXC = (
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.InternalServerError,
)
"""tenacity 가 재시도할 예외 — 일시적 네트워크/한도 오류만. LLMError/SchemaViolationError 는 즉시 raise."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    reraise=True,
)
def _call_with_tool(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    tool_def: dict[str, Any],
    temperature: float,
) -> dict[str, Any]:
    """tool_choice 로 단일 함수 강제 호출. 함수 인자 JSON 을 dict 로 반환."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=[{"type": "function", "function": tool_def}],
        tool_choice={"type": "function", "function": {"name": tool_def["name"]}},
        temperature=temperature,
    )
    choice = response.choices[0]
    tool_calls = choice.message.tool_calls or []
    if not tool_calls:
        raise LLMError(
            f"LLM 이 함수 {tool_def['name']!r} 를 호출하지 않음 (응답 mode={choice.finish_reason})"
        )
    raw_args = tool_calls[0].function.arguments
    try:
        return json.loads(raw_args)
    except json.JSONDecodeError as exc:
        raise SchemaViolationError(
            f"함수 {tool_def['name']!r} 인자 JSON 파싱 실패: {exc} — args={raw_args[:200]}"
        ) from exc


# ---------------------------------------------------------------------------
# 1. extract_slots
# ---------------------------------------------------------------------------


_EXTRACT_SLOTS_TOOL = {
    "name": "extract_slots",
    "description": (
        "사용자 자연어 메시지에서 SlotState 의 필드를 추출/갱신한다. "
        "추론 불가능하거나 사용자가 언급하지 않은 필드는 포함하지 않는다."
    ),
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "slot_updates": {
                "type": "object",
                "additionalProperties": False,
                "description": "갱신할 슬롯 (필드명은 아래 properties 만 허용)",
                "properties": {
                    "area": {"type": "string", "enum": ["accident_disease"]},
                    "insurer": {"type": "string"},
                    "product": {"type": "string"},
                    "version": {"type": "string"},
                    "incident_date": {"type": "string", "description": "ISO YYYY-MM-DD 형식 권장"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "diagnosis": {"type": "string", "description": "진단명 (실손)"},
                    "hospitalization_days": {"type": "integer", "minimum": 0},
                    "outpatient_visits": {"type": "integer", "minimum": 0},
                    # Sprint 17 — 청구서 표준 필드 (필수 X, OCR/마이데이터 prefill 친화)
                    "hospital": {"type": "string", "description": "의료기관명 (진단서)"},
                    "diagnosis_code": {"type": "string", "description": "KCD-7 진단코드 (예: S82.5)"},
                    "treatment_period": {"type": "string", "description": "치료기간 자유 표현"},
                    "policy_no": {"type": "string", "description": "보험 증권번호"},
                    "claim_amount": {"type": "integer", "minimum": 0, "description": "청구금액 (원)"},
                    "incident_location": {"type": "string", "description": "사고 발생 장소"},
                    # 자유 메타 — 청구 판단 무관, 사용자 확인 카드 노출 전용
                    "document_metadata": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "SlotState 매핑 외 참고 메타 (예: 발급일, 의사명, 연락처)",
                    },
                },
            },
            # Sprint 6 — "모름"/"몰라" 명시 슬롯. _compute_missing 가 missing 에서 제외.
            "unknown_slots": {
                "type": "array",
                "items": {"type": "string", "enum": list(_SLOT_FIELD_ENUM)},
                "description": (
                    "사용자가 '모름'/'몰라'/'모르겠어' 등으로 명시한 슬롯명. "
                    "slot_updates 에는 넣지 말고 본 배열에만 추가."
                ),
            },
            # Sprint 35 — 세션 메모(2층 기억): 슬롯 필드에 안 담기지만 판정에 영향 줄 수
            # 있는 대화 사실을 짧은 한국어 메모로. 판정/QA 입력에 슬롯과 함께 전달된다.
            "session_notes": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "슬롯 필드에 담기지 않는 판정 관련 사실의 짧은 메모 (각 40자 이내). "
                    "예: '산재 아님(회사 밖 사고)', '교통사고 — 가해 차량 있음', "
                    "'본인 보험 미가입 진술', '수술 예정'. 이번 메시지에서 새로 확인된 "
                    "사실만. 없으면 빈 배열."
                ),
            },
        },
        "required": ["slot_updates"],
    },
}


def _extract_slots_system(today: date) -> str:
    """현재 날짜를 system 프롬프트에 박아 '어제'/'오늘' 같은 상대 표현을 ISO 로 변환."""
    from datetime import timedelta
    yesterday = (today - timedelta(days=1)).isoformat()
    return (
        "당신은 보험청구심사 어시스턴트의 슬롯 추출기다.\n"
        "사용자 자연어 메시지를 읽고 SlotState 의 필드 중 명시적으로 언급된 값만 추출한다.\n\n"
        "필수 규칙 (실손의료보험 전용):\n"
        "1. `area` 는 항상 `accident_disease` (입원/통원/진단/질병/상해/골절/수술/병원 단서).\n"
        "2. **사용자가 언급한 보험사명·상품명을 빠짐없이 `insurer`/`product` 로 추출**.\n"
        "   - 예: '삼성화재 실손의료보험' → insurer='삼성화재', product='실손의료보험'\n"
        "3. `incident_date` 는 ISO YYYY-MM-DD 형식. 오늘 = " + today.isoformat() + ", 어제 = " + yesterday + ".\n"
        "   - '지난주', '며칠 전' 같은 모호 표현은 추출 생략\n"
        "4. `diagnosis`(진단명, 예: 급성 충수염), `hospitalization_days`(입원 일수), "
        "`outpatient_visits`(외래 횟수) 를 명시 시 추출.\n"
        "6-a. **\"모름\"/\"몰라\"/\"모르겠어\"/\"잘 모르겠어\" 등 명시적 무지 표현** → 해당 슬롯을 `unknown_slots` 배열에 추가 "
        "(slot_updates 에는 넣지 않는다). 예: '보험사 잘 모르겠어' → unknown_slots=['insurer'].\n"
        "6-b. **부정 표현 → 정수 슬롯 0 으로 채움**. 예: '입원 안 했어' → hospitalization_days=0, "
        "'통원 없어' → outpatient_visits=0.\n"
        "7. 추론·추측·기본값 입력 금지. 모호하면 그 필드는 생략 (단 6-a, 6-b 는 명시이므로 적용).\n"
        "8. **session_notes**: 슬롯 필드에 담기지 않지만 청구 판정에 영향 줄 수 있는 사실을 "
        "짧은 메모로 추출 (예: '산재 아님' / '교통사고 — 가해 차량 있음' / '본인 보험 미가입 진술' / "
        "'의사가 수술 권유'). 이번 메시지에서 새로 확인된 것만, 각 40자 이내.\n\n"
        "허용 필드: " + ", ".join(_SLOT_FIELD_ENUM) + "."
    )


def extract_slots(history: list[Message], user_msg: str, current_slots: SlotState) -> dict[str, Any]:
    """사용자 메시지에서 슬롯 갱신값을 추출한다.

    Returns:
        갱신할 필드 dict. 호출자가 SlotState.model_copy(update=...) 로 머지.

    Raises:
        ConfigurationError: API 키 누락
        LLMError / SchemaViolationError: LLM 호출/응답 오류
    """
    client = _get_client()
    from datetime import date as _date
    system = (
        _extract_slots_system(_date.today())
        + f"\n\n현재 채워진 슬롯: {current_slots.model_dump_json(exclude_none=True)}"
    )
    messages = _messages_for_llm(history, system_prompt=system, new_user_msg=user_msg)
    try:
        args = _call_with_tool(
            client, model=get_chat_model(), messages=messages,
            tool_def=_EXTRACT_SLOTS_TOOL, temperature=0.0,
        )
    except (LLMError, SchemaViolationError):
        raise
    except Exception as exc:
        raise LLMError(f"extract_slots 호출 실패: {exc}") from exc

    updates = args.get("slot_updates") or {}
    if not isinstance(updates, dict):
        raise SchemaViolationError(f"slot_updates 가 dict 아님: {type(updates).__name__}")
    # SlotState 필드명만 통과시킨다 (LLM 이 모르는 필드 만들면 차단)
    filtered = {k: v for k, v in updates.items() if k in _SLOT_FIELD_ENUM}

    # Sprint 6 — "모름" 표시 슬롯 병합 (current + 새로 표시된 항목, dedupe)
    new_unknown = args.get("unknown_slots") or []
    if isinstance(new_unknown, list):
        valid_unknown = [s for s in new_unknown if s in _SLOT_FIELD_ENUM]
        if valid_unknown:
            merged = list(dict.fromkeys([*current_slots.unknown_slots, *valid_unknown]))
            filtered["unknown_slots"] = merged

    # Sprint 35 — 세션 메모: 슬롯이 아니므로 예약 키 `_notes` 로 반환 (호출자가 pop 후
    # Session.notes 에 누적 — SlotState 머지에 섞이지 않게 분리).
    raw_notes = args.get("session_notes") or []
    if isinstance(raw_notes, list):
        notes = [str(n).strip()[:60] for n in raw_notes if str(n).strip()]
        if notes:
            filtered["_notes"] = notes

    logger.info(
        "extract_slots: %d 필드 갱신 (LLM 응답 %d → 필터 %d) / unknown 추가 %d",
        len(filtered), len(updates), len(filtered),
        len(new_unknown) if isinstance(new_unknown, list) else 0,
    )
    return filtered


# ---------------------------------------------------------------------------
# 2. next_question
# ---------------------------------------------------------------------------


def _next_question_tool() -> dict[str, Any]:
    """expected_slots enum 을 동적 생성. additionalProperties=false 로 환각 차단."""
    return {
        "name": "next_question",
        "description": "사용자에게 가장 영향이 큰 미충족 슬롯 1~2개를 묻는 자연스러운 질문을 생성한다.",
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "message": {
                    "type": "string",
                    "description": "사용자에게 보낼 한국어 질문. 한 번에 1~2개 슬롯만",
                },
                "expected_slots": {
                    "type": "array",
                    "items": {"type": "string", "enum": _SLOT_FIELD_ENUM},
                    "description": "1~2개만 선택 (피로 회피)",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "선택지가 명확하면 제공. 반드시 사용자가 읽을 한국어 라벨. "
                        "예: insurer 면 ['삼성화재','현대해상','메리츠화재','한화손해보험','롯데손해보험']. "
                        "영문 코드(samsung/hyundai 등) 사용 금지. "
                        "없으면 빈 리스트."
                    ),
                },
            },
            "required": ["message", "expected_slots", "options"],
        },
    }


_NEXT_QUESTION_SYSTEM = (
    "당신은 보험청구심사 어시스턴트다. 사용자가 청구 시나리오를 자연어로 설명하는데 "
    "추가 정보가 필요하다. 미충족 슬롯 중 가장 영향이 큰 1~2개에 대해 자연스럽고 "
    "친절한 한국어 질문을 만들어라. 한 번에 너무 많이 묻지 말고, 사용자가 답하기 쉽게 "
    "선택지(options)가 명확하면 함께 제공해라. 단, 답이 자유로운 케이스는 options 를 빈 리스트로. "
    "\n\n"
    "**옵션 규칙 (강제, 실손의료보험 전용)**:\n"
    "- 슬롯 성격에 따라 options 제공 여부를 결정한다:\n"
    "  * **open-ended 슬롯 (자유 텍스트)**: options 는 반드시 **빈 배열 []** 로 한다. 선택지 강요 X.\n"
    "    - insurer, product, incident_date, diagnosis, evidence,\n"
    "      hospitalization_days, outpatient_visits\n"
    "- area 의 영문 코드(accident_disease)를 options 에 절대 사용하지 않는다.\n"
    "- 사용자가 '모르겠습니다' 선택 시 extract_slots 가 unknown_slots 에 머지 → partial 모드 자연 진입.\n"
    "- 자유 텍스트 슬롯에서도 사용자가 '모르겠습니다' 라고 직접 입력 가능 (extract_slots 가 인식).\n"
    "\n"
    "**톤 가이드 (강제)**:\n"
    "- 시스템이 능동적으로 안내한다 — 사용자가 답하기 쉽도록 짧고 직접적으로.\n"
    "- 친근하고 자연스러운 한국어. 형식체(\"~드리겠습니다\") 가급적 피하고 \"~해요\" / \"~알려주실래요?\" 정도 친근체.\n"
    "- 한 문장이 짧고 명확. 50자 넘으면 \\n 으로 줄바꿈해서 호흡을 준다.\n"
    "- 문단을 두 개로 나눌 때는 \\n\\n (UI 가 white-space: pre-wrap 으로 그대로 보존).\n"
    "- 너무 격식 차린 도입부(\"정확한 안내를 위해 ... 확인하고 싶습니다\") 금지. 바로 본론으로.\n"
    "- 사용자에게 책임 떠넘기지 않는다. \"다시 확인해 주세요\" / \"정확히 알려주세요\" 같은 명령형 금지.\n"
    "- 예시: \"어떤 보험사 보험이신가요?\\n알고 계신 정보가 있으면 알려주세요.\""
)


def next_question(slots: SlotState, missing: list[str]) -> AssistantAsk:
    """미충족 슬롯을 바탕으로 후속 질문을 생성한다.

    Args:
        slots: 현재 슬롯 상태 (LLM 에 컨텍스트로 제공)
        missing: 우선순위 정렬된 미충족 슬롯 필드명 리스트 (서비스 레이어가 계산)

    Returns:
        AssistantAsk pydantic 모델
    """
    client = _get_client()
    user_msg = (
        f"현재 채워진 슬롯: {slots.model_dump_json(exclude_none=True)}\n"
        f"미충족 슬롯(우선순위 순): {missing}\n"
        f"위 중 1~2개에 대해 자연스러운 한국어 질문을 만들어줘."
    )
    messages = _messages_for_llm(
        history=[], system_prompt=_NEXT_QUESTION_SYSTEM, new_user_msg=user_msg
    )
    try:
        args = _call_with_tool(
            client, model=get_chat_model(), messages=messages,
            tool_def=_next_question_tool(), temperature=0.0,
        )
    except (LLMError, SchemaViolationError):
        raise
    except Exception as exc:
        raise LLMError(f"next_question 호출 실패: {exc}") from exc

    try:
        ask = AssistantAsk.model_validate({
            "type": "ask",
            "message": args["message"],
            "expected_slots": args["expected_slots"],
            "options": args.get("options") or [],
        })
    except Exception as exc:
        raise SchemaViolationError(f"next_question 응답이 AssistantAsk 와 불일치: {exc}") from exc

    logger.info("next_question: expected=%s options=%d", ask.expected_slots, len(ask.options))
    return ask


# ---------------------------------------------------------------------------
# 3. generate_assessment (Structured Outputs strict)
# ---------------------------------------------------------------------------

_ASSESSMENT_RESPONSE_SCHEMA = {
    "name": "claim_assessment",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "likelihood", "summary", "satisfied", "unsatisfied",
            "citations", "next_steps", "disclaimer", "confidence",
        ],
        "properties": {
            "likelihood": {"type": "string", "enum": ["높음", "중간", "낮음"]},
            "summary": {"type": "string", "minLength": 10},
            "confidence": {
                "type": "string",
                "enum": ["partial", "full"],
                "description": (
                    "full: 필수 슬롯 완전 충족. "
                    "partial: 일부 슬롯 부족(unknown_slots 포함)으로 추정 기반 답변."
                ),
            },
            "satisfied": {"type": "array", "items": {"type": "string"}},
            "unsatisfied": {"type": "array", "items": {"type": "string"}},
            "citations": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "chunk_id", "insurer", "product", "version",
                        "doc_type", "clause", "sub_no", "text", "page",
                    ],
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "insurer": {"type": "string"},
                        "product": {"type": "string"},
                        "version": {"type": "string"},
                        "doc_type": {"type": "string", "enum": ["summary", "business", "terms"]},
                        "clause": {"type": "string"},
                        "sub_no": {"type": ["string", "null"]},
                        "text": {"type": "string", "minLength": 5},
                        "page": {"type": "integer", "minimum": 1},
                    },
                },
            },
            "next_steps": {"type": "array", "items": {"type": "string"}},
            "disclaimer": {"type": "string"},
        },
    },
    "strict": True,
}


_ASSESSMENT_SYSTEM = (
    "당신은 보험청구심사 어시스턴트다. 사용자 청구 시나리오와 관련 약관 청크를 받아 "
    "가능성 등급(높음/중간/낮음) + 충족·미충족 항목 + 근거 약관 조항 인용을 응답한다.\n\n"
    "규칙:\n"
    "1. 단정적 판단 금지 — '~가능성이 있습니다', '~로 추정됩니다' 등 어시스턴트 톤\n"
    "2. citations 는 입력된 청크의 chunk_id / 메타를 그대로 인용 (text 는 청크 본문 원본). "
    "   단 summary/satisfied/unsatisfied/next_steps 등 **본문 텍스트에는 chunk_id·내부 식별자·'청크' 표현 금지**\n"
    "3. citations.minItems=1 — 인용 없는 응답 금지\n"
    "4. disclaimer 는 정해진 면책 문구 사용\n"
    "5. **summary 는 3~4문장, 다음 구조를 지킨다 (Sprint 35 — '그래서 저 약관이 뭔데?'에 답할 것)**:\n"
    "   ① 결론 — 청구 가능성 등급과 이유 요지 한 문장.\n"
    "   ② **인용 조항 해설** — 화면에 함께 표시되는 근거 약관 원문이 '무엇을 정하고 있는지' 쉬운 말로 "
    "한 문장. 조항 번호·제목을 자연스럽게 언급한다. "
    "(예: \"근거로 표시된 제3조(보장종목별 보상내용)는 상해로 입원·통원 치료를 받으면 "
    "본인이 부담한 의료비를 보상한다고 정하고 있어요.\")\n"
    "   ③ 적용 — 사용자의 상황이 그 조항의 어떤 요건에 해당하는지(또는 왜 미충족인지) 연결.\n"
    "   ④ (partial 일 때만) 맨 끝 후속 한 줄.\n"
    "6. **confidence 판정**: 입력 slots 의 필수 슬롯이 모두 채워졌으면 'full', "
    "  unknown_slots 가 있거나 일부 슬롯이 None 이면 'partial'.\n"
    "6-b. **session_notes 준수**: 입력에 session_notes 가 있으면 이는 대화에서 확인된 추가 "
    "사실(슬롯 외 기억)이다. 판정·설명에 반영하고, 메모에 이미 있는 사실을 다시 묻거나 "
    "모순되게 말하지 않는다. (예: '산재 아님' 메모가 있으면 산재 여부를 묻지 않는다.)\n"
    "7. **입력 slots 에 insurer/insurer_id 가 없으면 = 가입 보험 미상(익명/미공유)**: 이때는 "
    "  인용된 청크가 특정 보험사(예: 메리츠화재) 것이더라도 **그 보험사를 '가입하신 보험사'로 지칭하거나 "
    "  '가입 보험이 확인되어'라고 말해서는 절대 안 된다.** 오직 '일반 실손 표준약관 기준'으로만 지칭하고 "
    "  (예: \"실손 표준약관 기준으로는 …\"), summary 끝에 \"가입하신 보험사·세대에 따라 세부 조건은 다를 수 "
    "  있어요. 내 보험으로 확인하면 더 정확해요.\" 취지를 한 줄 덧붙인다. **반대로 slots 에 insurer 가 있으면** "
    "  그 보험사 약관 기준으로 안내한다. 정보가 적어도 답변을 거부하지 않는다.\n"
    "\n"
    "**톤 가이드 (강제) — '답변 먼저, 질문은 선택' (Sprint 34)**:\n"
    "- 친절체 + 존댓말 (\"~안내드립니다\" / \"~드리겠습니다\"). 명령형/반말 금지. 짧고 쉬운 말(어르신도 이해).\n"
    "- 사용자에게 책임 떠넘기지 않는다. 시스템이 능동적으로 안내.\n"
    "- **어떤 경우에도 summary 첫 문장은 '결론(가능성)'으로 시작한다.** 정보가 부족해도 "
    "  헤지·사과·유보(예: '정보가 부족하지만…')를 앞세우지 말 것. 예: "
    "  \"발목 골절로 입원하신 경우 실손 청구 가능성은 높은 편입니다.\" 처럼 먼저 답한다.\n"
    "- 부족한 정보가 있으면 summary/응답의 **맨 끝에 딱 한 줄**, 반드시 **행동형**으로 덧붙인다 — "
    "  사용자가 채팅창에 무엇을 어떻게 입력하면 되는지 예시까지: "
    "  \"참고로 '계단에서 넘어진 사고예요'처럼 사고 경위를 알려주시면 바로 다시 확인해 드려요.\" "
    "  (여러 개를 나열하지 말고 가장 중요한 1개.)\n"
    "- **금지**: \"추가 정보가 있어야 정확한 판단이 가능합니다\" 처럼 무엇을 말하면 되는지 "
    "  알려주지 않고 끝나는 수동형 마무리.\n"
    "- **금지**: 사용자가 이미 밝힌 사실을 다시 묻는 것 — 입력 slots 나 시나리오에 입원 일수가 "
    "  있으면 '치료 유형(입원/통원)'을 묻지 말고, 이미 준 정보는 판정에 반영만 한다.\n"
    "- **교통사고**: 시나리오가 교통사고(차에 치임 등) 피해면, 자동차보험(대인배상)에서 처리된 "
    "  치료비는 실손 보상에서 제외되고 **본인이 실제 부담한 의료비만** 실손 대상임을 summary 나 "
    "  unsatisfied 에 한 줄 안내한다.\n"
    "- confidence='full' 이면 후속 요청 문장 자체를 생략한다.\n"
    "\n"
    "**결정론 판정(coverage_decision) 준수 (강제, PM-35)**: 입력에 coverage_decision 이 있으면 이는 "
    "약관 규칙에 근거한 결정론 판정이다. LLM 은 이를 **뒤집지 못하며** 자연어로 설명만 한다.\n"
    "- outcome='excluded': likelihood='낮음'. summary 에 hits[].rationale 를 반영하고, unsatisfied 에 "
    "  면책 사유를 적는다. 가능하면 hits[].clause_ref 에 해당하는 약관 조항을 citations 로 인용.\n"
    "- outcome='covered': likelihood='높음'(정보 충분) 또는 '중간'(일부 부족). deductible 이 있으면 "
    "  next_steps 나 summary 에 예상 자기부담·청구가능액을 반영한다.\n"
    "- outcome='insufficient_info': likelihood='중간' 이하로, missing 항목을 unsatisfied 에 안내한다.\n"
    "- needs_generation=true: '가입 세대에 따라 보장이 다를 수 있어 확인이 필요합니다' 취지를 unsatisfied 에 넣는다.\n"
)

_DEFAULT_DISCLAIMER = (
    "본 안내는 보험 약관·법령·표준 자료를 바탕으로 한 참고용 가이드이며, "
    "법적 효력이나 보험사의 최종 청구 가능 판단을 대체하지 않습니다. "
    "정확한 청구·지급 여부는 가입하신 보험사의 약관과 심사에 따릅니다."
)
# [확인 필요] Sprint 8 — 법무 검토 후 확정. PM 잠정안 (대국민 서비스 진입 기준).


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(_RETRYABLE_EXC),
    reraise=True,
)
def _partial_json_string(content: str, field: str) -> str | None:
    """스트리밍 중 누적된 JSON content 에서 특정 문자열 필드의 값을 '지금까지' 디코드한다.

    닫는 따옴표가 아직 안 왔으면 현재까지의 값을 반환(스트리밍 미리보기용). 없으면 None.
    """
    marker = f'"{field}"'
    i = content.find(marker)
    if i < 0:
        return None
    j = content.find(":", i + len(marker))
    if j < 0:
        return None
    k = content.find('"', j + 1)
    if k < 0:
        return None
    out: list[str] = []
    idx = k + 1
    n = len(content)
    while idx < n:
        ch = content[idx]
        if ch == "\\" and idx + 1 < n:
            nxt = content[idx + 1]
            out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "r": "\r"}.get(nxt, nxt))
            idx += 2
            continue
        if ch == '"':
            break  # 값 종료
        out.append(ch)
        idx += 1
    return "".join(out)


def _call_structured_stream(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    response_schema: dict[str, Any],
    temperature: float,
    on_delta: Callable[[str], None],
    stream_field: str,
) -> dict[str, Any]:
    """Structured Outputs 스트리밍 호출. stream_field 값이 늘어나는 만큼 on_delta 로 흘린다.

    실패 시 비스트리밍 _call_structured 로 폴백(부분 파싱 실패 방어).
    """
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": response_schema},
            temperature=temperature,
            stream=True,
        )
        content = ""
        sent = 0
        for chunk in stream:
            choices = getattr(chunk, "choices", None)
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None) or ""
            if not delta:
                continue
            content += delta
            val = _partial_json_string(content, stream_field)
            if val is not None and len(val) > sent:
                on_delta(val[sent:])
                sent = len(val)
        return json.loads(content)
    except Exception as exc:  # noqa: BLE001 — 폴백 보장(부분 파싱/스트림 오류)
        logger.warning("스트리밍 구조화 호출 실패 → 비스트리밍 폴백: %s", exc)
        return _call_structured(
            client, model=model, messages=messages,
            response_schema=response_schema, temperature=temperature,
        )


def _call_structured(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    response_schema: dict[str, Any],
    temperature: float,
) -> dict[str, Any]:
    """Structured Outputs 호출. response_format=json_schema, strict=True."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": response_schema},
        temperature=temperature,
    )
    content = response.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise SchemaViolationError(
            f"Structured Outputs JSON 파싱 실패: {exc} — content[:200]={content[:200]}"
        ) from exc


def generate_assessment(
    slots: SlotState,
    chunks: list[dict[str, Any]],
    coverage: dict[str, Any] | None = None,
    notes: list[str] | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> AssistantAssessment:
    """슬롯 + RAG 청크(+ 결정론 보장 판정)로 가능성 등급 + 인용 응답 생성.

    schema-violation 발생 시 1회 재시도 (Structured Outputs strict=True 가 보통 막아주지만
    드물게 통과하는 케이스를 대비한 방어). 두 번째 시도에 더 강한 reminder 를 system 에 추가.

    Args:
        slots: 충족된 SlotState
        chunks: search.service.similarity_search 결과 (id/text/score/metadata 포함)
        coverage: 심볼릭 룰 엔진(coverage.evaluate)의 결정론 판정(dict). 주어지면 LLM 은
            이 판정을 뒤집지 못하고 자연어로 설명만 한다(PM-35 뉴로심볼릭 grounding).

    Returns:
        AssistantAssessment pydantic 모델 (disclaimer 자동 부착, 가짜 chunk_id 자동 제거)

    Raises:
        LLMError: chunks 비어있음, OpenAI 호출 실패
        SchemaViolationError: schema 재시도 후에도 응답이 AssistantAssessment 에 맞지 않음
    """
    if not chunks:
        raise LLMError("generate_assessment: chunks 가 비어있음 (RAG 검색 결과 없음)")

    client = _get_client()
    chunks_for_llm = _prepare_chunks(chunks)
    valid_chunk_ids = {c["chunk_id"] for c in chunks_for_llm if c["chunk_id"]}
    payload: dict[str, Any] = {
        "slots": slots.model_dump(mode="json", exclude_none=True),
        "chunks": chunks_for_llm,
    }
    if coverage is not None:
        payload["coverage_decision"] = coverage
    if notes:
        # Sprint 35 — 세션 메모(대화에서 확인된 비슬롯 사실). 판정 반영 + 재질문 방지.
        payload["session_notes"] = notes
    # mode='json' 으로 date → ISO 문자열 직렬화 (json.dumps 가 date 를 모르기 때문)
    user_payload = json.dumps(payload, ensure_ascii=False)

    # Sprint 34 — insurer 미상(익명/미공유)이면 '표준약관 모드'를 결정론으로 강제한다.
    # 규칙7 프롬프트만으로는 인용 청크의 보험사명(예: 메리츠화재)을 '가입하신 보험사'로 오지칭하는
    # 누수가 관측됨 → 시스템 프롬프트에 강한 지시 블록을 코드로 주입(모델 추론에 의존하지 않음).
    standard_mode = not (slots.insurer or slots.insurer_id)

    last_error: SchemaViolationError | None = None
    for attempt in (1, 2):
        system = _ASSESSMENT_SYSTEM
        if standard_mode:
            system += (
                "\n\n[표준약관 모드 — 강제] 이번 입력에는 가입 보험사 정보가 없다(익명/미공유). "
                "따라서 인용된 청크가 특정 보험사(예: 메리츠화재·현대해상 등) 약관이더라도 절대로 "
                "그 보험사를 '가입하신 보험사'라고 부르거나 '가입 보험이 확인되어'라고 말하지 않는다. "
                "summary·satisfied·unsatisfied·next_steps 어디에서도 특정 보험사명을 '가입한 곳'으로 "
                "지칭 금지. 오직 '일반 실손 표준약관 기준'으로만 서술하고(예: \"실손 표준약관 기준으로는 …\"), "
                "summary 맨 끝에 \"가입하신 보험사·세대에 따라 세부 조건은 다를 수 있어요. 내 보험으로 "
                "확인하면 더 정확해요.\" 한 줄을 반드시 덧붙인다."
            )
        if attempt == 2:
            system += (
                "\n\n[재시도] 이전 응답이 응답 스키마를 위반했습니다. "
                "citations 의 chunk_id 는 입력된 청크 목록에 존재하는 값만 사용하고, "
                "모든 필수 필드(likelihood/summary/citations/disclaimer 등)를 빠짐없이 포함하세요."
            )
        messages = _messages_for_llm(history=[], system_prompt=system, new_user_msg=user_payload)
        try:
            # 첫 시도 + on_delta 있으면 스트리밍(summary 를 실시간 전송). 재시도는 비스트리밍.
            if on_delta is not None and attempt == 1:
                raw = _call_structured_stream(
                    client, model=get_chat_model(), messages=messages,
                    response_schema=_ASSESSMENT_RESPONSE_SCHEMA, temperature=0.2,
                    on_delta=on_delta, stream_field="summary",
                )
            else:
                raw = _call_structured(
                    client, model=get_chat_model(), messages=messages,
                    response_schema=_ASSESSMENT_RESPONSE_SCHEMA, temperature=0.2,
                )
        except SchemaViolationError as exc:
            last_error = exc
            logger.warning("generate_assessment schema 위반 (attempt %d): %s", attempt, exc)
            continue
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"generate_assessment 호출 실패: {exc}") from exc

        try:
            assessment = _build_assessment(raw, valid_chunk_ids=valid_chunk_ids, chunks=chunks)
        except SchemaViolationError as exc:
            last_error = exc
            logger.warning("generate_assessment 결과 검증 실패 (attempt %d): %s", attempt, exc)
            continue
        # 표준약관 모드 결정론 보정 — LLM 이 '표준약관 기준' 지칭을 생략하면(실관측)
        # 인용 라벨(특정 보험사)만 보여 혼동 소지 → summary 에 기준 명시를 코드로 보장.
        if standard_mode and "표준약관" not in assessment.summary:
            assessment.summary = (
                assessment.summary.rstrip()
                + " 이 안내는 특정 가입 보험이 아닌 일반 실손 표준약관 기준이에요."
            )
        return assessment

    # 두 번 모두 실패
    raise last_error or SchemaViolationError("generate_assessment: 알 수 없는 schema 위반")


def _prepare_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """RAG 청크를 LLM 입력 포맷으로 정제 (text + 메타만).

    인용 카드 표시 품질: 적재 메타의 insurer_name/product_name 이 코드로 저장돼 있어
    (감사 M-3), 여기서 한글명으로 교정한다. 실손 상품(*_silson)은 '실손의료보험'.
    """
    from app.domains.rag._slots import insurer_display_name

    out: list[dict[str, Any]] = []
    for c in chunks:
        meta = c.get("metadata") or {}
        product_id = meta.get("product_id") or ""
        product = (
            "실손의료보험"
            if str(product_id).endswith("_silson")
            else (meta.get("product_name") or product_id or "")
        )
        out.append({
            "chunk_id": c.get("id"),
            "insurer": insurer_display_name(meta.get("insurer_id"), meta.get("insurer_name")),
            "product": product,
            "version": meta.get("version_label") or "",
            "doc_type": meta.get("doc_type") or "terms",
            "clause": meta.get("clause_no") or "",
            "sub_no": meta.get("sub_no") or None,
            "text": c.get("text") or "",
            "page": meta.get("page_start") or 1,
        })
    return out


# 영문 슬롯 필드명 → 사용자 노출용 한글 라벨.
# LLM 이 unsatisfied/next_steps 에 "policy_no을(를)..." 처럼 영문 필드명을 그대로
# 적는 경우가 있어, 응답 텍스트에서 한글로 치환한다 (사용자 노출 품질).
_SLOT_LABELS: dict[str, str] = {
    "policy_no": "증권번호",
    "claim_amount": "청구 금액",
    "incident_location": "사고 장소",
    "incident_date": "사고 발생일",
    "diagnosis_code": "진단코드",
    "diagnosis": "진단명",
    "hospitalization_days": "입원 일수",
    "outpatient_visits": "외래 진료 횟수",
    "treatment_period": "치료 기간",
    "hospital": "병원명",
    "insurer": "보험사",
    "product": "상품명",
    "treatment_type": "치료 유형",
    "benefit_type": "급여 구분",
    "purpose": "청구 목적",
    "generation": "실손 세대",
    "benefit_split": "급여/비급여 구분",
    "area": "보험 영역",
}
# 긴 키 우선 치환 (diagnosis_code 를 diagnosis 보다 먼저) — 부분 치환 방지.
_SLOT_LABELS_ORDERED: list[str] = sorted(_SLOT_LABELS, key=len, reverse=True)


def _localize_slot_names(text: str) -> str:
    """응답 문자열의 영문 슬롯 필드명을 한글 라벨로 치환."""
    for key in _SLOT_LABELS_ORDERED:
        if key in text:
            text = text.replace(key, _SLOT_LABELS[key])
    return text


# Sprint 35 — 본문에 새는 내부 식별자 결정론 제거 (프롬프트 금지만으론 누수 실관측:
# "(citation: e8af124a-…, 5d7053cd-…)" 가 사용자 화면에 그대로 노출).
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_CITE_PAREN_RE = re.compile(
    r"[\(\[]\s*(?:citations?|chunk_id|근거|출처)\s*[:：][^\)\]]*[\)\]]", re.IGNORECASE
)


def _strip_internal_ids(text: str) -> str:
    """본문에서 chunk UUID·'(citation: …)' 류 내부 식별자 표기를 제거한다.

    근거 제시는 citations 필드(칩/좌측 패널)가 담당 — 본문은 자연어만.
    """
    text = _CITE_PAREN_RE.sub("", text)
    text = _UUID_RE.sub("", text)
    # 마크다운 각주 마커 "[^1]" — 렌더되지 않는 각주 참조가 본문에 노출(라이브 실관측)
    text = re.sub(r"\[\^?\d+\]", "", text)
    # 제거 후 잔여물 정리: 빈 괄호, 쉼표만 남은 괄호, 중복 공백
    text = re.sub(r"[\(\[]\s*[,;·\s]*[\)\]]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _clean_text(text: str) -> str:
    """본문 텍스트 공통 방어 — 내부 식별자 제거 + 슬롯명 한글화."""
    return _localize_slot_names(_strip_internal_ids(text))


def _build_assessment(
    raw: dict[str, Any],
    *,
    valid_chunk_ids: set[str],
    chunks: list[dict[str, Any]] | None = None,
) -> AssistantAssessment:
    """LLM 응답 dict 를 AssistantAssessment 로 변환 + 방어 처리.

    방어:
        - disclaimer 표준 면책 문구로 덮어쓰기
        - 입력 청크에 없는 chunk_id 는 환각 가능성 → 필터링
        - 필터 후 citations 가 비면 SchemaViolationError (재시도 트리거)

    Sprint 5 hydrate:
        - chunks 가 주어지면 chunk_id → metadata.document_id 매핑으로
          Citation 의 page_image_url + pdf_url 을 backend 가 채운다 (LLM 미관여, 환각 회피)
    """
    raw["disclaimer"] = _DEFAULT_DISCLAIMER

    raw_citations = raw.get("citations") or []
    filtered = [c for c in raw_citations if c.get("chunk_id") in valid_chunk_ids]
    dropped = len(raw_citations) - len(filtered)
    if dropped > 0:
        logger.warning(
            "generate_assessment: 입력에 없는 chunk_id 인용 %d건 제거 (남은 %d건)",
            dropped, len(filtered),
        )
    if not filtered:
        raise SchemaViolationError(
            "generate_assessment: citations 가 모두 입력 청크에 없는 chunk_id (환각)"
        )

    try:
        citations = [Citation.model_validate(c) for c in filtered]
        # Sprint 5 — backend hydrate (page_image_url + pdf_url)
        if chunks:
            citations = _hydrate_citation_urls(citations, chunks)
        assessment = AssistantAssessment(
            likelihood=raw["likelihood"],
            summary=_clean_text(raw["summary"]),
            satisfied=[_clean_text(s) for s in raw.get("satisfied", [])],
            unsatisfied=[_clean_text(s) for s in raw.get("unsatisfied", [])],
            citations=citations,
            next_steps=[_clean_text(s) for s in raw.get("next_steps", [])],
            confidence=raw.get("confidence", "full"),  # Sprint 6 — backward-compat default
            disclaimer=raw["disclaimer"],
        )
    except Exception as exc:
        raise SchemaViolationError(
            f"generate_assessment 응답이 AssistantAssessment 와 불일치: {exc}"
        ) from exc

    logger.info(
        "generate_assessment: likelihood=%s confidence=%s citations=%d",
        assessment.likelihood, assessment.confidence, len(assessment.citations),
    )
    return assessment


def _hydrate_citation_urls(
    citations: list[Citation], chunks: list[dict[str, Any]]
) -> list[Citation]:
    """Citation 에 PDF 페이지 캡처 URL + 원본 PDF URL 을 주입.

    chunks 의 metadata.document_id 로 SQLite documents.file_path 조회 → URL 생성.
    변환 실패 / 파일 부재 시 None 유지 (frontend 가 graceful 렌더).
    """
    from app.domains.documents import service as doc_service
    from app.infrastructure.core.database import session_scope
    from app.infrastructure.pdfimage import service as pdf_service

    # chunk_id → (document_id, page_start, page_end) 매핑
    chunk_meta: dict[str, tuple[int, int, int]] = {}
    doc_ids: set[int] = set()
    for c in chunks:
        cid = c.get("id")
        meta = c.get("metadata") or {}
        doc_id = meta.get("document_id")
        page = meta.get("page_start")
        page_end = meta.get("page_end")
        if cid and isinstance(doc_id, int) and isinstance(page, int):
            chunk_meta[cid] = (doc_id, page, page_end if isinstance(page_end, int) else page)
            doc_ids.add(doc_id)

    if not doc_ids:
        return citations

    # document_id → file_path batch lookup (N+1 회피)
    file_paths: dict[int, str] = {}
    try:
        with session_scope() as sql:
            for doc_id in doc_ids:
                fp = doc_service.find_file_path_by_id(sql, doc_id)
                if fp:
                    file_paths[doc_id] = fp
    except Exception as exc:
        logger.warning("Citation hydrate — SQLite lookup 실패: %s", exc)
        return citations

    hydrated: list[Citation] = []
    for cite in citations:
        meta = chunk_meta.get(cite.chunk_id)
        if not meta:
            hydrated.append(cite)
            continue
        doc_id, page_start, page_end = meta
        file_path = file_paths.get(doc_id)
        if not file_path:
            hydrated.append(cite)
            continue

        # Sprint 35 — 인용 페이지를 '하이라이트가 가장 진한 페이지'로 결정론 선택.
        # 여러 페이지에 걸친 청크는 시작 페이지에 인용 본문의 알맹이가 없을 수 있어
        # (사용자 실지적: 하이라이트가 안 보임) 청크 범위 내에서 매칭 면적이 최대인
        # 페이지를 고른다. 지연 상한을 위해 최대 4페이지만 스캔.
        best_page, best_rects = page_start, []
        try:
            from app.infrastructure.pdfimage import highlight as hl

            best_area = -1.0
            for p in range(page_start, min(page_end, page_start + 3) + 1):
                rects = hl.find_highlights(file_path, p, cite.text, cite.clause)
                area = sum(r["w"] * r["h"] for r in rects)
                if area > best_area + 1e-9:
                    best_page, best_rects, best_area = p, rects, area
        except Exception as exc:
            logger.warning("Citation hydrate — 하이라이트 실패 chunk=%s: %s", cite.chunk_id, exc)

        # 이미지 변환 (lazy, 캐시) — 선택된 페이지 기준
        page_url: str | None = None
        try:
            pdf_service.render_page(doc_id, best_page, file_path)
            page_url = pdf_service.page_image_url(doc_id, best_page)
        except Exception as exc:
            logger.warning(
                "Citation hydrate — page 이미지 실패 chunk=%s: %s", cite.chunk_id, exc
            )

        pdf_link = pdf_service.pdf_url(file_path)

        hydrated.append(
            cite.model_copy(
                update={
                    "page": best_page,
                    "page_image_url": page_url,
                    "pdf_url": pdf_link,
                    "highlights": best_rects if page_url else [],
                }
            )
        )
    return hydrated


# ---------------------------------------------------------------------------
# 3.5 자유 질의응답 (PM-34) — 의도 분류 + 실손 약관 근거 설명
# ---------------------------------------------------------------------------

_INTENT_SYSTEM = (
    "너는 실손의료보험 청구 어시스턴트의 라우터다. 사용자 입력을 아래 3가지 의도 중 "
    "하나로 분류하고 반드시 classify 함수를 호출한다.\n"
    "- claim_diagnosis: 본인의 구체적 청구 상황 서술/진단 요청 "
    "(예: '충수염으로 3일 입원했는데 청구돼?', '삼성화재 실손인데 도수치료 받았어'). "
    "본인 상황·사고·증상을 말하면 이것.\n"
    "- general_qa: 실손 제도·약관·보장에 대한 일반 지식 질문 "
    "(예: '실손이 뭐야?', '비급여 자기부담률 얼마야?', '도수치료 보장돼?', '실손에서 안 되는 게 뭐야?'). "
    "본인 상황 서술이 아니라 정보를 묻는 것.\n"
    "- out_of_domain: 실손·보험과 **완전히** 무관 (예: '파이썬 코드 짜줘', '오늘 날씨'). "
    "직전 안내에 대한 반응이나 보험 관련 진술은 절대 out_of_domain 이 아니다.\n"
    "애매하면 claim_diagnosis 로 분류한다(보수적 폴백).\n\n"
    "**보험 미가입/미상 진술**: '나 보험 없어', '가입 안 했어', '내 보험 잘 몰라' 는 "
    "out_of_domain 이 아니라 **general_qa** — 문맥에 이어 무보험/미상 상황에 맞는 안내가 필요하다.\n"
    "**직전 어시스턴트 안내가 주어지면** 사용자 입력을 그에 대한 답변/반응으로 해석해 분류한다.\n\n"
    "**판정 완료 후의 후속 입력 (판정 완료 여부: 예)**:\n"
    "- 직전 안내에 대한 설명·부연 요청은 general_qa "
    "(예: '자기부담금이 뭐예요?', '그 약관이 무슨 뜻이에요?', '왜 중간이에요?', '서류는 뭐가 필요해요?').\n"
    "- 상황 사실의 추가·정정은 claim_diagnosis — 재판정 "
    "(예: '사실 통원도 2번 했어요', '입원은 5일이었어요', '다른 보험으로도 봐줘').\n"
    "- 판정 후에는 설명 요청을 claim_diagnosis 로 잘못 보내면 같은 판정만 반복되므로, "
    "새 사실이 없으면 general_qa 를 우선한다."
)


def _classify_intent_tool() -> dict[str, Any]:
    return {
        "name": "classify",
        "description": "사용자 입력의 의도를 3분류",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "enum": ["claim_diagnosis", "general_qa", "out_of_domain"],
                    "description": "분류 결과",
                },
            },
            "required": ["intent"],
        },
    }


def classify_intent(
    text: str,
    slots: SlotState,
    answered: bool = False,
    last_assistant: str | None = None,
) -> str:
    """사용자 입력 의도 3분류. 실패/애매 시 'claim_diagnosis'(기존 진단 흐름) 폴백.

    규칙 프리필터: 구체 상황 슬롯(진단명·입원·외래)이 이미 채워졌으면 LLM 호출 없이
    진단 흐름 확정 — 진행 중(수집 단계) 대화를 QA 로 이탈시키지 않는다.

    Sprint 35 멀티턴: **판정 완료(answered) 후에는 프리필터를 우회**한다. 슬롯이 차 있다는
    이유로 모든 후속 질문('자기부담금이 뭐예요?')이 재판정으로 빨려 들어가 같은 판정 카드만
    반복되던 문제 — 판정 후엔 LLM 분류로 설명 요청(general_qa)과 사실 정정(재판정)을 가른다.
    """
    if not answered and (
        slots.diagnosis or slots.hospitalization_days or slots.outpatient_visits
    ):
        return "claim_diagnosis"

    client = _get_client()
    # Sprint 35 — 직전 어시스턴트 발화를 함께 줘 문맥상 답변("나 보험 없어")이
    # out_of_domain 으로 오분류돼 상용구가 대화를 끊는 문제를 막는다(실관측).
    ctx = f"직전 어시스턴트 안내: {last_assistant[:200]}\n" if last_assistant else ""
    user_msg = (
        f"판정 완료 여부: {'예 — 직전에 청구 가능성 판정을 안내했음' if answered else '아니오'}\n"
        f"{ctx}현재 슬롯: {slots.model_dump_json(exclude_none=True)}\n사용자 입력: {text}"
    )
    messages = _messages_for_llm(
        history=[], system_prompt=_INTENT_SYSTEM, new_user_msg=user_msg
    )
    try:
        args = _call_with_tool(
            client, model=get_chat_model(), messages=messages,
            tool_def=_classify_intent_tool(), temperature=0.0,
        )
        intent = args.get("intent")
        if intent in ("claim_diagnosis", "general_qa", "out_of_domain"):
            logger.info("classify_intent: %s", intent)
            return intent
    except Exception as exc:
        logger.warning("classify_intent 실패 → claim_diagnosis 폴백: %s", exc)
    return "claim_diagnosis"


_EXPLANATION_SYSTEM = (
    "당신은 실손의료보험 안내 어시스턴트다. 사용자의 일반 질문에 대해, 제공된 약관 청크를 "
    "근거로 설명한다.\n\n"
    "규칙:\n"
    "1. citations 는 입력된 청크의 chunk_id/메타를 그대로 인용 (최소 1건). 인용 없는 단정 금지.\n"
    "2. 약관 청크에서 확인되는 범위로만 답한다. 청크에 없는 내용은 추측하지 않는다.\n"
    "3. 단정 금지 — '~로 안내드립니다', '일반적으로 ~입니다' 어시스턴트 톤. 존댓말.\n"
    "4. message 는 2~5문장 한국어. 특정 가입 보험(insurer)이 확인되지 않으면 "
    "   '일반적인 실손의료보험 표준약관 기준'임을 밝힌다.\n"
    "5. related_questions: 사용자가 이어서 물어볼 만한 실손 관련 질문 최대 4개 (없으면 빈 배열).\n"
    "6. needs_policy: 정확한 답에 가입 약관 확인이 필요하면 true.\n"
    "7. **금지**: message 본문에 chunk_id·내부 식별자·'청크'/'청크_id' 같은 표현을 절대 쓰지 말 것. "
    "   근거는 citations 로만 제시하고, 본문은 사람이 읽는 자연어만.\n"
    "8. **실손 중복가입**: 사용자가 실손을 여러 개 가입해 '둘 다 받는지/어디가 이득인지' 물으면, "
    "   실손은 중복가입해도 실제 부담한 의료비 한도 내에서 여러 보험사가 '비례분담'해 지급하므로 "
    "   **이중(중복) 수령은 되지 않는다**고 정확히 안내한다(여러 개 유지 시 보험료만 이중일 수 있음). "
    "   '어느 회사가 더 이득'이라는 비교는 실손에선 성립하지 않음. (진단비 등 정액 특약은 별도로 각각 지급.)\n"
    "9. **대화 문맥(멀티턴)**: 이전 대화가 함께 주어지면, 질문이 직전 안내를 가리키는 경우 "
    "   ('그게 무슨 뜻이에요?', '왜 중간이에요?', '그 자기부담금은요?') 그 문맥에 이어서 답한다. "
    "   직전에 청구 가능성 판정을 안내했다면 그 판정 내용과 모순되지 않게 설명한다.\n"
    "10. **보험 미가입 진술**('나 보험 없어' 등): 상용구로 돌리지 말고 문맥에 맞게 안내한다 — "
    "   실손 청구는 가입자만 가능함을 부드럽게 알리고, 상황에 맞는 대안을 준다. 특히 대화가 "
    "   교통사고(차에 치임 등) 피해라면 **가해자 측 자동차보험(대인배상)으로 치료비 처리가 가능**하고 "
    "   본인 보험이 없어도 보상받을 수 있음을 안내한다.\n"
    "11. **교통사고 상식**: 교통사고 피해 치료비 중 자동차보험(대인배상)·산재보험에서 처리된 금액은 "
    "   실손에서 보상하지 않으며, 본인이 실제 부담한 의료비만 실손 보상 대상이다.\n"
    "12. **session_notes**: 입력에 session_notes 가 있으면 대화에서 확인된 사실이다 — "
    "   설명에 반영하고 그 사실을 다시 묻지 않는다.\n"
)

# citations 항목 스키마는 assessment 와 동일 (약관 인용 포맷 공유).
_EXPLANATION_RESPONSE_SCHEMA = {
    "name": "silson_explanation",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["message", "citations", "related_questions", "needs_policy"],
        "properties": {
            "message": {"type": "string", "minLength": 10},
            "citations": _ASSESSMENT_RESPONSE_SCHEMA["schema"]["properties"]["citations"],
            "related_questions": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 4,
            },
            "needs_policy": {"type": "boolean"},
        },
    },
    "strict": True,
}


def generate_explanation(
    question: str,
    chunks: list[dict[str, Any]],
    history: list[Message] | None = None,
    notes: list[str] | None = None,
    on_delta: Callable[[str], None] | None = None,
) -> AssistantAnswer:
    """실손 일반 질문 + RAG 청크로 약관 근거 설명(AssistantAnswer) 생성.

    generate_assessment 와 동일한 인용 검증/hydrate 방어를 적용하되, 가능성 등급 없이
    설명 텍스트 + 인용 + 후속 질문을 반환한다.

    Sprint 35 멀티턴: history(최근 대화)를 함께 전달해 "그게 무슨 뜻이에요?" 같은
    직전 안내를 가리키는 후속 질문에 문맥 있는 답을 만든다.

    Raises:
        LLMError: chunks 비어있음 / 호출 실패
        SchemaViolationError: 재시도 후에도 스키마 불일치
    """
    if not chunks:
        raise LLMError("generate_explanation: chunks 가 비어있음 (RAG 검색 결과 없음)")

    client = _get_client()
    chunks_for_llm = _prepare_chunks(chunks)
    valid_chunk_ids = {c["chunk_id"] for c in chunks_for_llm if c["chunk_id"]}
    recent = (history or [])[-8:]  # 직전 문맥만 — 프롬프트 비대 방지
    qa_payload: dict[str, Any] = {"question": question, "chunks": chunks_for_llm}
    if notes:
        qa_payload["session_notes"] = notes  # Sprint 35 — 대화에서 확인된 비슬롯 사실
    user_payload = json.dumps(qa_payload, ensure_ascii=False)

    last_error: SchemaViolationError | None = None
    for attempt in (1, 2):
        system = _EXPLANATION_SYSTEM
        if attempt == 2:
            system += (
                "\n\n[재시도] 이전 응답이 스키마를 위반했습니다. citations.chunk_id 는 "
                "입력된 청크에 존재하는 값만 사용하고 최소 1건을 포함하세요."
            )
        messages = _messages_for_llm(
            history=recent, system_prompt=system, new_user_msg=user_payload
        )
        try:
            if on_delta is not None and attempt == 1:
                raw = _call_structured_stream(
                    client, model=get_chat_model(), messages=messages,
                    response_schema=_EXPLANATION_RESPONSE_SCHEMA, temperature=0.2,
                    on_delta=on_delta, stream_field="message",
                )
            else:
                raw = _call_structured(
                    client, model=get_chat_model(), messages=messages,
                    response_schema=_EXPLANATION_RESPONSE_SCHEMA, temperature=0.2,
                )
        except SchemaViolationError as exc:
            last_error = exc
            logger.warning("generate_explanation schema 위반 (attempt %d): %s", attempt, exc)
            continue
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"generate_explanation 호출 실패: {exc}") from exc

        try:
            return _build_answer(raw, valid_chunk_ids=valid_chunk_ids, chunks=chunks)
        except SchemaViolationError as exc:
            last_error = exc
            logger.warning("generate_explanation 결과 검증 실패 (attempt %d): %s", attempt, exc)
            continue

    raise last_error or SchemaViolationError("generate_explanation: 알 수 없는 schema 위반")


def _build_answer(
    raw: dict[str, Any],
    *,
    valid_chunk_ids: set[str],
    chunks: list[dict[str, Any]] | None = None,
) -> AssistantAnswer:
    """LLM 응답 dict → AssistantAnswer + 방어(환각 chunk_id 필터 + URL hydrate)."""
    raw_citations = raw.get("citations") or []
    filtered = [c for c in raw_citations if c.get("chunk_id") in valid_chunk_ids]
    dropped = len(raw_citations) - len(filtered)
    if dropped > 0:
        logger.warning(
            "generate_explanation: 입력에 없는 chunk_id 인용 %d건 제거 (남은 %d건)",
            dropped, len(filtered),
        )
    if not filtered:
        raise SchemaViolationError(
            "generate_explanation: citations 가 모두 입력 청크에 없는 chunk_id (환각)"
        )

    try:
        citations = [Citation.model_validate(c) for c in filtered]
        if chunks:
            citations = _hydrate_citation_urls(citations, chunks)
        answer = AssistantAnswer(
            message=_clean_text(raw["message"]),
            citations=citations,
            related_questions=raw.get("related_questions", [])[:4],
            needs_policy=bool(raw.get("needs_policy", False)),
        )
    except Exception as exc:
        raise SchemaViolationError(
            f"generate_explanation 응답이 AssistantAnswer 와 불일치: {exc}"
        ) from exc

    logger.info(
        "generate_explanation: citations=%d related=%d needs_policy=%s",
        len(answer.citations), len(answer.related_questions), answer.needs_policy,
    )
    return answer


# ---------------------------------------------------------------------------
# 4. OCR — 서류 분류 + 슬롯 매핑 (Sprint 15 REQ-11)
# ---------------------------------------------------------------------------


_DOC_TYPES: list[str] = ["diagnosis", "police_report", "claim_form", "receipt", "other"]
"""OCR 서류 유형 5종 (PM-16 결정 3)."""


# 서류 유형별 기대 슬롯 필드 (PM-16 결정 4 + Sprint 15.5 + Sprint 17 매핑 풀 확장)
# Sprint 17: SlotState 6 신규 필드 추가 — 진단서/청구서/경찰 신고서 표준 필드 매핑.
_DOC_TYPE_SLOT_FIELDS: dict[str, list[str]] = {
    "diagnosis": [
        # 기존 4
        "diagnosis", "hospitalization_days", "outpatient_visits", "evidence",
        # Sprint 17 — 진단서 표준 필드 4
        "hospital", "diagnosis_code", "treatment_period", "incident_date",
    ],
    "police_report": [
        # 실손 전용(PM-33) — auto 필드 제거. 상해 사고 신고서에서 날짜·장소·진단만.
        "incident_date", "incident_location", "diagnosis",
    ],
    "claim_form": [
        # 기존 3
        "insurer", "product", "incident_date",
        # Sprint 17 — 청구서 표준 필드 2
        "policy_no", "claim_amount",
        # PM-20 — 청구서에서 area/evidence 도 흔히 추출 가능
        "area", "evidence",
    ],
    "receipt": [
        # 기존 1
        "evidence",
        # Sprint 17 — 영수증 표준 필드 2
        "claim_amount", "hospital",
        # PM-20 — 진료비 영수증 등 풍부 필드 (treatment_period, 진료시작일, 사업장 주소,
        # 진료과목·DRG 코드, 분야 분류) 추가. 매핑 풀 부족이 추출 자체 차단했음.
        "treatment_period", "incident_date", "incident_location",
        "diagnosis", "diagnosis_code", "area",
    ],
    # Sprint 15.5 — "other" 도 SlotState 전 필드 자유 추출. 빈 매핑 X.
    "other": list(_SLOT_FIELD_ENUM),
}


_CLASSIFY_DOCUMENT_TOOL: dict[str, Any] = {
    "name": "classify_document",
    "description": "OCR 추출 텍스트를 보험 청구 관련 서류 5 유형 중 하나로 분류한다.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,  # W-2 (reviewer 10) — 다른 tool 5종 일관
        "properties": {
            "doc_type": {
                "type": "string",
                "enum": _DOC_TYPES,
                "description": (
                    "diagnosis(병원 진단서) / police_report(경찰 신고서) / "
                    "claim_form(보험 청구서) / receipt(영수증) / other(기타)"
                ),
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "분류 신뢰도. 0.7 미만이면 호출자가 other 로 폴백 권장.",
            },
            "reason": {
                "type": "string",
                "description": "분류 근거 한 줄 (한국어).",
            },
        },
        "required": ["doc_type", "confidence", "reason"],
    },
}


_HELP_SYSTEM = (
    "당신은 '보험길잡이' 서비스의 도움말·상담 안내원입니다. 두 가지 일을 합니다:\n"
    "  (A) 서비스 사용법 안내,  (B) 실손보험·약관에 대한 일반 질문(QA) 답변.\n\n"
    "[참고 자료] 사용자 질문과 함께 실손 표준약관에서 검색된 참고 청크가 제공됩니다. "
    "이 청크는 질문과 무관할 수도 있으니, 관련될 때만 근거로 씁니다.\n\n"
    "[역할 경계 — Sprint 34 완화]\n"
    "- 사용자가 '내 경우 청구 되나요?' 처럼 본인 사례를 물으면, **거부하지 말고 '일반 실손 표준약관 "
    "기준'으로 가능성을 안내**하세요(예: \"발목 골절로 입원하셨다면 표준약관상 보상되는 경우가 많아요\"). "
    "단 **특정 보험사 약관으로 단정하지 말 것** — '가입하신 보험사·세대에 따라 세부 조건은 다를 수 있어요' "
    "를 덧붙이고, 더 정확히 원하면 '내 보험으로 확인하기'(로그인) 를 권합니다.\n"
    "- 확신 톤 금지(단정 금지)이되 헤지를 앞세우지 말고 **결론(가능성)을 먼저** 말합니다.\n\n"
    "[답변 규칙]\n"
    "1. 실손보험·약관 관련 **사실 질문**이고 참고 청크가 관련되면, 그 청크를 근거로 답하고 "
    "   citations 에 사용한 chunk_id 를 담습니다 (환각 금지 — 제공된 chunk_id 만 사용).\n"
    "2. **서비스 사용법·조작 질문**이거나 참고 청크가 질문과 무관하면, 아는 범위에서 쉽게 답하고 "
    "   citations 는 빈 배열로 둡니다.\n"
    "3. 청크에 없는 약관 세부 수치·조건을 지어내지 않습니다. 특정 가입 보험이 확인되지 않으면 "
    "   '일반적인 실손 표준약관 기준' 임을 밝힙니다.\n"
    "4. 단정 금지, 어시스턴트 존댓말, 2~4문장으로 간결하게(어르신도 이해하도록). "
    "   message 본문에 chunk_id·'청크' 같은 내부 표현을 절대 쓰지 않습니다.\n"
    "5. related_questions: 이어서 물어볼 만한 질문 최대 4개(없으면 빈 배열). "
    "   needs_policy: 정확한 답에 가입 약관 확인이 필요하면 true.\n"
    "6. **실손 중복가입**: '실손 여러 개면 둘 다 받나/어디가 이득?' 물으면 — 실손은 중복가입해도 "
    "   실제 낸 의료비 한도 안에서 보험사들이 '비례분담'해 지급하므로 **이중 수령은 안 된다**고 "
    "   정확히 안내(여러 개 유지 시 보험료만 이중). '어느 회사가 이득'은 실손에선 성립 X. "
    "   (진단비 등 정액 특약은 별도로 각각 받음.)\n"
)

# 응답 스키마는 explanation 과 동일 포맷을 공유하되, citations 는 0건 허용(사용법 질문).
_HELP_RESPONSE_SCHEMA = {
    "name": "help_answer",
    "schema": _EXPLANATION_RESPONSE_SCHEMA["schema"],
    "strict": True,
}


def generate_help_answer(
    question: str, chunks: list[dict[str, Any]] | None = None
) -> AssistantAnswer:
    """도움 챗봇('무엇이든 물어보세요') 전용 — RAG 근거 일반 QA + 사용법 안내.

    메인 상담(generate_assessment)과 달리 **청구 가능성 판정을 하지 않는다.** 대신:
      - 실손·약관 사실 질문이면 검색 청크를 근거로 답하고 citations 를 담는다(compact 출처).
      - 사용법/무관 질문이면 citations 없이 쉽게 답한다.
      - 본인 사례 판단 요청은 메인 흐름으로 안내(citations 빈 배열).

    generate_explanation 과 달리 citations 최소 1건을 강제하지 않으며(사용법 질문),
    스키마 위반 시에도 plain 텍스트로 graceful fallback 하여 도움 챗봇이 하드 실패하지 않는다.
    """
    client = _get_client()
    chunks = chunks or []
    chunks_for_llm = _prepare_chunks(chunks)
    valid_chunk_ids = {c["chunk_id"] for c in chunks_for_llm if c["chunk_id"]}
    user_payload = json.dumps(
        {"question": question.strip(), "chunks": chunks_for_llm}, ensure_ascii=False
    )
    messages = _messages_for_llm(
        history=[], system_prompt=_HELP_SYSTEM, new_user_msg=user_payload
    )
    try:
        raw = _call_structured(
            client, model=get_chat_model(), messages=messages,
            response_schema=_HELP_RESPONSE_SCHEMA, temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001 — 외부 LLM/스키마 방어 → plain fallback
        logger.warning("generate_help_answer 구조화 호출 실패, plain fallback: %s", exc)
        return _help_plain_answer(client, question)

    # citations 는 있으면 검증/hydrate, 없으면 그대로 빈 배열 (사용법 질문).
    raw_citations = [c for c in (raw.get("citations") or []) if c.get("chunk_id") in valid_chunk_ids]
    citations: list[Citation] = []
    if raw_citations:
        try:
            citations = _hydrate_citation_urls(
                [Citation.model_validate(c) for c in raw_citations], chunks
            )
        except Exception as exc:  # noqa: BLE001 — 인용 하이드레이트 실패는 무시(본문은 유효)
            logger.warning("generate_help_answer citation hydrate 실패: %s", exc)
            citations = []
    return AssistantAnswer(
        message=_clean_text(raw.get("message", "").strip()),
        citations=citations,
        related_questions=(raw.get("related_questions") or [])[:4],
        needs_policy=bool(raw.get("needs_policy", False)),
    )


def _help_plain_answer(client: OpenAI, question: str) -> AssistantAnswer:
    """구조화 호출 실패 시 plain 텍스트 폴백 (인용 없이 본문만)."""
    messages = _messages_for_llm(
        history=[], system_prompt=_HELP_SYSTEM, new_user_msg=question.strip()
    )
    try:
        response = client.chat.completions.create(
            model=get_chat_model(), messages=messages, temperature=0.3,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"generate_help_answer 폴백 호출 실패: {exc}") from exc
    return AssistantAnswer(
        message=_strip_internal_ids((response.choices[0].message.content or "").strip()),
        citations=[], related_questions=[], needs_policy=False,
    )


def _classify_document_system() -> str:
    return (
        "당신은 보험 청구에 첨부될 수 있는 서류 분류기다. "
        "사용자가 보험 청구를 위해 업로드한 모든 서류는 잠재적 증빙이므로, "
        "보험 직접 관련 서류 외에도 청구 근거가 될 만한 일반 서류 (영수증/증명서/확인서) 까지 폭넓게 분류한다.\n\n"
        "유형 정의:\n"
        "- diagnosis: 의료기관이 발급한 병명·치료기간·입원여부 등을 포함한 진단서\n"
        "- police_report: 경찰서 발급 사고사실확인원 / 교통사고확인원\n"
        "- claim_form: 보험사 청구 신청서 (보험사명·증권번호·청구 항목)\n"
        "- receipt: 의료비/수리비/일반 결제 영수증 (약제비/식음료/핸드폰 수리/항공 발권 영수증 등 모두 포함)\n"
        "- other: 위 유형에 해당하지 않으나 여행자/핸드폰 보험 등에서 청구 증빙으로 쓰일 수 있는 서류. "
        "  예: 출입국사실증명서, 항공권 e-ticket, 항공사 지연확인서, 통신사 부가서비스 내역서, 수리불가 확인서. "
        "  '보험 청구 관련 서류가 아님' 으로 단정 금지 — 사용자는 청구 의도로 업로드했다.\n\n"
        "원칙: 추측보다 텍스트 근거 우선. 영수증 형식이면 receipt 우선, 명세서/증명서면 other (단 0.7 이상 신뢰도 유지)."
    )


def classify_document(text: str) -> dict[str, Any]:
    """OCR 추출 텍스트 → 서류 유형 분류 (5종) + 신뢰도.

    Args:
        text: OCR 어댑터가 반환한 텍스트 (이미 PII 마스킹 완료 권장)

    Returns:
        {"doc_type": ..., "confidence": float, "reason": str}.
        신뢰도 < 0.7 시 호출자가 other 로 폴백.

    Raises:
        LLMError / SchemaViolationError
    """
    if not text.strip():
        return {"doc_type": "other", "confidence": 0.0, "reason": "빈 텍스트"}

    client = _get_client()
    messages = [
        {"role": "system", "content": _classify_document_system()},
        {"role": "user", "content": text[:2000]},  # 토큰 가드
    ]
    result = _call_with_tool(
        client,
        model=get_chat_model(),
        messages=messages,
        tool_def=_CLASSIFY_DOCUMENT_TOOL,
        temperature=0.0,
    )
    # 신뢰도 < 0.7 폴백
    if result.get("confidence", 0.0) < 0.7 and result.get("doc_type") != "other":
        logger.info(
            "classify_document: 신뢰도 낮음 (%.2f) → other 폴백 (원본 type=%s)",
            result["confidence"], result["doc_type"],
        )
        result = {
            "doc_type": "other",
            "confidence": result["confidence"],
            "reason": f"신뢰도 낮음 폴백 ({result.get('reason', '')})",
        }
    return result


# PM-20 — 필드별 의미·예시·반례 사전. tool_def description + system prompt 양쪽에서 활용.
# LLM 환각(표 라벨을 필드 값으로 잘못 추출) 억제 핵심.
_FIELD_DESCRIPTIONS: dict[str, str] = {
    "area": (
        "보험 분야 코드. 실손의료보험 전용이므로 의료 관련 서류면 'accident_disease' 하나만. "
        "의료비 영수증·진단서·약제비 영수증은 accident_disease. "
        "**중요 반례**: 식음료 결제·항공권·통신·핸드폰 수리·일반 영수증 등 의료와 "
        "**무관한 서류에는 area 추출 금지**. "
        "분야가 명백하지 않으면 응답에서 area 키 자체를 제외한다. "
        "**중요**: area 가 명확하지 않다고 해서 evidence/claim_amount/incident_date 같은 "
        "다른 슬롯의 추출까지 생략하지 말 것 — area 만 비우고 나머지는 정상 추출."
    ),
    "insurer": "보험사 회사명 (예: 삼성화재, 현대해상, 메리츠화재, 롯데손해보험, 한화손해보험). 카드사·은행 이름은 제외.",
    "product": "보험 상품명 (예: 실손의료보험).",
    "incident_date": (
        "사고/진료 시작일. **YYYY-MM-DD** 형식. "
        "영수증의 '진료기간' 행이 있으면 그 시작일을 사용. "
        "예: 진료기간이 '2022.08.31 ~ 2022.09.05' 이면 incident_date='2022-08-31'."
    ),
    "incident_location": (
        "진료 발생 장소. 주소·시·구·도로명 등. "
        "영수증의 '사업장 소재지' / '병원 주소' 모두 가능. "
        "예: '경기도 안산시 단원구'."
    ),
    "diagnosis": (
        "진단명·병명·질환명 (**반드시 한국어**, 자유 텍스트). 예: '발목 골절', '폐렴'. "
        "**반례**: 진료과목명(내과·정형외과·Orthopedics·Internal Medicine 등) 단독은 진단명이 아님 — 응답에서 제외. "
        "영어 진단명이 본문에 있으면 한국어로 변환 (예: 'Fracture of ankle' → '발목 골절'). 변환 불가하면 제외."
    ),
    "diagnosis_code": (
        "KCD-7 진단코드 (예: S82.5) 또는 DRG 질병군 번호. "
        "영수증의 '질병군(DRG)번호' 열 값. 코드 자체 (영숫자) 만 추출."
    ),
    "hospitalization_days": "총 입원 일수 (정수).",
    "outpatient_visits": "통원 횟수 (정수).",
    "treatment_period": (
        "치료/진료 기간. 형식: 'YYYY-MM-DD ~ YYYY-MM-DD'. "
        "영수증/진단서의 '진료기간' 행에서 가져옴. "
        "예: '2022-08-31 ~ 2022-09-05'."
    ),
    "hospital": (
        "**의료기관명만**. 예: '서울대학교병원', '한강병원'. "
        "**중요 반례 (절대 금지)**: '영수증번호', '환자등록번호', '카드번호', "
        "'진료비번호', '현금영수증' 같은 영수증 표의 **항목 라벨/번호** 자체를 "
        "hospital 필드 값으로 추출하면 안 됨. 의료기관 이름이 마스킹(*****)된 경우 "
        "마스킹된 값 그대로 반환."
    ),
    "policy_no": "보험 증권번호 (예: POLICY-2026-001, 영숫자 식별자).",
    "claim_amount": (
        "**환자/사용자가 청구할 수 있는 금액 (원 단위 정수, 콤마 제외)**. "
        "영수증류는 '진료비 총액', '환자부담 총액', '결제금액', '약제비 합계', '수리비 총액' 중 "
        "가장 큰 금액 1개를 반드시 추출 (영수증 형식이면 claim_amount 누락 금지). "
        "**반례**: 카드 승인번호, 환자등록번호, 사업자등록번호, 가맹점번호 같은 식별자 숫자는 절대 아님. "
        "예: '진료비 총액 2,243,771' → claim_amount=2243771."
    ),
    "evidence": (
        "증빙 서류명. 본 서류 자체의 제목. "
        "예: '진료비 계산서·영수증', '진단서', '입퇴원 확인서', '약제비 영수증'."
    ),
    "version": "보험 약관 버전.",
    "unknown_slots": "사용자가 모른다고 명시한 슬롯 (LLM 추출 미사용)",
    "document_metadata": "참고용 자유 메타 (UI 확인 카드용)",
}


def _extract_doc_slots_tool(doc_type: str) -> dict[str, Any]:
    """서류 유형에 따라 필드 enum 을 좁힌 tool 정의. PM-20 — 필드별 description 사전 활용."""
    fields = _DOC_TYPE_SLOT_FIELDS.get(doc_type, [])
    return {
        "name": "extract_slots_from_document",
        "description": (
            f"서류 유형 '{doc_type}' 에서 보험 청구 슬롯 정보를 추출한다. "
            "본문에 명시되지 않은 필드는 응답 객체에서 제외한다 (추측 금지). "
            "표의 행 라벨(예: '영수증번호', '카드번호')을 필드 값으로 잘못 추출하지 말 것."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                field: {
                    "type": "string",
                    "description": _FIELD_DESCRIPTIONS.get(
                        field, f"본문에서 추출한 {field} 값 (한국어)"
                    ),
                }
                for field in fields
            },
            "additionalProperties": False,
        },
    }


def extract_slots_from_document(text: str, doc_type: str) -> dict[str, Any]:
    """서류 유형별 기대 필드 → SlotState 부분 업데이트 dict.

    Args:
        text: OCR 추출 텍스트 (PII 마스킹 권장)
        doc_type: classify_document 결과의 doc_type

    Returns:
        부분 SlotState dict. 본문에 없는 필드는 키 자체 없음.
        doc_type 이 매핑 없음(other) 이면 빈 dict.

    Raises:
        LLMError / SchemaViolationError
    """
    fields = _DOC_TYPE_SLOT_FIELDS.get(doc_type, [])
    if not fields or not text.strip():
        # Sprint 15.5: 알려지지 않은 doc_type 도 SlotState 전체 enum 으로 자유 추출 시도.
        # 단 doc_type 이 매핑에 명시되지 않은 경우 ("unknown_type" 등) 만 — other 는 이제 매핑 있음.
        if doc_type not in _DOC_TYPE_SLOT_FIELDS or not text.strip():
            return {}
        fields = list(_SLOT_FIELD_ENUM)

    client = _get_client()
    tool_def = _extract_doc_slots_tool(doc_type)

    # PM-20 — 필드별 의미·예시·반례를 system prompt 에도 인라인. tool_def description 만으론
    # gpt-4o-mini 가 환각하는 경향 (예: hospital 에 '영수증번호' 매핑). 두 곳 동시 노출 필요.
    field_guide = "\n".join(
        f"- {f}: {_FIELD_DESCRIPTIONS.get(f, '(설명 없음)')}" for f in fields
    )
    base_rules = (
        "원칙 (반드시 준수):\n"
        "1. 본문에 명시된 값만 채운다. 추측·해석·다른 서류 가정 금지.\n"
        "2. 표의 행 라벨/항목명(예: '영수증번호', '환자등록번호', '카드번호', '현금영수증') "
        "   자체를 필드 값으로 사용 금지. 라벨에 대응되는 **실제 값**만 추출.\n"
        "3. 본문에 없는 필드는 응답 객체에서 제외 (null/빈 문자열 X).\n"
        "4. PII 마스킹(*****) 이 포함된 값은 마스킹된 그대로 반환 (호출자 책임).\n"
        "5. 날짜·금액은 위 필드 설명의 형식 규칙을 따른다."
    )
    if doc_type == "other":
        system_msg = (
            "당신은 보험 청구 슬롯 추출기다. 본 서류는 정형 4종(diagnosis/police_report/claim_form/receipt)에 "
            "해당하지 않지만, **사용자가 보험 청구 증빙으로 업로드한 서류**다 "
            "(예: 여행자보험의 출입국증명서·항공권·지연확인서, 핸드폰보험의 통신사 내역서·수리불가 확인서).\n\n"
            "**적극 추출 원칙**: evidence(서류명), claim_amount(영수증 금액·환불금액 등), "
            "incident_date(여행일·사고일·발급일·수리일), incident_location(여행지·공항·매장·주소), "
            "document_metadata(자유 메타 — 예: '발권일', '편명', '예약번호') 중 본문에 명시된 모든 정보를 "
            "최대한 추출. 추출 0 회피.\n\n"
            f"{base_rules}\n\n"
            "필드 의미:\n" + field_guide
        )
    else:
        # receipt/diagnosis/police_report/claim_form 공통.
        # receipt 가이드: 의료/비의료 양쪽 모두 적극 추출 — 의료 영수증에서 의료 필드 누락 방지.
        receipt_extra = (
            "\n\n**영수증(receipt) 추출 가이드**:\n"
            "1) 영수증 형식이면 evidence(서류명), claim_amount(총액), incident_date(거래일), "
            "   incident_location(매장·주소·병원 위치) 4개는 무조건 적극 추출.\n"
            "2) **의료 영수증**(진료비/약제비/병원 영수증)이면 위 4개 + hospital(의료기관명), "
            "   treatment_period(진료기간), diagnosis(진단명), diagnosis_code(질병군 번호), "
            "   area='accident_disease' 까지 적극 추출. 의료 정보 누락 금지.\n"
            "3) 비의료 영수증(식음료/통신/항공/수리 등)은 위 4개만 추출, 의료 전용 필드와 area 는 생략."
            if doc_type == "receipt"
            else ""
        )
        system_msg = (
            f"당신은 보험 청구 슬롯 추출기다. 서류 유형은 {doc_type}.\n\n"
            f"{base_rules}{receipt_extra}\n\n"
            "필드 의미:\n" + field_guide
        )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": text[:3000]},
    ]
    result = _call_with_tool(
        client,
        model=get_chat_model(),
        messages=messages,
        tool_def=tool_def,
        temperature=0.0,
    )
    # 빈 문자열 키 제거 (LLM 이 명시 "" 로 반환할 가능성)
    return {k: v for k, v in result.items() if v and str(v).strip()}
