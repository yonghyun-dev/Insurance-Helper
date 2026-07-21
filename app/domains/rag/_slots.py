"""app.domains.rag._slots

파일 경로: app/rag/_slots.py
목적: SlotState → 검색 query / filter 변환. 기존 sessions.service 의 동명 함수를 이전.

본 모듈은 RAG 채널 (vector / graph) 들이 공통으로 슬롯을 해석하는 지점.
sessions.service 는 이 모듈을 직접 import 하지 않는다 (RagService 가 캡슐화).
"""

from __future__ import annotations

from typing import Any

from app.domains.sessions.schemas import SlotState

# 보험사 코드·한글명·약칭은 단일 소스(app.shared.insurers)에서 온다. 벡터 메타의
# insurer_id 와 일치시켜 "가입 보험사가 아닌 다른 보험사 약관 인용"을 차단한다(PM-43).
from app.shared import insurers as _insurers


def insurer_to_code(insurer: str | None) -> str | None:
    """한글 보험사명 → insurer_id 코드. 매핑 실패 시 None (필터 미적용).

    공백/약칭 정규화는 단일 소스 name_to_code 가 담당 — "한화 손해보험"·"한화" 모두 매핑.
    """
    return _insurers.name_to_code(insurer)


def insurer_display_name(insurer_id: str | None, fallback: str | None = None) -> str:
    """insurer_id 코드 → 한글 보험사명. 매핑 실패 시 fallback(코드가 아닌 한글이면) 또는 코드.

    적재 메타(insurer_name)가 코드로 저장돼 인용 카드에 코드가 노출되던 문제(감사 M-3)를
    표시 시점에 교정한다.
    """
    name = _insurers.code_to_name(insurer_id)
    if name:
        return name
    return (fallback or insurer_id or "").strip()


def slots_to_query(slots: SlotState) -> str:
    """슬롯을 자연어 검색 쿼리로 변환.

    PoC: 단순 영역별 dump. Sprint 5+ 에서 LLM 으로 자연어 쿼리 합성 검토.
    """
    parts: list[str] = []
    if slots.insurer:
        parts.append(slots.insurer)
    if slots.area == "accident_disease":
        parts.append(f"상해 {slots.diagnosis or ''} 입원".strip())
    parts.append("보험금 지급 사유")
    return " ".join(p for p in parts if p)


def slots_to_filters(slots: SlotState) -> dict[str, Any] | None:
    """슬롯에서 검색 where 필터 생성 (None 값 제외).

    area + insurer_id(코드) 로 필터. 다중 키가 될 수 있으므로, Chroma 어댑터는
    2개 이상 키를 `$and` 로 감싸 처리한다 (search.service.similarity_search).
    """
    f: dict[str, Any] = {}
    if slots.area:
        f["area"] = slots.area
    # 구조화 seed(마이데이터)가 insurer_id 를 직접 채웠으면 그대로 사용 — 매핑 불필요.
    # 순수 자연어 흐름(한글명만)에선 name→code 폴백.
    code = slots.insurer_id or insurer_to_code(slots.insurer)
    if code:
        f["insurer_id"] = code
    return f or None
