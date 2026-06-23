"""app.infrastructure.external.kidi

손해보험협회 (KIDI) 표준 과실비율 인정기준 어댑터.

공식 API 없음 → `data/static/fault_ratio/scenarios.json` 정적 데이터셋 사용.
법적 근거: 금감원 보험업감독업무 시행세칙 별표 15 (자동차보험표준약관 별표 3).

Sprint 9 — 외부 API key 불필요. 즉시 활성 가능.
"""

from app.infrastructure.external.kidi.service import FaultRatioScenario, lookup_by_scenario

__all__ = ["FaultRatioScenario", "lookup_by_scenario"]
