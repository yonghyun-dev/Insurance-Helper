"""app.shared.tools.dispatcher

파일 경로: app/tools/dispatcher.py
목적: LLM tool_call 을 실 함수 호출로 라우팅. Sprint 11 ReAct 본격 활성화의 라우터.

설계 참고:
    - docs/design/agent-architecture.md § 3.2 ReAct loop
    - docs/design/external-apis.md (외부 API 어댑터 호출 패턴)

단계적 활성화:
    - Sprint 10 (현재): deterministic 2 tool (calc, validate) + search_terms (기존) 활성.
      외부 tool 4종 (law/hira/kidi/fss) 은 stub — "not implemented" 반환
    - Sprint 11: 외부 어댑터 실 구현 후 활성

호출 패턴 (Sprint 11 ReAct):
    tool_call = llm_response.choices[0].message.tool_calls[0]
    result = dispatcher.invoke(tool_call.function.name, json.loads(tool_call.function.arguments))
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from app.shared.tools.calc import calc_claim_amount, validate_coverage_period
from app.shared.tools.definitions import tool_names

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """LLM 이 정의되지 않은 tool 을 호출 (환각)."""


class ToolNotImplementedError(Exception):
    """tool 정의는 있으나 Sprint 단계상 미구현 (stub)."""


def invoke(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """LLM tool_call 을 실 함수로 라우팅.

    Args:
        tool_name: definitions.ALL_TOOLS 의 function.name
        args: function.arguments 를 json.loads 한 dict

    Returns:
        tool 결과 dict (LLM 의 다음 turn 에 tool message 로 전달)

    Raises:
        ToolNotFoundError: 정의되지 않은 tool (LLM 환각)
        ToolNotImplementedError: 정의는 있으나 미구현 (Sprint 단계상)
    """
    if tool_name not in tool_names():
        raise ToolNotFoundError(f"정의되지 않은 tool: {tool_name}")

    logger.info("dispatcher: %s(%s)", tool_name, args)

    # Sprint 10 활성 — deterministic tools
    if tool_name == "calc_claim_amount":
        result = calc_claim_amount(
            loss_amount=args["loss_amount"],
            fault_ratio=args.get("fault_ratio", 0),
            deductible=args.get("deductible", 0),
        )
        return result.model_dump()

    if tool_name == "validate_coverage_period":
        result = validate_coverage_period(
            incident_date=_parse_iso_date(args["incident_date"]),
            policy_start_date=_parse_iso_date(args["policy_start_date"]),
            policy_end_date=_parse_iso_date(args["policy_end_date"]),
        )
        return result.model_dump(mode="json")

    # Sprint 11 search_terms 활성 — query 기반 vector 검색.
    # 주의: ReAct loop 안에서 호출되더라도 react=False 강제 (무한 재귀 회피).
    # SlotState 의존성 없음 — LLM 이 query 텍스트 직접 생성.
    if tool_name == "search_terms":
        from app.domains.search import service as search_service

        query = args["query"]
        top_k = args.get("top_k", 8)
        results = search_service.similarity_search(query, top_k=top_k)
        # Sprint 11 ReAct LLM 이 chunk_id + text 만 필요 (citations 검증에 사용)
        compact = [
            {
                "id": r["id"],
                "text": r["text"][:600],  # 토큰 절감 — 600자 자르기
                "score": r.get("score"),
                "metadata": r.get("metadata", {}),
            }
            for r in results
        ]
        return {"chunks": compact, "count": len(compact)}

    # Sprint 9 외부 어댑터 — KIDI 만 활성 (정적 데이터, API key 불필요).
    # law / hira 는 어댑터 골격은 있으나 OC/serviceKey 발급 대기 → 호출 시 NotConfiguredError.
    if tool_name == "get_fault_ratio_standard":
        from app.infrastructure.external.kidi import lookup_by_scenario

        result = lookup_by_scenario(args["scenario_keyword"])
        return result.model_dump() if result else {"matched": False}

    if tool_name == "lookup_law_clause":
        from app.infrastructure.external.law import LawNotConfiguredError, lookup_clause

        try:
            result = lookup_clause(args["law_name"], args["keyword_or_article"])
        except LawNotConfiguredError as exc:
            raise ToolNotImplementedError(str(exc)) from exc
        return result.model_dump() if result else {"matched": False}

    if tool_name == "get_disease_code":
        from app.infrastructure.external.hira import HiraNotConfiguredError, lookup_by_name

        try:
            result = lookup_by_name(args["diagnosis_korean"])
        except HiraNotConfiguredError as exc:
            raise ToolNotImplementedError(str(exc)) from exc
        return result.model_dump() if result else {"matched": False}

    if tool_name == "get_product_meta":
        from app.infrastructure.external.fss import FssNotImplementedError, get_product_meta

        try:
            result = get_product_meta(args["insurer"], args["product_name"])
        except FssNotImplementedError as exc:
            raise ToolNotImplementedError(str(exc)) from exc
        return result.model_dump() if result else {"matched": False}

    if tool_name == "finish":
        # ReAct loop 종료 신호 — Sprint 11 ReAct runner 가 처리
        return {"finished": True, "reason": args.get("reason", "")}

    raise ToolNotFoundError(f"라우팅 미정의 tool: {tool_name}")


def _parse_iso_date(value: str | date) -> date:
    """ISO 8601 'YYYY-MM-DD' 문자열 또는 date 객체 → date.

    LLM 이 보통 문자열로 전달. date 객체로 직접 전달도 허용 (테스트).
    """
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def serialize_for_llm(result: dict[str, Any]) -> str:
    """tool 결과 dict 를 LLM 에 전달할 JSON 문자열로 직렬화.

    OpenAI tool message 의 content 필드는 문자열만 가능.
    """
    return json.dumps(result, ensure_ascii=False)
