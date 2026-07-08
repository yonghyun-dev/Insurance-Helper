"""app.domains.coverage.rules

실손 보장 판정 규칙의 **선언적 카탈로그**.

확장 원칙 (PM-35 D3/D4):
    - 규칙은 scope(area·generation·insurer·effective)로 적용 범위를 한정하는 데이터다.
    - 새 보험사/세대/특약 = 규칙(엔트리) 추가로 확장한다. 엔진(engine.py)은 불변.
    - 지금은 인메모리 카탈로그. 규모 확장 시 DB/YAML 외부화 경로를 열어둔다
      (CoverageRule 은 순수 데이터 + 단일 predicate 라 직렬화 가능한 구조).

주의: clause_ref 는 세대/보험사 무관한 표준 조항 라벨이다. 실제 인용은 Phase 2 통합에서
      해당 보험사 청크로 해석한다(여기서는 판정 근거 라벨만 확정).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from app.domains.coverage.schemas import (
    ClaimFacts,
    ClaimPurpose,
    DeductibleBreakdown,
    RuleKind,
    TreatmentType,
)

AREA_SILSON = "accident_disease"


@dataclass(frozen=True)
class RuleScope:
    """규칙 적용 범위. None/빈 집합은 '전체'를 의미한다."""

    areas: frozenset[str] = field(default_factory=lambda: frozenset({AREA_SILSON}))
    generations: frozenset[int] | None = None  # None = 전 세대
    insurers: frozenset[str] | None = None  # None = 전 보험사
    effective_from: date | None = None
    effective_to: date | None = None

    def applies_to(self, facts: ClaimFacts) -> bool:
        area = facts_area(facts)
        if self.areas and area not in self.areas:
            return False
        if self.generations and facts.effective_generation not in self.generations:
            return False
        if self.insurers and (facts.insurer_id or "") not in self.insurers:
            return False
        # effective 기간은 사고일 기준(약관 개정 이력 대응)
        if facts.incident_date:
            if self.effective_from and facts.incident_date < self.effective_from:
                return False
            if self.effective_to and facts.incident_date > self.effective_to:
                return False
        return True


def facts_area(_facts: ClaimFacts) -> str:
    """현재 실손 전용 — 단일 area. 다영역 확장 시 facts 에 area 필드 추가."""
    return AREA_SILSON


@dataclass(frozen=True)
class CoverageRule:
    """선언적 보장 규칙. when(facts) 이 참이면 발화한다."""

    id: str
    kind: RuleKind
    title: str
    when: Callable[[ClaimFacts], bool]
    clause_ref: str
    rationale: str
    scope: RuleScope = field(default_factory=RuleScope)
    priority: int = 100  # 낮을수록 먼저 평가(동일 kind 내)
    version: str = "2026.1"


# ---------------------------------------------------------------------------
# 면책(보상하지 않는 사항) — 4세대 표준약관 제4관 계열. 목적(purpose) 기반.
# ---------------------------------------------------------------------------

_EXCLUSIONS: list[CoverageRule] = [
    CoverageRule(
        id="exc_cosmetic",
        kind=RuleKind.EXCLUSION,
        title="미용·성형 목적",
        when=lambda f: f.purpose == ClaimPurpose.COSMETIC,
        clause_ref="제4조(보상하지 않는 사항) — 외모개선 목적의 치료",
        rationale="외모 개선(미용·성형) 목적의 치료는 실손에서 보상하지 않습니다.",
    ),
    CoverageRule(
        id="exc_preventive",
        kind=RuleKind.EXCLUSION,
        title="예방·건강검진",
        when=lambda f: f.purpose == ClaimPurpose.PREVENTIVE,
        clause_ref="제4조(보상하지 않는 사항) — 건강검진·예방접종",
        rationale="질병 치료와 직접 관련 없는 건강검진·예방접종은 보상하지 않습니다.",
    ),
    CoverageRule(
        id="exc_pregnancy",
        kind=RuleKind.EXCLUSION,
        title="임신·출산·산후기",
        when=lambda f: f.purpose == ClaimPurpose.PREGNANCY,
        clause_ref="제4조(보상하지 않는 사항) — 임신·출산·산후기 관련",
        rationale="임신·출산·산후기 관련 의료비는 보상하지 않습니다(상해로 인한 경우 등은 예외).",
    ),
    CoverageRule(
        id="exc_self_harm",
        kind=RuleKind.EXCLUSION,
        title="고의 자해",
        when=lambda f: f.purpose == ClaimPurpose.SELF_HARM,
        clause_ref="제4조(보상하지 않는 사항) — 피보험자의 고의",
        rationale="피보험자의 고의에 의한 자해는 보상하지 않습니다.",
    ),
    CoverageRule(
        id="exc_crime_war",
        kind=RuleKind.EXCLUSION,
        title="범죄·전쟁",
        when=lambda f: f.purpose == ClaimPurpose.CRIME_WAR,
        clause_ref="제4조(보상하지 않는 사항) — 범죄행위·전쟁 등",
        rationale="피보험자의 범죄행위, 전쟁·내란 등으로 인한 경우는 보상하지 않습니다.",
    ),
]

# ---------------------------------------------------------------------------
# 보장기간 — 사고일이 계약기간 내인지(하드 조건).
# ---------------------------------------------------------------------------

_PERIOD: list[CoverageRule] = [
    CoverageRule(
        id="period_out_of_coverage",
        kind=RuleKind.COVERAGE_PERIOD,
        title="보장기간 외 사고",
        when=lambda f: (
            f.incident_date is not None
            and f.policy_start_date is not None
            and f.policy_end_date is not None
            and not (f.policy_start_date <= f.incident_date <= f.policy_end_date)
        ),
        clause_ref="제1조(보험기간) — 보장개시 이후 발생한 사고",
        rationale="사고일이 보장기간(계약 개시~만료) 밖이라 청구 대상이 아닙니다.",
    ),
]

# ---------------------------------------------------------------------------
# 기본 보장 성립 — 치료 목적의 질병·상해 입원/통원/수술.
# ---------------------------------------------------------------------------

_COVERED_BASIS: list[CoverageRule] = [
    CoverageRule(
        id="basis_treatment",
        kind=RuleKind.COVERED_BASIS,
        title="질병·상해 치료 의료비",
        when=lambda f: (
            f.purpose == ClaimPurpose.TREATMENT
            and f.treatment_type
            in {TreatmentType.INPATIENT, TreatmentType.OUTPATIENT, TreatmentType.SURGERY}
        ),
        clause_ref="제3조(보상하는 사항) — 질병·상해로 인한 입원·통원 의료비",
        rationale="질병 또는 상해 치료를 위한 입원·통원 의료비는 실손 보장 대상입니다.",
    ),
]

RULES: list[CoverageRule] = [*_PERIOD, *_EXCLUSIONS, *_COVERED_BASIS]


def rules_for(facts: ClaimFacts) -> list[CoverageRule]:
    """facts 의 scope 에 해당하는 규칙만 반환(우선순위 정렬)."""
    return sorted(
        (r for r in RULES if r.scope.applies_to(facts)), key=lambda r: r.priority
    )


# ---------------------------------------------------------------------------
# 자기부담(공제) 정책 — 세대별 파라미터. 규칙과 분리한 결정론 계산.
# 4세대: 급여 20% / 비급여 30%, 통원 최소 공제(정액) 적용.
# (세대별 정확 수치는 확장 대상 — 여기서는 대표 파라미터 시드)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DeductibleParams:
    covered_rate: float
    non_covered_rate: float
    outpatient_min_copay: int  # 통원 최소 공제(정액)


DEDUCTIBLE_PARAMS: dict[int, DeductibleParams] = {
    1: DeductibleParams(covered_rate=0.0, non_covered_rate=0.0, outpatient_min_copay=5000),
    2: DeductibleParams(covered_rate=0.1, non_covered_rate=0.2, outpatient_min_copay=10000),
    3: DeductibleParams(covered_rate=0.1, non_covered_rate=0.2, outpatient_min_copay=10000),
    4: DeductibleParams(covered_rate=0.2, non_covered_rate=0.3, outpatient_min_copay=30000),
}


def compute_deductible(facts: ClaimFacts) -> DeductibleBreakdown | None:
    """세대·급여구분 기반 결정론 자기부담 산정. 금액 정보 부족 시 None."""
    covered = facts.covered_amount
    non_covered = facts.non_covered_amount
    if covered is None and non_covered is None:
        # 급여/비급여 분리 정보 없음 — 정확 계산 불가.
        if facts.charged_amount is None:
            return None
        # 총액만 아는 경우: 비급여율(보수적)로 근사하지 않고 계산 보류.
        return None

    covered = covered or 0
    non_covered = non_covered or 0
    total = facts.charged_amount if facts.charged_amount is not None else covered + non_covered

    p = DEDUCTIBLE_PARAMS[facts.effective_generation]
    rate_deductible = covered * p.covered_rate + non_covered * p.non_covered_rate
    deductible = rate_deductible
    if facts.treatment_type == TreatmentType.OUTPATIENT:
        deductible = max(rate_deductible, float(p.outpatient_min_copay))

    deductible_int = min(total, round(deductible))
    payable = max(0, total - deductible_int)
    return DeductibleBreakdown(
        charged_amount=total,
        deductible=deductible_int,
        payable_estimate=payable,
        formula=(
            f"급여 {covered:,}×{p.covered_rate:.0%} + 비급여 {non_covered:,}×{p.non_covered_rate:.0%}"
            + (f" (통원 최소공제 {p.outpatient_min_copay:,}원 적용)"
               if facts.treatment_type == TreatmentType.OUTPATIENT else "")
            + f" = 공제 {deductible_int:,}원 → 예상 청구가능 {payable:,}원"
        ),
    )
