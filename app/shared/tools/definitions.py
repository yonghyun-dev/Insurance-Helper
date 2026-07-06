"""app.shared.tools.definitions

파일 경로: app/tools/definitions.py
목적: LLM agent 가 호출 가능한 tool 다발의 OpenAI Function Calling 정의.

Sprint 11 ReAct 본격 활성화의 핵심 — LLM 이 본 정의를 받고 자가 라우팅.

설계 참고:
    - docs/design/agent-architecture.md § 3.3 tool 카탈로그 (8 tool)
    - docs/design/external-apis.md § 1.5 / 2.4 / 3.3 / 4.2 (외부 tool 정의)

구조:
    - ALL_TOOLS: 모든 tool 의 Function Calling 정의 list
    - TOOLS_BY_AREA: 영역별 (accident_disease 단일, 실손 전용) 의무·권장 tool 매핑
    - 각 tool 의 실 구현은 app.shared.tools.dispatcher 가 라우팅

Sprint 11 단계적 활성화:
    - Sprint 10 까지: deterministic 2 tool 만 활성. 외부 tool 은 stub
    - Sprint 11: 모든 tool 활성 + ReAct loop 가 LLM 자가 라우팅
"""

from __future__ import annotations

from typing import Any, Literal

ToolDef = dict[str, Any]  # OpenAI Function Calling JSON Schema


# ---------------------------------------------------------------------------
# 약관 RAG (기존)
# ---------------------------------------------------------------------------

SEARCH_TERMS: ToolDef = {
    "type": "function",
    "function": {
        "name": "search_terms",
        "description": (
            "보험 약관 청크를 검색한다. Chroma 벡터 검색 + Neo4j 그래프 검색을 합성 (hybrid). "
            "모든 영역에서 의무 호출. 슬롯 (보험사·상품·영역) 을 query 로 활용."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색 키워드 (예: '추돌 사고 과실비율 자기부담금')",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# 외부 read-only tool (Sprint 9)
# ---------------------------------------------------------------------------

LOOKUP_LAW_CLAUSE: ToolDef = {
    "type": "function",
    "function": {
        "name": "lookup_law_clause",
        "description": (
            "국가법령정보센터 (law.go.kr) 에서 법령 조항을 검색해 본문과 출처 URL 을 반환. "
            "약관에 명시되지 않은 법적 권리 안내 시 호출. 모든 영역에서 권장."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "law_name": {
                    "type": "string",
                    "description": "법령명 (예: '보험업법', '상법', '자동차손해배상보장법')",
                },
                "keyword_or_article": {
                    "type": "string",
                    "description": "검색 키워드 또는 조항 번호 (예: '계약 해지' 또는 '제4조')",
                },
            },
            "required": ["law_name", "keyword_or_article"],
        },
    },
}

GET_DISEASE_CODE: ToolDef = {
    "type": "function",
    "function": {
        "name": "get_disease_code",
        "description": (
            "한국어 진단명을 KCD-8 코드로 변환 (HIRA 공공데이터). "
            "accident_disease 영역에서 정확한 진단 분류 시 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "diagnosis_korean": {
                    "type": "string",
                    "description": "사용자가 입력한 진단명 (예: '발목 골절')",
                },
            },
            "required": ["diagnosis_korean"],
        },
    },
}

# ---------------------------------------------------------------------------
# Deterministic Python tool (Sprint 10 — 이미 구현)
# ---------------------------------------------------------------------------

CALC_CLAIM_AMOUNT: ToolDef = {
    "type": "function",
    "function": {
        "name": "calc_claim_amount",
        "description": (
            "보험금 deterministic 산정 = max(0, 손해액 × (1 - 과실비율/100) - 자기부담금). "
            "LLM 산수 환각 회피. 청구 금액 산정이 필요할 때 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "loss_amount": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "손해액 (원)",
                },
                "fault_ratio": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "본인 과실비율 (0~100, 기본 0)",
                },
                "deductible": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "자기부담금 (원, 기본 0)",
                },
            },
            "required": ["loss_amount"],
        },
    },
}

VALIDATE_COVERAGE_PERIOD: ToolDef = {
    "type": "function",
    "function": {
        "name": "validate_coverage_period",
        "description": (
            "사고일이 보장기간 (policy_start ~ policy_end) 안에 있는지 deterministic 검증. "
            "LLM 날짜 계산 환각 회피. 모든 영역에서 의무 호출."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "incident_date": {
                    "type": "string",
                    "format": "date",
                    "description": "사고 발생일 (ISO 8601 'YYYY-MM-DD')",
                },
                "policy_start_date": {
                    "type": "string",
                    "format": "date",
                    "description": "보장 시작일",
                },
                "policy_end_date": {
                    "type": "string",
                    "format": "date",
                    "description": "보장 만료일",
                },
            },
            "required": ["incident_date", "policy_start_date", "policy_end_date"],
        },
    },
}


# ---------------------------------------------------------------------------
# 종료 신호 (ReAct loop 종료 — LLM 이 "정보 충분, 답변 생성" 선언)
# ---------------------------------------------------------------------------

FINISH: ToolDef = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": (
            "수집한 정보로 충분히 답변할 수 있을 때 호출. "
            "본 호출 후 ReAct loop 종료 + generate_assessment 단계로 진입."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "종료 이유 (예: 'all required slots filled + 3 sources gathered')",
                },
            },
            "required": ["reason"],
        },
    },
}


# ---------------------------------------------------------------------------
# 전체 tool 카탈로그
# ---------------------------------------------------------------------------

# 실손 전용 피벗(PM-33) — auto/fire tool(get_fault_ratio_standard/get_product_meta) 제거.
ALL_TOOLS: list[ToolDef] = [
    SEARCH_TERMS,
    LOOKUP_LAW_CLAUSE,
    GET_DISEASE_CODE,
    CALC_CLAIM_AMOUNT,
    VALIDATE_COVERAGE_PERIOD,
    FINISH,
]


# ---------------------------------------------------------------------------
# 영역별 의무·권장 tool (LLM system prompt 가이드용)
# ---------------------------------------------------------------------------

Area = Literal["accident_disease"]

TOOLS_BY_AREA: dict[Area, dict[str, list[str]]] = {
    "accident_disease": {
        "mandatory": ["search_terms", "validate_coverage_period"],
        "recommended": [
            "lookup_law_clause",
            "get_disease_code",
            "calc_claim_amount",
        ],
    },
}


def tool_names() -> list[str]:
    """전체 tool 이름 리스트 반환 (dispatcher 검증용)."""
    return [t["function"]["name"] for t in ALL_TOOLS]


def tools_for_area(area: Area) -> dict[str, list[str]]:
    """영역별 의무·권장 tool 이름 dict 반환."""
    return TOOLS_BY_AREA[area]
