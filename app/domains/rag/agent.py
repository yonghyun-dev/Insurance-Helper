"""app.domains.rag.agent

파일 경로: app/rag/agent.py
목적: Sprint 11 본격 ReAct agent — LLM 이 tool 다발 자가 라우팅.

기존 `app.domains.rag.react.ReActRunner` 는 단순 retrieve 반복 + LLM Finish 결정.
본 `AgentRunner` 는 OpenAI Function Calling + `app.shared.tools.dispatcher` 통합으로
LLM 이 search_terms / lookup_law_clause / get_disease_code / get_fault_ratio_standard /
calc_claim_amount / validate_coverage_period / get_product_meta / finish 를
자가 선택. 뉴로심볼릭 아키텍처의 핵심.

설계 참조:
    - docs/design/agent-architecture.md § 3.2 ReAct loop
    - docs/design/agent-architecture.md § 3.4 Tool 선택 정책

종료 조건 (우선순위):
    1. LLM 이 `finish` tool 호출 — 정상 종료
    2. iter == max_iter — 강제 종료 (안전망)
    3. dispatcher 가 ToolNotImplementedError raise — 해당 tool 무시 + 다음 iter
    4. dispatcher 가 ToolNotFoundError raise — LLM 환각, 무시 + 다음 iter

비용 가드:
    - max_iter 5 (Sprint 4 결정 유지)
    - tool 결과는 600자 자르기 (search_terms) — 토큰 절감
    - 같은 tool 동일 인자 2회 호출 시 cache hit 강제 (정의된 외부 어댑터는 자체 캐시 사용)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from app.domains.sessions.schemas import SlotState
from app.infrastructure.llm.client import get_chat_client, get_chat_model
from app.shared.tools.definitions import ALL_TOOLS, tools_for_area
from app.shared.tools.dispatcher import (
    ToolNotFoundError,
    ToolNotImplementedError,
    invoke,
    serialize_for_llm,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITER = 5


def _get_openai_client() -> OpenAI:
    """추론 LLM 클라이언트 — 중앙 팩토리(app.infrastructure.llm.client)에 위임.

    제품 추론은 Upstage Solar 전용(provider=upstage 기본), OpenAI 폴백 없음.
    심볼명 유지 — 테스트가 본 함수를 패치한다. 캐시는 팩토리가 담당.
    """
    return get_chat_client()


@dataclass
class AgentResult:
    """AgentRunner.run 의 반환 형식.

    sessions.service 가 chunks 를 generate_assessment 에 전달 + tool_results 를
    추가 컨텍스트로 넘김 (Sprint 11 service 통합 시점에 확정).
    """

    chunks: list[dict[str, Any]] = field(default_factory=list)  # search_terms 결과 누적
    tool_results: list[dict[str, Any]] = field(default_factory=list)  # 모든 tool 호출 결과
    iterations: int = 0
    finish_reason: str = ""  # "finish" / "max_iter" / "no_tool_call"


_SYSTEM_PROMPT = """\
당신은 한국 보험청구심사 어시스턴트의 ReAct agent다.
사용자 슬롯과 대화 컨텍스트가 주어지면, 정확한 청구 가능성 답변을 위해
아래 tool 다발 중 필요한 것을 자가 판단해 호출한다.

**원칙 (강제)**:
1. 모든 영역에서 `search_terms` 를 최소 1회 호출 (약관 인용 의무)
2. 모든 영역에서 `validate_coverage_period` 호출 (사고일 ∈ 보장기간 검증, 의무)
3. 청구 금액 추정 시 `calc_claim_amount` 호출 (deterministic — LLM 산수 환각 회피)
4. 영역별 권장:
   - auto: `get_fault_ratio_standard` (표준 과실비율) + `lookup_law_clause` (자배법)
   - fire: `lookup_law_clause` (상법)
   - accident_disease: `get_disease_code` (KCD 코드) + `lookup_law_clause` (보험업법)
5. 같은 tool 을 동일 인자로 2회 호출 금지 (이미 결과를 받았다)
6. 정보 충분하면 `finish` tool 호출하여 종료 (즉시 generate_assessment 단계로 진입)
7. 최대 5회 iter — 도달 시 강제 종료

**현재 슬롯**:
{slots_summary}

**영역별 의무·권장**:
- 의무: {mandatory}
- 권장: {recommended}
"""


class AgentRunner:
    """OpenAI Function Calling 기반 ReAct loop runner.

    사용:
        runner = AgentRunner()
        result = runner.run(slots, user_message)
        # result.chunks → generate_assessment 의 chunks 인자
        # result.tool_results → 추가 컨텍스트 (선택)
    """

    def __init__(self, *, max_iter: int = DEFAULT_MAX_ITER) -> None:
        self._max_iter = max_iter
        self._called_tools: set[tuple[str, str]] = set()  # (tool_name, args_json) 중복 차단

    def run(self, slots: SlotState, user_message: str) -> AgentResult:
        """ReAct loop 실행. tool_calls 반복 후 finish 또는 max_iter 종료.

        Args:
            slots: 현재 SlotState (LLM 컨텍스트)
            user_message: 사용자 자연어 입력 (LLM user role 시작 메시지)

        Returns:
            AgentResult (chunks + tool_results + iterations + finish_reason)
        """
        client = _get_openai_client()

        area = slots.area or "auto"  # 영역 미정 시 auto 기본 (의무 tool 동일)
        area_policy = tools_for_area(area)  # type: ignore[arg-type]
        system = _SYSTEM_PROMPT.format(
            slots_summary=self._slot_summary(slots),
            mandatory=", ".join(area_policy["mandatory"]),
            recommended=", ".join(area_policy["recommended"]),
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]

        result = AgentResult()

        for it in range(self._max_iter):
            result.iterations = it + 1
            response = client.chat.completions.create(
                model=get_chat_model(),
                messages=messages,
                tools=ALL_TOOLS,
                tool_choice="auto",
                temperature=0.0,
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                # LLM 이 tool 안 부르고 텍스트 답변 — 정보 충분 가정, 종료
                logger.info("agent: no_tool_call iter=%d — 종료", it + 1)
                result.finish_reason = "no_tool_call"
                break

            # assistant message + tool_calls 를 messages 에 추가 (OpenAI 프로토콜)
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            finish_hit = False
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                # 중복 호출 차단
                key = (tool_name, json.dumps(args, sort_keys=True, ensure_ascii=False))
                if key in self._called_tools:
                    logger.info("agent: 중복 tool 호출 skip (%s)", tool_name)
                    tool_result: dict[str, Any] = {"skipped": "duplicate"}
                else:
                    self._called_tools.add(key)
                    tool_result = self._safe_invoke(tool_name, args)

                # tool 결과 누적
                result.tool_results.append({"tool": tool_name, "args": args, "result": tool_result})

                # search_terms 결과는 chunks 누적
                if tool_name == "search_terms" and "chunks" in tool_result:
                    result.chunks.extend(tool_result["chunks"])

                # finish 호출 감지
                if tool_name == "finish":
                    finish_hit = True
                    result.finish_reason = "finish"

                # tool message 응답을 messages 에 추가
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": serialize_for_llm(tool_result),
                    }
                )

            if finish_hit:
                logger.info("agent: finish iter=%d", it + 1)
                break

        if result.finish_reason == "":
            result.finish_reason = "max_iter"
            logger.warning("agent: max_iter (%d) 도달 — 강제 종료", self._max_iter)

        # chunks dedupe by id (search_terms 가 여러 번 호출됐을 수도)
        result.chunks = self._dedupe_chunks(result.chunks)
        return result

    @staticmethod
    def _safe_invoke(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """dispatcher.invoke 호출 + 모든 예외를 graceful 결과 dict 로 변환.

        LLM 이 보고 다음 turn 에 적응할 수 있도록 에러 정보도 LLM 에 전달.
        """
        try:
            return invoke(tool_name, args)
        except ToolNotImplementedError as exc:
            return {"error": "not_implemented", "tool": tool_name, "message": str(exc)}
        except ToolNotFoundError as exc:
            return {"error": "not_found", "tool": tool_name, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.error("dispatcher.invoke 예외 (%s): %s", tool_name, exc)
            return {"error": "runtime", "tool": tool_name, "message": str(exc)}

    @staticmethod
    def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """동일 chunk id 중복 제거 — score 높은 것 유지."""
        by_id: dict[str, dict[str, Any]] = {}
        for c in chunks:
            cid = str(c.get("id"))
            existing = by_id.get(cid)
            if existing is None or (c.get("score") or 0) > (existing.get("score") or 0):
                by_id[cid] = c
        return list(by_id.values())

    @staticmethod
    def _slot_summary(slots: SlotState) -> str:
        """슬롯 한 줄 요약. LLM system prompt 에 주입."""
        parts: list[str] = []
        for field_name in ("area", "insurer", "product", "incident_date", "incident_type"):
            val = getattr(slots, field_name, None)
            if val:
                parts.append(f"{field_name}={val}")
        return ", ".join(parts) or "(empty)"
