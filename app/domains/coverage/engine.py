"""app.domains.coverage.engine

실손 보장 판정의 결정론 평가기(심볼릭). 자연어를 보지 않고 ClaimFacts 만 소비한다.

평가 순서(PM-35):
    1) 보장기간(사고일 ∈ 계약기간) — 하드 배제
    2) 면책(보상하지 않는 사항)
    3) 기본 보장 성립 → 자기부담 산정
    4) 판정 불가 → 부족 사실(missing) 도출 / 조건부

원칙: 정보가 부족하면 추측하지 않고 INSUFFICIENT_INFO 를 반환한다(3원칙 단정금지).
모든 결론에는 발화 규칙(rule_id)과 약관 조항 근거(clause_ref)가 붙어 감사가능하다.
"""

from __future__ import annotations

from app.domains.coverage.rules import (
    CoverageRule,
    compute_deductible,
    rules_for,
)
from app.domains.coverage.schemas import (
    ClaimFacts,
    CoverageAssessment,
    CoverageOutcome,
    RuleHit,
    RuleKind,
)


def _hit(rule: CoverageRule) -> RuleHit:
    return RuleHit(
        rule_id=rule.id,
        kind=rule.kind,
        title=rule.title,
        clause_ref=rule.clause_ref,
        rationale=rule.rationale,
    )


def _fire(rules: list[CoverageRule], kind: RuleKind, facts: ClaimFacts) -> list[RuleHit]:
    return [_hit(r) for r in rules if r.kind == kind and r.when(facts)]


def _missing_for_decision(facts: ClaimFacts) -> list[str]:
    """기본 보장 판정에 반드시 필요한 사실 중 비어있는 것."""
    missing: list[str] = []
    if facts.treatment_type is None:
        missing.append("treatment_type")  # 입원/통원/수술 구분
    return missing


def evaluate(facts: ClaimFacts) -> CoverageAssessment:
    """ClaimFacts → 결정론 보장 판정."""
    applicable = rules_for(facts)
    needs_generation = facts.generation is None

    # 1) 보장기간(하드 배제)
    period_hits = _fire(applicable, RuleKind.COVERAGE_PERIOD, facts)
    if period_hits:
        return CoverageAssessment(
            outcome=CoverageOutcome.EXCLUDED,
            hits=period_hits,
            reasons=[h.rationale for h in period_hits],
            needs_generation=needs_generation,
        )

    # 2) 면책
    exclusion_hits = _fire(applicable, RuleKind.EXCLUSION, facts)
    if exclusion_hits:
        return CoverageAssessment(
            outcome=CoverageOutcome.EXCLUDED,
            hits=exclusion_hits,
            reasons=[h.rationale for h in exclusion_hits],
            needs_generation=needs_generation,
        )

    # 3) 기본 보장 성립
    basis_hits = _fire(applicable, RuleKind.COVERED_BASIS, facts)
    if basis_hits:
        reasons = [h.rationale for h in basis_hits]
        missing: list[str] = []
        deductible = compute_deductible(facts)
        if deductible is None:
            missing.append("benefit_split")
            reasons.append("정확한 자기부담(공제) 계산에는 급여/비급여 금액 구분이 필요합니다.")
        if facts.policy_start_date is None or facts.policy_end_date is None:
            reasons.append("보장기간 확인을 위해 계약 시작·만료일 정보가 있으면 더 정확합니다.")
        return CoverageAssessment(
            outcome=CoverageOutcome.COVERED,
            hits=basis_hits,
            deductible=deductible,
            reasons=reasons,
            missing=missing,
            needs_generation=needs_generation,
        )

    # 4) 판정 불가
    missing = _missing_for_decision(facts)
    if missing:
        return CoverageAssessment(
            outcome=CoverageOutcome.INSUFFICIENT_INFO,
            missing=missing,
            reasons=["보장 여부 판정에 필요한 정보가 부족합니다."],
            needs_generation=needs_generation,
        )

    # 사실은 있으나 기본 보장 요건과 다름 → 조건부(특약/한도 확인)
    return CoverageAssessment(
        outcome=CoverageOutcome.CONDITIONAL,
        reasons=["기본 보장 요건과 달라 특약·보장한도 확인이 필요합니다."],
        needs_generation=needs_generation,
    )
