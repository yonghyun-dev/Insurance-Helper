"""app.domains.coverage.proration

Sprint 33 L3 — 다중 실손 비교/비례분담(결정론, LLM 0회).

실손 중복가입은 각 계약의 보상책임액 비율로 안분(비례보상)되며 총액은 실제 의료비를
넘지 못한다(이중 수령 불가). 본 모듈은 보험사별 판정(CoverageAssessment)들을 받아:
  1. 세대별 자기부담률 비교 (금액 없이도 — DEDUCTIBLE_PARAMS)
  2. 금액(payable_estimate) 있으면 비례 안분 수치
  3. "어느 약관이 이 상황에 유리한지" 결정론 판단 + 비례분담 설명 텍스트
를 산출한다. coverage 엔진(evaluate)은 계약 단위 불변 — 본 모듈은 그 위 오케스트레이션.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.coverage.rules import DEDUCTIBLE_PARAMS
from app.domains.coverage.schemas import CoverageAssessment, CoverageOutcome

_GEN_LABEL = {1: "1세대", 2: "2세대", 3: "3세대", 4: "4세대"}


@dataclass
class PolicyProration:
    """비교표 1행 — 보험사별 자기부담 요약 + (다건+금액 시) 안분액."""

    policy_no: str
    generation: int | None
    covered_rate: float
    non_covered_rate: float
    outpatient_min_copay: int
    payable_estimate: int | None
    prorated_share: int | None  # 비례분담 후 이 보험 분담액


@dataclass
class ProrationResult:
    per_policy: dict[str, PolicyProration]  # policy_no → 요약
    summary: str
    recommended_policy_no: str | None


def _deductible_view(gen: int | None) -> tuple[float, float, int]:
    """세대 → (급여 자기부담률, 비급여 자기부담률, 통원 최소공제). 미상은 4세대 표준가정."""
    params = DEDUCTIBLE_PARAMS[gen or 4]
    return params.covered_rate, params.non_covered_rate, params.outpatient_min_copay


def compute(
    items: list[tuple[str, int | None, CoverageAssessment]],
) -> ProrationResult:
    """보험사별 (policy_no, generation, CoverageAssessment) → 비교/비례분담 결과.

    Args:
        items: 보험별 판정. generation 은 해당 계약 세대(None=미상→4세대 가정).
    """
    per: dict[str, PolicyProration] = {}
    payables: dict[str, int] = {}
    for policy_no, gen, cov in items:
        cr, ncr, mc = _deductible_view(gen)
        payable = cov.deductible.payable_estimate if cov.deductible else None
        per[policy_no] = PolicyProration(
            policy_no=policy_no, generation=gen,
            covered_rate=cr, non_covered_rate=ncr, outpatient_min_copay=mc,
            payable_estimate=payable, prorated_share=None,
        )
        # 안분 대상: 보장(covered) 판정 + payable 양수인 계약만
        if cov.outcome == CoverageOutcome.COVERED and payable and payable > 0:
            payables[policy_no] = payable

    # 비례 안분(비례보상): 중복가입이어도 실제 보상총액은 한 계약이 낼 최대치(≈max payable)를
    # 넘지 못하고, 각사는 자기 보상책임액 비율로 나눠 분담한다.
    #   총지급 = max(payable),  share_i = 총지급 × payable_i / Σpayable_j
    total_resp = sum(payables.values())
    if len(payables) >= 2 and total_resp > 0:
        actual_payout = max(payables.values())
        for policy_no, payable in payables.items():
            per[policy_no].prorated_share = round(actual_payout * payable / total_resp)

    summary, recommended = _summarize(items, per, bool(payables) and len(payables) >= 2)
    return ProrationResult(per_policy=per, summary=summary, recommended_policy_no=recommended)


def _summarize(
    items: list[tuple[str, int | None, CoverageAssessment]],
    per: dict[str, PolicyProration],
    prorated: bool,
) -> tuple[str, str | None]:
    """결정론 비교 요약 + 추천(자기부담 유리) 산출."""
    covered = [(pn, gen, cov) for pn, gen, cov in items if cov.outcome == CoverageOutcome.COVERED]
    lines: list[str] = []

    # 어느 약관이 유리한가 — 보장되는 계약 중 비급여 자기부담률이 가장 낮은 쪽.
    recommended: str | None = None
    if covered:
        best = min(covered, key=lambda t: per[t[0]].non_covered_rate)
        recommended = best[0]
        best_gen = _GEN_LABEL.get(best[1] or 4, "표준")
        lines.append(
            f"가입하신 실손 중 **{best_gen}** 약관이 자기부담률이 낮아(비급여 "
            f"{int(per[best[0]].non_covered_rate * 100)}%) 이 치료에는 더 유리합니다."
        )

    # 세대 차이가 있으면 명시
    gens = {gen for _, gen, _ in items}
    if len(gens) >= 2:
        lines.append(
            "가입 세대가 달라 자기부담률·보장조건이 다릅니다(구세대일수록 자기부담이 대체로 낮음)."
        )

    if prorated:
        lines.append(
            "다만 실손은 중복가입해도 비례로 나눠 지급되어, 두 곳에서 각각 전액을 받는 것은 "
            "아닙니다. 아래 예상 분담액을 참고하세요."
        )
    else:
        lines.append(
            "실손은 중복가입해도 실제 낸 의료비 한도 안에서 비례로 나눠 지급됩니다(이중 수령 불가)."
        )
    return " ".join(lines), recommended
