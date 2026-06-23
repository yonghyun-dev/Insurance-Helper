"""app.domains.rag.prompts

파일 경로: app/rag/prompts.py
목적: GraphCypherQAChain few-shot + ReAct Think 프롬프트.

설계 참조: docs/design/graph-schema.md (스키마 + Cypher 예시)
"""

from __future__ import annotations

CYPHER_FEW_SHOT_EXAMPLES = """
다음은 한국어 보험약관 도메인 질문과 Neo4j Cypher 의 매핑 예시입니다.

# 예시 1 — 특정 보험사의 자동차 약관 보험금 지급 사유
질문: 한화손해보험 자동차 약관에서 보험금 지급 사유 조항은?
Cypher:
MATCH (i:Insurer)-[:SELLS]->(p:Product {area: 'auto'})
      -[:HAS_VERSION]->(v:Version {is_active: true})
      -[:HAS_DOCUMENT]->(d:Document {doc_type: 'terms'})
      -[:CONTAINS]->(c:Clause)
WHERE i.name CONTAINS '한화' AND c.text CONTAINS '보험금 지급 사유'
RETURN c.chunk_id, c.clause_no, c.text, c.page_start
ORDER BY c.page_start LIMIT 8;

# 예시 2 — 특정 조항의 모든 항/호 (계층)
질문: 제6조의 모든 항과 호 본문 보여줘.
Cypher:
MATCH (c:Clause {clause_no: '제6조'})-[:HAS_SUBCLAUSE*1..3]->(s:SubClause)
RETURN c.chunk_id, c.clause_no, s.chunk_id, s.sub_no, s.text, s.page_start
ORDER BY s.page_start;

# 예시 3 — 영역별 적재된 보험사/상품 목록
질문: 자동차 영역에 어떤 보험사와 상품이 있어?
Cypher:
MATCH (i:Insurer)-[:SELLS]->(p:Product {area: 'auto'})
RETURN DISTINCT i.id AS insurer_id, i.name AS insurer, p.id AS product_id, p.name AS product;

# 예시 4 — 화재 약관에서 면책 / 손해 키워드
질문: 화재 약관에서 면책 또는 손해 관련 조항은?
Cypher:
MATCH (p:Product {area: 'fire'})-[:HAS_VERSION]->(v:Version {is_active: true})
      -[:HAS_DOCUMENT]->(d:Document)-[:CONTAINS]->(c:Clause)
WHERE c.text CONTAINS '면책' OR c.text CONTAINS '손해'
RETURN c.chunk_id, c.clause_no, c.text, c.page_start
ORDER BY c.page_start LIMIT 8;

규칙:
- RETURN 절에 `chunk_id` 를 가능한 한 포함 (감사 추적용)
- Clause 와 SubClause 둘 다 매칭 가능하면 union 으로 모두 RETURN
- LIMIT 8 또는 10 (기본). 너무 큰 결과 차단
"""


REACT_THINK_PROMPT = """
당신은 보험약관 검색 에이전트입니다. 사용자 슬롯과 직전 검색 결과를 보고
다음 행동을 결정하세요.

[입력]
- 슬롯: {slots}
- 직전 검색 결과 (top_k 청크): {chunks_summary}
- 누적 반복 횟수: {iter} / 최대: {max_iter}

[가능한 행동]
1. FINISH — 현재 누적된 청크로 청구 가능성 평가 충분. 종료.
2. REFINE — 검색 결과 부족. 다음 검색 쿼리를 다르게 (refine) 시도.

[종료 조건 — 우선순위 순]
- 누적 청크 수 >= 3개 (서로 다른 조항)
- 단일 청크 score > 0.92
- iter == max_iter (강제)

[출력 형식]
JSON: {{"action": "FINISH" | "REFINE", "refine_query": "...새 검색어..." (REFINE 시만)}}
"""
