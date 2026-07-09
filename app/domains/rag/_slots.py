"""app.domains.rag._slots

파일 경로: app/rag/_slots.py
목적: SlotState → 검색 query / filter 변환. 기존 sessions.service 의 동명 함수를 이전.

본 모듈은 RAG 채널 (vector / graph) 들이 공통으로 슬롯을 해석하는 지점.
sessions.service 는 이 모듈을 직접 import 하지 않는다 (RagService 가 캡슐화).
"""

from __future__ import annotations

from typing import Any

from app.domains.sessions.schemas import SlotState

# 한글 보험사명(및 흔한 변형) → data/raw 폴더 코드(insurer_id).
# 벡터 메타의 insurer_id 와 일치시켜 "가입 보험사가 아닌 다른 보험사 약관 인용"을 차단한다.
# 실손 전용 5개 손보사 (Sprint 27). 신규 보험사 적재 시 여기 추가.
_INSURER_NAME_TO_CODE: dict[str, str] = {
    "삼성화재": "samsung",
    "현대해상": "hyundai",
    "메리츠화재": "meritz",
    "메리츠": "meritz",
    "한화손해보험": "hanwha",
    "한화손보": "hanwha",
    "롯데손해보험": "lotte",
    "롯데손보": "lotte",
}


def insurer_to_code(insurer: str | None) -> str | None:
    """한글 보험사명 → insurer_id 코드. 매핑 실패 시 None (필터 미적용).

    정확 매칭 우선, 실패 시 부분 매칭("삼성화재해상보험" → samsung).
    """
    if not insurer:
        return None
    name = insurer.strip()
    if name in _INSURER_NAME_TO_CODE:
        return _INSURER_NAME_TO_CODE[name]
    for key, code in _INSURER_NAME_TO_CODE.items():
        if key in name:
            return code
    return None


# insurer_id 코드 → 대표 한글명. 적재 메타(insurer_name)가 코드로 저장돼 있어
# 인용 카드에 코드가 노출되던 문제(감사 M-3)를 표시 시점에 교정한다.
_INSURER_CODE_TO_NAME: dict[str, str] = {
    "samsung": "삼성화재",
    "hyundai": "현대해상",
    "meritz": "메리츠화재",
    "hanwha": "한화손해보험",
    "lotte": "롯데손해보험",
}


def insurer_display_name(insurer_id: str | None, fallback: str | None = None) -> str:
    """insurer_id 코드 → 한글 보험사명. 매핑 실패 시 fallback(코드가 아닌 한글이면) 또는 코드."""
    if insurer_id and insurer_id in _INSURER_CODE_TO_NAME:
        return _INSURER_CODE_TO_NAME[insurer_id]
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


def slots_to_question(slots: SlotState) -> str:
    """슬롯을 그래프 채널용 자연어 질문으로 변환. (구 GraphCypherQAChain 잔재 — 현재 미사용 가능)

    vector 의 query 와 달리 graph 는 LLM 이 Cypher 를 만들어야 하므로 더 명시적인 한국어 문장.
    Sprint 4 graph 모드 진입 시 사용.
    """
    if not slots.area:
        return "약관 상 보험금 지급 사유와 관련된 조항을 찾아 주세요."

    area_korean = {
        "accident_disease": "실손의료보험",
    }.get(slots.area, slots.area)

    parts: list[str] = [f"{area_korean} 약관에서"]
    if slots.product:
        parts.append(f"상품명 '{slots.product}' 와 관련해")
    if slots.diagnosis:
        parts.append(f"진단명 '{slots.diagnosis}' 관련")
    parts.append("보험금 지급 사유와 면책 조항을 찾아 주세요.")
    return " ".join(parts)
