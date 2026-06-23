"""app.domains.sessions.schemas

파일 경로: app/sessions/schemas.py
목적: 세션·슬롯·대화 이력·어시스턴트 응답의 pydantic 모델 정의.

설계 참고:
    - docs/design/data-model.md § 세션 모델 (Sprint 2 — 확정)
    - docs/design/api-spec.md § Sprint 2 디테일 확정 (next_question / generate_assessment 응답)

모델 분류:
    - SessionStatus / Message / SlotState / Session  : 도메인 상태
    - SessionCreate                                   : POST /sessions 요청
    - MessageRequest                                  : POST /sessions/{id}/messages 요청
    - Citation                                        : assessment 응답의 인용 1건
    - AssistantAsk / AssistantAssessment              : 어시스턴트 응답 2가지 모드
    - SessionResponse                                 : POST /sessions/{id}/messages 응답
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

SessionStatus = Literal["gathering", "analyzing", "answered", "closed"]
"""세션 상태 전이 — data-model.md § 상태 전이 와 동기화."""

Area = Literal["auto", "fire", "accident_disease"]
"""허용된 영역 코드 — documents.models AREA_CODES 와 동기화."""

LikelihoodLevel = Literal["높음", "중간", "낮음"]
"""가능성 등급 — api-spec.md generate_assessment JSON Schema 와 동기화."""


# ---------------------------------------------------------------------------
# 도메인 상태
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """대화 이력 1건."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    created_at: datetime
    response_type: Literal["ask", "assessment"] | None = Field(
        default=None,
        description="assistant 메시지만 채워진다. 감사 추적용",
    )


class SlotState(BaseModel):
    """현재 채워진 슬롯 상태. `None` 은 미채움.

    영역별 필수 슬롯은 data-model.md § 영역별 필수 슬롯 표 참조.
    `next_question` 우선순위 / `extract_slots` 의 갱신 대상은 동일 필드명.
    """

    model_config = ConfigDict(extra="forbid")

    # 공통 (모든 영역)
    area: Area | None = None
    insurer: str | None = None
    product: str | None = None
    version: str | None = None
    incident_date: date | None = None
    evidence: list[str] = Field(default_factory=list)

    @field_validator("incident_date", mode="before")
    @classmethod
    def _coerce_date(cls, value: Any) -> Any:
        """LLM 이 ISO 문자열로 보낸 incident_date 를 date 로 변환.

        - None / date 객체 → 그대로
        - 'YYYY-MM-DD' 문자열 → date.fromisoformat
        - 그 외 문자열 → None (모호한 상대 표현은 service 가 재질문)
        """
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return value

    # auto 전용
    incident_type: str | None = Field(
        default=None, description="추돌 / 단독 / 대물 / 대인"
    )
    fault_ratio: Annotated[int, Field(ge=0, le=100)] | None = None
    damage_type: str | None = Field(default=None, description="자차 / 대물 / 대인")

    # fire 전용
    loss_type: str | None = Field(
        default=None, description="전소 / 부분소실 / 도난 / 누수"
    )
    damaged_items: list[str] = Field(default_factory=list)
    cause: str | None = None

    # accident_disease 전용
    diagnosis: str | None = None
    hospitalization_days: Annotated[int, Field(ge=0)] | None = None
    outpatient_visits: Annotated[int, Field(ge=0)] | None = None

    # Sprint 6 — "모름" 명시 슬롯. _compute_missing 가 missing 에서 제외.
    # extract_slots LLM 이 사용자 "모름"/"몰라" 입력 인식 시 채움.
    unknown_slots: list[str] = Field(default_factory=list)

    # Sprint 17 — 청구서 표준 필드 (필수 X, OCR/마이데이터 prefill 친화)
    hospital: str | None = Field(default=None, description="의료기관명 (진단서)")
    diagnosis_code: str | None = Field(
        default=None, description="KCD-7 진단코드 (예: S82.5)"
    )
    treatment_period: str | None = Field(
        default=None, description="치료 기간 (예: 2026-05-10 ~ 2026-05-20)"
    )
    policy_no: str | None = Field(default=None, description="보험 증권번호")
    claim_amount: Annotated[int, Field(ge=0)] | None = Field(
        default=None, description="청구금액 (원)"
    )
    incident_location: str | None = Field(
        default=None, description="사고 발생 장소 (경찰 신고서)"
    )

    # Sprint 17 — 자유 메타데이터. 청구 가능성 판단 미사용 — UI 확인 카드 노출 전용.
    # OCR 추출 시 SlotState 매핑 외 정보 (서류 발급일/연락처/병원 주소 등) 보관.
    document_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="청구 판단 무관 참고 메타 (UI 확인 카드 노출용)",
    )


class Session(BaseModel):
    """세션 1건. 인메모리 SessionStore 가 보관."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="uuid v4")
    created_at: datetime
    last_activity_at: datetime
    status: SessionStatus = "gathering"
    slots: SlotState = Field(default_factory=SlotState)
    history: list[Message] = Field(default_factory=list)

    def is_expired(self, now: datetime, ttl_seconds: int) -> bool:
        """`last_activity_at + ttl` 경과 시 만료.

        Note:
            `now` 와 `last_activity_at` 둘 다 **timezone-aware** datetime 이어야 한다.
            naive 를 섞으면 TypeError. 본 도메인은 항상 UTC aware 를 사용한다.
        """
        return (now - self.last_activity_at).total_seconds() > ttl_seconds


# ---------------------------------------------------------------------------
# 요청
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """POST /sessions 요청."""

    model_config = ConfigDict(extra="forbid")

    initial_message: str | None = Field(
        default=None,
        description="첫 메시지를 함께 보낼 수 있다. 비우면 빈 세션만 생성",
    )


class MessageRequest(BaseModel):
    """POST /sessions/{id}/messages 요청."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="사용자 자연어 입력")


# ---------------------------------------------------------------------------
# 어시스턴트 응답 (ask / assessment 2모드)
# ---------------------------------------------------------------------------


class AssistantAsk(BaseModel):
    """ask 모드 — 슬롯 부족 시 후속 질문."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ask"] = "ask"
    message: str = Field(..., min_length=1)
    expected_slots: list[str] = Field(..., min_length=1, max_length=2)
    options: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    """assessment 응답의 인용 1건. chunks/schemas.py Chunk 와 필드 동기화."""

    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    insurer: str
    product: str
    version: str
    doc_type: Literal["summary", "business", "terms"]
    clause: str
    sub_no: str | None = None
    text: str = Field(..., min_length=5)
    page: int = Field(..., ge=1)
    # Sprint 5 — PDF 페이지 캡처 (backend 가 응답 직전 hydrate. LLM 미관여)
    page_image_url: str | None = Field(
        default=None,
        description="/static/page_images/{document_id}/{page:04d}.png (lazy 캐시)",
    )
    pdf_url: str | None = Field(
        default=None,
        description="/static/raw/<insurer>/<area>/.../<doc_type>.pdf (#page=N 점프)",
    )


class AssistantAssessment(BaseModel):
    """assessment 모드 — 가능성 등급 + 인용 + 면책."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["assessment"] = "assessment"
    likelihood: LikelihoodLevel
    summary: str = Field(..., min_length=10)
    satisfied: list[str] = Field(default_factory=list)
    unsatisfied: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(..., min_length=1)
    next_steps: list[str] = Field(default_factory=list)
    # Sprint 6 — full(슬롯 완전 충족) vs partial(일부 부족 → 추정 기반)
    confidence: Literal["partial", "full"] = "full"
    disclaimer: str = Field(
        default="본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다."
    )


# ---------------------------------------------------------------------------
# 통합 응답 (POST /sessions/{id}/messages)
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """POST /sessions/{id}/messages 응답.

    `assistant` 는 AssistantAsk 또는 AssistantAssessment 중 하나.
    Sprint 2 PoC 에서는 단일 직렬화 + discriminator(`type`) 으로 클라이언트 분기.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    turn: int = Field(..., ge=1, description="이번 메시지가 몇 번째 대화 턴인지")
    assistant: AssistantAsk | AssistantAssessment = Field(
        ..., discriminator="type"
    )
    slots: SlotState
    status: SessionStatus
