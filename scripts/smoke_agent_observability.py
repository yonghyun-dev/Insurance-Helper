"""Sprint 24 라이브 스모크 — 단일 LangGraph 에이전트 + 토큰/latency 관측성 확인.

실제 Upstage Solar 호출 + dispatcher(search_terms→Chroma) 라운드트립.
실행: uv run python scripts/smoke_agent_observability.py
"""

from __future__ import annotations

from datetime import date

from app.domains.rag.service import run_agent
from app.domains.sessions.schemas import SlotState


def main() -> None:
    slots = SlotState(
        area="auto",
        insurer="한화손해보험",
        product="개인용자동차보험",
        incident_date=date(2026, 3, 15),
        incident_type="추돌",
    )
    result = run_agent(slots, "주차장에서 후진하다 추돌했어요. 보험금 받을 수 있나요?")

    print(f"finish_reason = {result.finish_reason}")
    print(f"iterations    = {result.iterations}")
    print(f"chunks        = {len(result.chunks)}")
    print(f"llm_calls     = {len(result.llm_calls)}")
    total = sum((c.get('total_tokens') or 0) for c in result.llm_calls)
    print(f"total_tokens  = {total}")
    for i, c in enumerate(result.llm_calls):
        print(
            f"  LLM[{i}] model={c.get('model')} "
            f"prompt={c.get('prompt_tokens')} completion={c.get('completion_tokens')} "
            f"latency_ms={c.get('latency_ms')}"
        )
    print("tool_results:")
    for tr in result.tool_results:
        print(
            f"  {tr['tool']:24} ok={tr.get('ok')} latency_ms={tr.get('latency_ms')}"
        )


if __name__ == "__main__":
    main()
