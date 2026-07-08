"""app.domains.coverage

실손 보장 판정 룰 엔진(뉴로심볼릭의 '심볼릭' 층).

자연어 이해/사실 추출(뉴럴)과 사실→판정(심볼릭)을 분리한다. 엔진은 ClaimFacts 만
소비해 결정론적·감사가능한 CoverageAssessment 를 반환한다(PM-35).
"""

from app.domains.coverage.engine import evaluate
from app.domains.coverage.facts import build_facts_from_slots
from app.domains.coverage.schemas import (
    ClaimFacts,
    CoverageAssessment,
    CoverageOutcome,
)

__all__ = [
    "evaluate",
    "build_facts_from_slots",
    "ClaimFacts",
    "CoverageAssessment",
    "CoverageOutcome",
]
