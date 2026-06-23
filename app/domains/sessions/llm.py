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
from datetime import date
from typing import Any

import openai
from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.domains.sessions.schemas import (
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
    # auto
    "incident_type", "fault_ratio", "damage_type",
    # fire
    "loss_type", "damaged_items", "cause",
    # accident_disease
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
                    "area": {"type": "string", "enum": ["auto", "fire", "accident_disease"]},
                    "insurer": {"type": "string"},
                    "product": {"type": "string"},
                    "version": {"type": "string"},
                    "incident_date": {"type": "string", "description": "ISO YYYY-MM-DD 형식 권장"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "incident_type": {"type": "string", "description": "auto 전용 (추돌/단독/대물/대인)"},
                    "fault_ratio": {"type": "integer", "minimum": 0, "maximum": 100},
                    "damage_type": {"type": "string", "description": "auto 전용 (자차/대물/대인)"},
                    "loss_type": {"type": "string", "description": "fire 전용 (전소/부분소실/도난/누수)"},
                    "damaged_items": {"type": "array", "items": {"type": "string"}},
                    "cause": {"type": "string"},
                    "diagnosis": {"type": "string", "description": "accident_disease 전용"},
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
        "필수 규칙:\n"
        "1. `area` 는 가장 먼저 결정한다 (auto/fire/accident_disease).\n"
        "   - '자동차/충돌/추돌/주차/접촉/대인배상' 단서 → area=auto\n"
        "   - '주택화재/누수/도난/소실/소방' 단서 → area=fire\n"
        "   - '입원/통원/진단/골절/질병/상해/넘어졌/다쳤/병원' 단서 → area=accident_disease\n"
        "2. **사용자가 언급한 보험사명·상품명을 빠짐없이 `insurer`/`product` 로 추출**.\n"
        "   - 예: '한화손해보험 개인용자동차보험' → insurer='한화손해보험', product='개인용자동차보험'\n"
        "   - 예: '삼성생명 무배당상해입원보장' → insurer='삼성생명', product='무배당상해입원보장'\n"
        "3. `incident_date` 는 ISO YYYY-MM-DD 형식. 오늘 = " + today.isoformat() + ", 어제 = " + yesterday + ".\n"
        "   - '지난주', '며칠 전' 같은 모호 표현은 추출 생략\n"
        "4. fire 영역의 가전제품/가구/건물 등 손상 품목은 `damaged_items` (배열) — `damage_type` 아님.\n"
        "5. auto 영역의 `damage_type` 은 보장 종목(자차/대물/대인). 손상 품목 아님.\n"
        "6-a. **\"모름\"/\"몰라\"/\"모르겠어\"/\"잘 모르겠어\" 등 명시적 무지 표현** → 해당 슬롯을 `unknown_slots` 배열에 추가 "
        "(slot_updates 에는 넣지 않는다). 예: '보험사 잘 모르겠어' → unknown_slots=['insurer'].\n"
        "6-b. **부정 표현 → 정수 슬롯 0 으로 채움**. 예: '입원 안 했어' / '통원 없어' / '하루도 안 함' → "
        "hospitalization_days=0, '통원 0번' → outpatient_visits=0, '과실 0%' → fault_ratio=0.\n"
        "7. 추론·추측·기본값 입력 금지. 모호하면 그 필드는 생략 (단 6-a, 6-b 는 명시이므로 적용).\n\n"
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
                        "예: area 면 ['자동차','화재','사고질병']. "
                        "영문 코드(auto/fire/accident_disease) 사용 금지. "
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
    "**옵션 규칙 (강제)**:\n"
    "- 슬롯 성격에 따라 options 제공 여부를 결정한다:\n"
    "  * **closed-ended 슬롯 (enum 분류, 5종)**: options 채움 + 마지막에 '모르겠습니다' 추가\n"
    "    - area: ['자동차', '화재', '사고질병', '모르겠습니다']\n"
    "    - incident_type (auto): ['추돌', '접촉', '주차사고', '단독사고', '기타', '모르겠습니다']\n"
    "    - damage_type (auto): ['대물', '대인', '자기차량', '기타', '모르겠습니다']\n"
    "    - loss_type (fire): ['전손', '부분손해', '도난', '기타', '모르겠습니다']\n"
    "    - cause (fire): ['전기적 원인', '가스/조리 부주의', '방화', '자연재해', '기타', '모르겠습니다']\n"
    "  * **open-ended 슬롯 (자유 텍스트)**: options 는 반드시 **빈 배열 []** 로 한다. 선택지 강요 X.\n"
    "    - insurer, product, incident_date, diagnosis, damaged_items, evidence,\n"
    "      hospitalization_days, outpatient_visits, fault_ratio\n"
    "- area 의 영문 코드(auto/fire/accident_disease)를 options 에 절대 사용하지 않는다.\n"
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
    "2. citations 는 입력된 청크의 chunk_id / 메타를 그대로 인용 (text 는 청크 본문 원본)\n"
    "3. citations.minItems=1 — 인용 없는 응답 금지\n"
    "4. disclaimer 는 정해진 면책 문구 사용\n"
    "5. summary 는 1~2 문장의 한국어 요약\n"
    "6. **confidence 판정**: 입력 slots 의 필수 슬롯이 모두 채워졌으면 'full', "
    "  unknown_slots 가 있거나 일부 슬롯이 None 이면 'partial'.\n"
    "\n"
    "**톤 가이드 (강제)**:\n"
    "- 친절체 + 존댓말 (\"~안내드립니다\" / \"~드리겠습니다\"). 명령형/반말 금지.\n"
    "- 사용자에게 책임 떠넘기지 않는다. 시스템이 능동적으로 안내.\n"
    "- confidence='full' 인 경우 summary 첫 문장: \"제공해 주신 정보를 바탕으로 정확하게 안내드립니다.\" 식.\n"
    "- confidence='partial' 인 경우 summary 첫 문장: \"정확한 답변에는 {부족 슬롯} 정보가 더 있으면 좋겠으나, "
    "  현재 정보로 일반적인 약관 기준에 따라 안내드리겠습니다.\" 식. 그리고 unsatisfied 의 첫 항목에 부족 슬롯을 "
    "  \"{슬롯명}을(를) 알려주시면 더 정확하게 안내드릴 수 있습니다\" 식으로 부드럽게 적어라.\n"
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
) -> AssistantAssessment:
    """슬롯 + RAG 청크로 가능성 등급 + 인용 응답 생성.

    schema-violation 발생 시 1회 재시도 (Structured Outputs strict=True 가 보통 막아주지만
    드물게 통과하는 케이스를 대비한 방어). 두 번째 시도에 더 강한 reminder 를 system 에 추가.

    Args:
        slots: 충족된 SlotState
        chunks: search.service.similarity_search 결과 (id/text/score/metadata 포함)

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
    # mode='json' 으로 date → ISO 문자열 직렬화 (json.dumps 가 date 를 모르기 때문)
    user_payload = json.dumps(
        {"slots": slots.model_dump(mode="json", exclude_none=True), "chunks": chunks_for_llm},
        ensure_ascii=False,
    )

    last_error: SchemaViolationError | None = None
    for attempt in (1, 2):
        system = _ASSESSMENT_SYSTEM
        if attempt == 2:
            system += (
                "\n\n[재시도] 이전 응답이 응답 스키마를 위반했습니다. "
                "citations 의 chunk_id 는 입력된 청크 목록에 존재하는 값만 사용하고, "
                "모든 필수 필드(likelihood/summary/citations/disclaimer 등)를 빠짐없이 포함하세요."
            )
        messages = _messages_for_llm(history=[], system_prompt=system, new_user_msg=user_payload)
        try:
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
            return _build_assessment(raw, valid_chunk_ids=valid_chunk_ids, chunks=chunks)
        except SchemaViolationError as exc:
            last_error = exc
            logger.warning("generate_assessment 결과 검증 실패 (attempt %d): %s", attempt, exc)
            continue

    # 두 번 모두 실패
    raise last_error or SchemaViolationError("generate_assessment: 알 수 없는 schema 위반")


def _prepare_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """RAG 청크를 LLM 입력 포맷으로 정제 (text + 메타만)."""
    out: list[dict[str, Any]] = []
    for c in chunks:
        meta = c.get("metadata") or {}
        out.append({
            "chunk_id": c.get("id"),
            "insurer": meta.get("insurer_name") or meta.get("insurer_id") or "",
            "product": meta.get("product_name") or meta.get("product_id") or "",
            "version": meta.get("version_label") or "",
            "doc_type": meta.get("doc_type") or "terms",
            "clause": meta.get("clause_no") or "",
            "sub_no": meta.get("sub_no") or None,
            "text": c.get("text") or "",
            "page": meta.get("page_start") or 1,
        })
    return out


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
            summary=raw["summary"],
            satisfied=raw.get("satisfied", []),
            unsatisfied=raw.get("unsatisfied", []),
            citations=citations,
            next_steps=raw.get("next_steps", []),
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

    # chunk_id → (document_id, page) 매핑
    chunk_meta: dict[str, tuple[int, int]] = {}
    doc_ids: set[int] = set()
    for c in chunks:
        cid = c.get("id")
        meta = c.get("metadata") or {}
        doc_id = meta.get("document_id")
        page = meta.get("page_start")
        if cid and isinstance(doc_id, int) and isinstance(page, int):
            chunk_meta[cid] = (doc_id, page)
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
        doc_id, page = meta
        file_path = file_paths.get(doc_id)
        if not file_path:
            hydrated.append(cite)
            continue

        # 이미지 변환 (lazy, 캐시)
        page_url: str | None = None
        try:
            pdf_service.render_page(doc_id, cite.page, file_path)
            page_url = pdf_service.page_image_url(doc_id, cite.page)
        except Exception as exc:
            logger.warning(
                "Citation hydrate — page 이미지 실패 chunk=%s: %s", cite.chunk_id, exc
            )

        pdf_link = pdf_service.pdf_url(file_path)
        hydrated.append(
            cite.model_copy(update={"page_image_url": page_url, "pdf_url": pdf_link})
        )
    return hydrated


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
        # 기존 4
        "incident_date", "incident_type", "fault_ratio", "damage_type",
        # Sprint 17 — 경찰 신고서 표준 필드 1
        "incident_location",
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
        "보험 분야 코드. 정확히 다음 셋 중 하나만 영문 코드로: "
        "'auto'(자동차), 'fire'(화재), 'accident_disease'(상해·질병·의료비). "
        "의료비 영수증·진단서·약제비 영수증은 accident_disease. "
        "**중요 반례**: 식음료 결제·항공권·통신·핸드폰 수리·일반 영수증 등 자동차/화재/상해와 "
        "**무관한 서류에는 area 추출 금지** (특히 'fire' 로 잘못 매핑하지 말 것). "
        "분야가 명백하지 않으면 응답에서 area 키 자체를 제외한다. "
        "**중요**: area 가 명확하지 않다고 해서 evidence/claim_amount/incident_date 같은 "
        "다른 슬롯의 추출까지 생략하지 말 것 — area 만 비우고 나머지는 정상 추출."
    ),
    "insurer": "보험사 회사명 (예: 한화손해보험, 삼성화재, KB손해보험). 카드사·은행 이름은 제외.",
    "product": "보험 상품명 (예: 차차차매일안심자동차보험, 무배당i리젠보장보험).",
    "incident_date": (
        "사고/진료 시작일. **YYYY-MM-DD** 형식. "
        "영수증의 '진료기간' 행이 있으면 그 시작일을 사용. "
        "예: 진료기간이 '2022.08.31 ~ 2022.09.05' 이면 incident_date='2022-08-31'."
    ),
    "incident_type": "사고 유형 (자동차): 추돌·접촉·주차사고·단독사고·기타.",
    "incident_location": (
        "사고/진료 발생 장소. 주소·시·구·도로명 등. "
        "영수증의 '사업장 소재지' / '병원 주소' / 신고서의 '사고 장소' 모두 가능. "
        "예: '경기도 안산시 단원구'."
    ),
    "damage_type": "손해 유형 (자동차): 자기차량·대물·대인·기타.",
    "fault_ratio": "과실 비율 (0~100 정수).",
    "loss_type": "손해 종류 (화재): 전손·부분손해·도난·누수.",
    "cause": "원인 (화재): 전기적 원인·가스/조리 부주의·방화·자연재해·기타.",
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
        "예: '진료비 계산서·영수증', '진단서', '경찰 사고확인원', '약제비 영수증'."
    ),
    "damaged_items": "손상 물품 목록 (화재).",
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
