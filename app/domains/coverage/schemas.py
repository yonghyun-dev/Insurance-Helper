"""app.domains.coverage.schemas

실손 보장 판정(심볼릭)의 도메인 타입.

설계 원칙 (PM-35):
    - 사실(ClaimFacts)과 규칙(CoverageRule)을 분리 → 뉴럴(자연어→사실 추출)과
      심볼릭(사실→판정)의 경계를 명확히 한다.
    - 판정 결과(CoverageAssessment)는 결정론적이고 감사가능해야 한다: 모든 결론에
      rule_id + 약관 조항 근거(clause_ref)가 붙는다.
    - 정보가 부족하면 추측하지 않고 INSUFFICIENT_INFO + missing 을 반환한다(3원칙 단정금지).

확장성:
    - 전 국민 서비스 = 5사 × 1~4세대 × 특약. 규칙은 scope 로 적용 범위를 한정하며,
      새 보험사/세대/특약은 규칙(데이터) 추가로 확장된다(엔진 코드 불변).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TreatmentType(StrEnum):
    """치료 구분 — 실손 보장/자기부담 구조가 이 값에 따라 달라진다."""

    INPATIENT = "inpatient"  # 입원
    OUTPATIENT = "outpatient"  # 통원(외래)
    SURGERY = "surgery"  # 수술
    PRESCRIPTION = "prescription"  # 처방조제


class BenefitType(StrEnum):
    """급여/비급여 — 4세대 자기부담률이 이 값에 따라 다르다(급여 20% / 비급여 30%)."""

    COVERED = "covered"  # 급여(건강보험 급여 대상)
    NON_COVERED = "non_covered"  # 비급여


class ClaimPurpose(StrEnum):
    """청구 목적/성격 플래그 — 면책 판정의 핵심 사실. 자연어에서 뉴럴이 추출한다."""

    TREATMENT = "treatment"  # 치료 목적(기본)
    COSMETIC = "cosmetic"  # 미용·성형 목적
    PREVENTIVE = "preventive"  # 예방·건강검진
    PREGNANCY = "pregnancy"  # 임신·출산·산후기
    SELF_HARM = "self_harm"  # 고의 자해
    CRIME_WAR = "crime_war"  # 범죄·전쟁


class CoverageOutcome(StrEnum):
    """보장 판정 결과."""

    COVERED = "covered"  # 보장 성립
    EXCLUDED = "excluded"  # 면책(보상하지 않는 사항)
    CONDITIONAL = "conditional"  # 조건부(한도/특약 확인 필요 등)
    INSUFFICIENT_INFO = "insufficient_info"  # 판정에 필요한 사실 부족


class RuleKind(StrEnum):
    """규칙 종류 — 엔진의 평가 순서를 결정한다."""

    COVERAGE_PERIOD = "coverage_period"  # 보장기간(사고일 ∈ 계약기간)
    EXCLUSION = "exclusion"  # 면책(보상하지 않는 사항) — 전면 미보상
    PARTIAL = "partial"  # 조건부/부분보상 — 특정 부분만 제외·공제 (한방 비급여·산재 공제 등)
    COVERED_BASIS = "covered_basis"  # 기본 보장 성립 근거
    DEDUCTIBLE = "deductible"  # 자기부담(공제)
    LIMIT = "limit"  # 보장 한도


class ClaimFacts(BaseModel):
    """정규화된 판정 입력. 자연어에서 뉴럴이 추출/정규화한 '사실'만 담는다.

    엔진은 이 사실만 소비하며 자연어를 보지 않는다(결정론 보장).
    """

    model_config = ConfigDict(extra="forbid")

    insurer_id: str | None = Field(default=None, description="보험사 코드(예: samsung)")
    generation: int | None = Field(
        default=None, ge=1, le=4, description="실손 세대(1~4). None=미상 → 표준(4세대) 가정"
    )
    treatment_type: TreatmentType | None = None
    benefit_type: BenefitType | None = None
    diagnosis: str | None = None
    diagnosis_code: str | None = Field(default=None, description="KCD-8 코드")
    purpose: ClaimPurpose = Field(
        default=ClaimPurpose.TREATMENT, description="청구 목적(면책 판정 핵심)"
    )
    # 금액(원) — 자기부담 계산용. 청구(환자 부담) 의료비를 급여/비급여로 나눠 담는다.
    charged_amount: int | None = Field(default=None, ge=0, description="총 환자 부담 의료비")
    covered_amount: int | None = Field(default=None, ge=0, description="급여 부분 금액")
    non_covered_amount: int | None = Field(default=None, ge=0, description="비급여 부분 금액")
    # 기간
    incident_date: date | None = None
    policy_start_date: date | None = None
    policy_end_date: date | None = None
    # 진료량
    hospitalization_days: int | None = Field(default=None, ge=0)
    outpatient_visits: int | None = Field(default=None, ge=0)
    # PM-43 coverage 모델링 — 부분보상/공제 판정용 정황 사실 (뉴럴 추출, 약관 근거).
    # 근거: 한방=한의사 비급여 제외 / 해외=국내 요양기관 전제 / 치과질병=K00~K08 비급여 제외 /
    #       산재·자보=자동차보험·산재보험 발생 본인부담 제외.
    treatment_overseas: bool = Field(default=False, description="해외(국외) 의료기관 치료")
    is_oriental_medicine: bool = Field(default=False, description="한방(한의원·한의사) 치료")
    dental_disease: bool = Field(default=False, description="치과 질병(충치·치주 등, 상해 아님)")
    other_insurance_settled: bool = Field(
        default=False, description="자동차보험(대인배상)·산재보험으로 처리된 부분 존재"
    )

    @property
    def effective_generation(self) -> int:
        """판정에 사용할 세대 — 미상이면 현행 표준(4세대) 가정."""
        return self.generation or 4


class RuleHit(BaseModel):
    """발화(적용)한 규칙 1건의 감사 기록."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    kind: RuleKind
    title: str
    clause_ref: str = Field(description="근거 약관 조항(예: 제4조 보상하지 않는 사항)")
    rationale: str = Field(description="사용자에게 보여줄 판정 사유")


class DeductibleBreakdown(BaseModel):
    """자기부담 산정 내역(결정론)."""

    model_config = ConfigDict(extra="forbid")

    charged_amount: int = Field(ge=0)
    deductible: int = Field(ge=0, description="공제(자기부담)")
    payable_estimate: int = Field(ge=0, description="예상 청구 가능액")
    formula: str


class CoverageAssessment(BaseModel):
    """실손 보장 판정 결과 — 결정론·감사가능."""

    model_config = ConfigDict(extra="forbid")

    outcome: CoverageOutcome
    hits: list[RuleHit] = Field(default_factory=list)
    deductible: DeductibleBreakdown | None = None
    reasons: list[str] = Field(default_factory=list)
    missing: list[str] = Field(
        default_factory=list, description="판정에 더 필요한 사실(INSUFFICIENT_INFO 시)"
    )
    needs_generation: bool = Field(
        default=False, description="세대 미상으로 표준 가정 판정 — 실제 세대 확인 필요"
    )
