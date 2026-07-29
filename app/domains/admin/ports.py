"""admin.ports — 그래프 시각화 데이터 소스 계약 (헥사고날 seam, 사용자 결정).

관리자 그래프 UI(사이드바 트리·Sigma 캔버스·경로)는 이 포트만 소비한다.
어댑터 교체 계획:
    - 현재: MemgraphGraphSource (service.py — 우리 심볼릭 채널)
    - 예정: 연구팀 TDD 트리 산출물(output_json_save/ + knowledge_graphs/*.json) 어댑터
      → 이 Protocol 만 구현하면 UI·라우터·스코프 로직 무변경으로 교체된다.

계약 요약 (contract 테스트가 강제):
    fetch_graph  → {"nodes":[{id,node_type,label,...}], "edges":[{edge_id,source,target,
                    relation_type}], "node_count", "edge_count"}. scope 는 루트 노드 id 로
                    하향 서브그래프 절단(형제·상위 미포함).
    list_scopes  → 사이드바 트리 [{insurer_id,node_id,label,documents:[{node_id,label,
                    doc_type,clause_count,clauses:[{node_id,label,child_count}]}]}]
    shortest_path→ fetch_graph 가 준 뷰와 동일 데이터에서 무방향 최단 경로
                    {"nodes":[...], "edges":[...], "hop_count"} 또는 None.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class GraphSourcePort(Protocol):
    """그래프 시각화 데이터 소스 — 어댑터가 구현해야 하는 전부."""

    def fetch_graph(
        self, insurer_id: str | None = None, scope: str | None = None
    ) -> dict[str, Any]: ...

    def list_scopes(self) -> list[dict[str, Any]]: ...

    def shortest_path(
        self, graph: dict[str, Any], source: str, target: str
    ) -> dict[str, Any] | None: ...

    def node_content(self, node_id: str) -> dict[str, Any] | None:
        """노드 본문 — 조항/하위항의 약관 원문 텍스트 + 하위 목록
        [{id,label,node_type,preview}]. 합성 노드(root/section:*)도 응답. 미존재 시 None."""
        ...

    def document_tree(self) -> dict[str, Any]:
        """TDD 트리 {virtual_root, nodes:[{id,label,node_type,order,child_count,
        preview}], edges:[{source,target}]} — 좌측 트리 캔버스 계약.
        깊이 6단: Root→Insurer→Document→Section(합성 id 'section:<doc>:<n>')→
        Clause→SubClause. Section id 는 fetch_graph 의 scope 로도 유효해야 한다."""
        ...
