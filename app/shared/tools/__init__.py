"""app.shared.tools

LLM agent 의 deterministic tool 다발.

뉴로심볼릭 아키텍처의 symbolic 부분 — LLM 날짜 환각 차단 + 외부 검증 데이터 인용.

- validate_coverage_period (deterministic Python, 보장기간 검증)
- definitions (OpenAI Function Calling 정의, 실손 4 tool) + dispatcher (tool_call 라우팅)
"""

from app.shared.tools.calc import (
    CoverageValidation,
    validate_coverage_period,
)

__all__ = [
    "CoverageValidation",
    "validate_coverage_period",
]
