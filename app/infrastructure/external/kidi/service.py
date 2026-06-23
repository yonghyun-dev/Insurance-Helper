"""app.infrastructure.external.kidi.service

파일 경로: app/external/kidi/service.py
목적: 손보협회 표준 과실비율 정적 데이터셋 lookup.

LLM tool `get_fault_ratio_standard` 의 실 구현.

데이터: `data/static/fault_ratio/scenarios.json` (PM 수동 적재, 분기 갱신).
법적 근거: 금감원 보험업감독업무 시행세칙 별표 15.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# 데이터 파일 위치 (repo 루트 기준). app/infrastructure/external/kidi/service.py → parents[4]=repo 루트.
_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "static" / "fault_ratio"
_SCENARIOS_PATH = _DATA_DIR / "scenarios.json"
_MANIFEST_PATH = _DATA_DIR / "manifest.json"


class _ModifierFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition: str
    delta_a: int
    delta_b: int


class FaultRatioScenario(BaseModel):
    """과실비율 단일 시나리오."""

    model_config = ConfigDict(extra="allow")  # base_ratio 의 _note 등 허용

    chart_no: str = Field(description="손보협회 표 번호 (예: '차101')")
    scenario_keyword: list[str] = Field(description="매칭용 키워드 리스트")
    scenario_description: str = Field(description="시나리오 한국어 설명")
    base_ratio: dict = Field(description="기본 과실비율 {A: int, B: int}")
    modifier_factors: list[_ModifierFactor] = Field(description="가감 요소 목록")
    source_clause: str = Field(description="인용 시 표시 문구")


@lru_cache(maxsize=1)
def _load_scenarios() -> list[FaultRatioScenario]:
    """정적 JSON 을 한 번만 로드 (lru_cache 싱글톤)."""
    if not _SCENARIOS_PATH.exists():
        logger.warning("KIDI 정적 데이터 미존재: %s", _SCENARIOS_PATH)
        return []
    raw = json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))
    return [FaultRatioScenario.model_validate(item) for item in raw]


def lookup_by_scenario(scenario_keyword: str) -> FaultRatioScenario | None:
    """키워드를 받아 가장 잘 매칭되는 시나리오 1건 반환.

    매칭 정책:
        - 키워드를 띄어쓰기로 분리해 시나리오의 scenario_keyword list 와 부분 매칭
        - 가장 많은 단어가 매칭된 시나리오 반환 (동률 시 첫 번째)
        - 매칭 0 → None (LLM 에 "표준 과실비율 데이터 없음" 전달)

    Args:
        scenario_keyword: 사용자/LLM 이 입력한 사고 키워드 (예: "신호대기 추돌")

    Returns:
        FaultRatioScenario 또는 None
    """
    scenarios = _load_scenarios()
    if not scenarios:
        return None

    query_tokens = set(scenario_keyword.split())
    if not query_tokens:
        return None

    best: FaultRatioScenario | None = None
    best_score = 0
    for sc in scenarios:
        # 각 시나리오의 키워드 set 와 query token 의 교집합 크기로 스코어
        kw_set = set()
        for kw in sc.scenario_keyword:
            kw_set.update(kw.split())
        score = len(query_tokens & kw_set)
        if score > best_score:
            best_score = score
            best = sc

    if best_score == 0:
        logger.info("KIDI lookup_by_scenario: 매칭 없음 (query=%s)", scenario_keyword)
        return None
    return best


def clear_cache() -> None:
    """테스트용 — 데이터셋 reload."""
    _load_scenarios.cache_clear()
