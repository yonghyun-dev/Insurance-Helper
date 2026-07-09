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

# 실손 전용 피벗(Sprint 27) 이후 accident_disease(상해·질병) 단일. auto/fire 폐기(PM-33).
Area = Literal["accident_disease"]
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
    response_type: Literal["ask", "assessment", "answer", "comparison"] | None = Field(
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
    # 보험사 코드(예: "samsung"). 마이데이터/구조화 seed 가 채우면 검색이 한글명→코드
    # 매핑 없이 이 값으로 직접 필터링한다. 순수 자연어 흐름에선 None (name→code 폴백).
    insurer_id: str | None = Field(default=None, description="보험사 코드 (data/raw 폴더명)")
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

    # PM-35 — 보장 판정(coverage 룰 엔진) 사실. purpose 는 extract_slots(뉴럴)가 분류,
    # generation 은 마이데이터 seed 가 채운다. coverage.build_facts_from_slots 가 소비.
    generation: Annotated[int, Field(ge=1, le=4)] | None = Field(
        default=None, description="실손 세대(1~4). 마이데이터 seed 로 채움"
    )
    purpose: str | None = Field(
        default=None,
        description=(
            "청구 목적 — treatment/cosmetic/preventive/pregnancy/self_harm/crime_war. "
            "면책 판정 핵심. 미상이면 None(치료 목적으로 간주)."
        ),
    )

    # Sprint 17 — 자유 메타데이터. 청구 가능성 판단 미사용 — UI 확인 카드 노출 전용.
    # OCR 추출 시 SlotState 매핑 외 정보 (서류 발급일/연락처/병원 주소 등) 보관.
    document_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="청구 판단 무관 참고 메타 (UI 확인 카드 노출용)",
    )


class PolicyRef(BaseModel):
    """가입 실손 1건 참조 — Sprint 33 다중판정(L3).

    SlotState 는 '상황 사실'(진단/치료량/금액) 담당으로 유지하고, 보유·선택된 보험
    목록은 Session.policies 로 분리한다(SlotState 복수화의 광범위 부작용 회피).
    판정 시 각 policy 를 공유 상황 슬롯에 얹어 임시 slots 를 만들어 N회 판정한다.
    """

    model_config = ConfigDict(extra="forbid")

    insurer_id: str
    insurer: str
    product: str
    policy_no: str
    generation: Annotated[int, Field(ge=1, le=4)] | None = None


class Session(BaseModel):
    """세션 1건. 인메모리 SessionStore 가 보관."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="uuid v4")
    created_at: datetime
    last_activity_at: datetime
    status: SessionStatus = "gathering"
    slots: SlotState = Field(default_factory=SlotState)
    history: list[Message] = Field(default_factory=list)
    # Sprint 33 — 보유·선택 실손 목록(다중판정 L3). 0~1 건이면 단일 판정 경로(하위호환).
    policies: list[PolicyRef] = Field(default_factory=list)
    # Sprint 22 — 마지막 assessment 보관 (청구 요약·체크리스트 집계용). P-3 보정.
    last_assessment: AssistantAssessment | None = None
    # Sprint 33 — 마지막 비교 결과 보관.
    last_comparison: AssistantComparison | None = None

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


class SlotSeedRequest(BaseModel):
    """POST /sessions/{id}/slots 요청 — 구조화 슬롯 결정론 seed (PM-33 Track A).

    마이데이터/건강보험/OCR 의 구조화 데이터를 자연어 왕복 없이 직접 세팅한다.
    모든 필드 옵셔널. 값 있는 것만 병합. extra 는 무시(프론트 여유).
    """

    model_config = ConfigDict(extra="ignore")

    insurer: str | None = None
    insurer_id: str | None = None
    product: str | None = None
    policy_no: str | None = None
    area: Area | None = None
    incident_date: date | None = None
    diagnosis: str | None = None
    diagnosis_code: str | None = None
    hospital: str | None = None
    hospitalization_days: int | None = None
    outpatient_visits: int | None = None
    treatment_period: str | None = None
    claim_amount: int | None = None
    incident_location: str | None = None
    # Sprint 33 — 다중 실손 seed. 있으면 Session.policies 로 저장(대표 1건은 slots.insurer 등에도 반영).
    policies: list[PolicyRef] = Field(default_factory=list)


class SlotSeedResponse(BaseModel):
    """slots seed 결과 — 병합 후 슬롯 + 아직 부족한 필수 슬롯."""

    model_config = ConfigDict(extra="forbid")

    slots: SlotState
    missing: list[str]


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


class HighlightBox(BaseModel):
    """페이지 이미지 위 하이라이트 박스 — 페이지 크기 대비 정규화(0~1)."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


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
    # PM — 인용 조항의 페이지 내 위치(정규화 0~1 박스). backend 가 search_for 로 계산,
    # 프론트가 원본 이미지 위에 하이라이트 오버레이. LLM 미관여.
    highlights: list[HighlightBox] = Field(default_factory=list)


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


class AssistantAnswer(BaseModel):
    """answer 모드 — 실손 도메인 일반 질문에 약관 근거로 답하는 자유 질의응답(PM-34).

    진단(assessment) 과 달리 가능성 등급/충족·미충족이 없다. 슬롯 없이도 동작하나
    citations 는 여전히 최소 1건 강제(환각 차단 원칙).
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["answer"] = "answer"
    message: str = Field(..., min_length=10)
    citations: list[Citation] = Field(..., min_length=1)
    related_questions: list[str] = Field(default_factory=list, max_length=4)
    # 정확한 답에 가입 약관이 필요하면 True → 프론트가 청구 진단 유도 CTA 표시
    needs_policy: bool = False
    disclaimer: str = Field(
        default="본 안내는 일반적인 실손의료보험 표준약관 기준 참고용이며, "
        "정확한 판단은 가입하신 약관과 보험사 심사에 따릅니다."
    )


# ---------------------------------------------------------------------------
# 다중 실손 비교 (Sprint 33 L3)
# ---------------------------------------------------------------------------


class DeductibleView(BaseModel):
    """세대별 자기부담 요약 — 비교표 셀(금액 없이도 표시 가능)."""

    model_config = ConfigDict(extra="forbid")

    generation: int | None = None                 # 실손 세대(1~4). None=미상
    covered_rate: float                           # 급여 자기부담률 (0~1)
    non_covered_rate: float                       # 비급여 자기부담률 (0~1)
    outpatient_min_copay: int                     # 통원 최소 공제(원)
    payable_estimate: int | None = None           # 예상 청구가능액(금액 있을 때만)
    prorated_share: int | None = None             # 비례분담 후 이 보험 분담액(다건+금액)


class PolicyAssessment(BaseModel):
    """보험사 1건의 판정 — 기존 AssistantAssessment 를 inner 로 재사용."""

    model_config = ConfigDict(extra="forbid")

    insurer_id: str
    insurer: str
    product: str
    policy_no: str
    assessment: AssistantAssessment
    deductible: DeductibleView


class AssistantComparison(BaseModel):
    """comparison 모드 — 여러 실손을 각각 판정해 비교(Sprint 33 L3).

    실손 중복은 비례분담(이중 수령 불가)이므로 '더 받는 법'이 아니라 '어느 약관이
    이 상황에 유리한지(세대·자기부담) + 비례가 어떻게 나뉘는지'를 제시한다.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["comparison"] = "comparison"
    policies: list[PolicyAssessment] = Field(..., min_length=2)
    summary: str = Field(..., min_length=10)          # 결정론 비교 요약(어느 약관 유리 + 비례분담)
    recommended_policy_no: str | None = None          # 자기부담 유리(비례분담 전제 하)
    disclaimer: str = Field(
        default="실손보험은 중복가입해도 실제 낸 의료비 한도 안에서 비례로 나눠 지급되며, "
        "이중으로 더 받지는 못합니다. 본 비교는 참고용입니다."
    )


# ---------------------------------------------------------------------------
# 통합 응답 (POST /sessions/{id}/messages)
# ---------------------------------------------------------------------------


class SessionResponse(BaseModel):
    """POST /sessions/{id}/messages 응답.

    `assistant` 는 AssistantAsk / AssistantAssessment / AssistantAnswer /
    AssistantComparison 중 하나. discriminator(`type`) 으로 클라이언트 분기.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    turn: int = Field(..., ge=1, description="이번 메시지가 몇 번째 대화 턴인지")
    assistant: (
        AssistantAsk | AssistantAssessment | AssistantAnswer | AssistantComparison
    ) = Field(..., discriminator="type")
    slots: SlotState
    status: SessionStatus


# 전방 참조 해소 — Session/SlotSeedRequest 가 뒤에 정의된 PolicyRef/AssistantComparison/
# AssistantAssessment 를 forward ref 로 참조 → 재빌드.
Session.model_rebuild()
SlotSeedRequest.model_rebuild()
