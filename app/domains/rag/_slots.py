"""app.domains.rag._slots

파일 경로: app/rag/_slots.py
목적: SlotState → 검색 query / filter 변환. 기존 sessions.service 의 동명 함수를 이전.

본 모듈은 RAG 채널 (vector / graph) 들이 공통으로 슬롯을 해석하는 지점.
sessions.service 는 이 모듈을 직접 import 하지 않는다 (RagService 가 캡슐화).
"""

from __future__ import annotations

from typing import Any

from app.domains.sessions.schemas import SlotState


def slots_to_query(slots: SlotState) -> str:
    """슬롯을 자연어 검색 쿼리로 변환.

    PoC: 단순 영역별 dump. Sprint 5+ 에서 LLM 으로 자연어 쿼리 합성 검토.
    """
    parts: list[str] = []
    if slots.area == "auto":
        parts.append(
            f"자동차 사고 {slots.incident_type or ''} {slots.damage_type or ''}".strip()
        )
    elif slots.area == "fire":
        parts.append(f"화재 {slots.loss_type or ''} {slots.cause or ''}".strip())
        if slots.damaged_items:
            parts.append("손해 품목 " + ", ".join(slots.damaged_items))
    elif slots.area == "accident_disease":
        parts.append(f"상해 {slots.diagnosis or ''} 입원".strip())
    parts.append("보험금 지급 사유")
    return " ".join(p for p in parts if p)


def slots_to_filters(slots: SlotState) -> dict[str, Any] | None:
    """슬롯에서 Chroma where 필터 생성 (None 값 제외).

    PoC 한계 — `insurer` 필터 미적용:
        slots.insurer 는 LLM 이 사용자 자연어에서 추출한 한글 보험사명(예: "한화손해보험")이고,
        Chroma 메타의 `insurer_id` 는 폴더명 코드(예: "hanwha") 라 그대로 매칭되지 않는다.
        Sprint 5+ 에서 한글명↔코드 매핑 테이블 도입 시 본 함수에 `insurer_id` 필터 추가할 것.
    """
    f: dict[str, Any] = {}
    if slots.area:
        f["area"] = slots.area
    return f or None


def slots_to_question(slots: SlotState) -> str:
    """슬롯을 GraphCypherQAChain 에 던질 자연어 질문으로 변환.

    vector 의 query 와 달리 graph 는 LLM 이 Cypher 를 만들어야 하므로 더 명시적인 한국어 문장.
    Sprint 4 graph 모드 진입 시 사용.
    """
    if not slots.area:
        return "약관 상 보험금 지급 사유와 관련된 조항을 찾아 주세요."

    area_korean = {
        "auto": "자동차보험",
        "fire": "주택화재보험",
        "accident_disease": "상해/질병보험",
    }.get(slots.area, slots.area)

    parts: list[str] = [f"{area_korean} 약관에서"]
    if slots.product:
        parts.append(f"상품명 '{slots.product}' 와 관련해")
    if slots.area == "auto" and slots.incident_type:
        parts.append(f"'{slots.incident_type}' 사고에 대한")
    elif slots.area == "fire" and slots.loss_type:
        parts.append(f"'{slots.loss_type}' 손해에 대한")
    elif slots.area == "accident_disease" and slots.diagnosis:
        parts.append(f"진단명 '{slots.diagnosis}' 관련")
    parts.append("보험금 지급 사유와 면책 조항을 찾아 주세요.")
    return " ".join(parts)
