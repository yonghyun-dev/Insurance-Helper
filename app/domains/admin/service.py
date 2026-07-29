"""admin.service — Memgraph 그래프를 시각화용 node-link JSON 으로 변환.

설계 (연구팀 graphrag-viz 패턴 이식, PM 결정):
    - 서버는 스코프 필터(보험사)만 담당하고 스타일·레이아웃은 전부 클라이언트(Sigma.js).
    - 노드 id 는 라벨 접두("insurer:", "clause:" 등)로 전 라벨 유일성을 보장한다.
    - 보험사 스코프는 문자열 매칭이 아니라 **그래프 연결성(BFS)** 으로 자른다 —
      Insurer 노드에서 도달 가능한 서브그래프가 곧 그 보험사의 자산(구조가 진실).
    - 경로 탐색도 서빙 데이터와 동일한 뷰에서 무방향 BFS — 화면과 계산의 정합 보장.
"""

from __future__ import annotations

import os.path
import re
from collections import deque
from typing import Any

from neo4j import GraphDatabase

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

# 시각화에 노출할 노드 속성 (라벨별). 청크 본문 텍스트는 제외(용량 절감).
_NODE_FIELDS: dict[str, tuple[str, ...]] = {
    "Insurer": ("id", "name"),
    "Product": ("id", "name", "area"),
    "Version": ("id", "version_label", "is_active"),
    "Document": ("id", "doc_type", "page_count"),
    "Clause": ("chunk_id", "clause_no", "title", "insurer_id", "document_id"),
    "SubClause": ("chunk_id", "clause_no", "title", "insurer_id", "document_id"),
}


def _node_id(label: str, props: dict[str, Any]) -> str:
    key = (
        props.get("id")
        if label in ("Insurer", "Product", "Version", "Document")
        else props.get("chunk_id")
    )
    return f"{label.lower()}:{key}"


_CLAUSE_TITLE_RE = re.compile(r"^(제\s*\d+\s*조(?:의\s*\d+)?\s*(?:\([^)]{0,40}\))?)")


def _display_label(label: str, props: dict[str, Any]) -> str:
    if label in ("Insurer", "Product"):
        return str(props.get("name") or props.get("id") or "")
    if label == "Version":
        return str(props.get("version_label") or props.get("id") or "")
    if label == "Document":
        doc_ko = {"terms": "약관 전문", "summary": "상품요약서", "business": "사업방법서"}
        return doc_ko.get(str(props.get("doc_type")), str(props.get("doc_type") or "문서"))
    # Clause/SubClause — title 은 본문 첫 줄(최대 80자)이라 그대로 쓰면 화면이 텍스트로
    # 덮인다(실측). '제N조 (제목)' 패턴까지만 잘라 라벨로 쓰고, 없으면 clause_no/앞 28자.
    raw = str(props.get("title") or "")
    m = _CLAUSE_TITLE_RE.match(raw)
    if m:
        return m.group(1).strip()
    return str(props.get("clause_no") or raw[:28] or props.get("chunk_id") or "")


# ── SQLite 문서 구조 복원 ────────────────────────────────────────────────
# Memgraph HAS_SUBCLAUSE 는 다대다 중복(16k+)이라 계층으로 쓸 수 없고, SubClause 노드
# 속성도 문서마다 들쭉날쭉(제목 없음 → UUID 라벨)이다. 대신 SQLite 청크의 읽기 순서
# (rowid)와 구조 신호(article=새 조, 조 번호 하락=새 섹션, 첫 조 이전=도입부)만으로
# 트리·라벨·섹션 스코프를 복원한다 — 키워드 규칙 없음.


def _clause_num(clause_no: str | None) -> int | None:
    m = re.search(r"\d+", clause_no or "")
    return int(m.group()) if m else None


def _strip_heading(text: str) -> str:
    return _CLAUSE_TITLE_RE.sub("", text, count=1).strip()


def _sub_label(
    clause_no: str | None, sub_no: str | None, chunk_type: str, page_start: int | None
) -> str:
    """하위 청크 표시 라벨 — '제3조 ②' / '제9조 1. (계속 2)' / '[표] p.6'."""
    base, _, part = (sub_no or "").partition("#")
    if base.startswith("part-"):
        base, part = "", base
    part_no = part.removeprefix("part-")
    bits: list[str] = []
    if clause_no:
        bits.append(clause_no)
    if base:
        bits.append(base)
    if chunk_type == "table":
        bits.append(f"[표] p.{page_start}")
    elif chunk_type == "annex":
        # clause_no 가 이미 '별표 2' 형태면 태그 중복('별표 2 [별표]') 방지
        tag = "" if (clause_no and "별표" in clause_no) else "[별표] "
        bits.append(f"{tag}p.{page_start}")
    if part_no:
        bits.append(f"(계속 {part_no})")
    return " ".join(bits) or f"p.{page_start}"


def _dedupe_previews(items: list[dict[str, Any]]) -> None:
    """형제 미리보기의 공통 접두(부모 조 문두 보일러플레이트) 제거 — 변별력 확보."""
    pvs = [i["preview"] for i in items if i.get("preview")]
    if len(pvs) < 2:
        return
    common = os.path.commonprefix(pvs)
    if len(common) < 16:
        return
    for i in items:
        if i.get("preview"):
            i["preview"] = i["preview"][len(common):].lstrip() or i["preview"]


def _build_doc_sections(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """한 문서의 청크 행(읽기 순서)을 (도입부 항목들, 조 섹션들)로 복원 — 순수 함수.

    신호: article=새 조 · 같은 조 번호 연속 article=분할 계속 · 조 번호 하락=새 섹션
    (본문 뒤 특별약관들이 제1조부터 재시작) · 첫 article 이전=도입부(표지·안내).
    """
    intro: list[dict[str, Any]] = []
    sections: list[list[dict[str, Any]]] = []
    cur_art: dict[str, Any] | None = None
    last_num: int | None = None
    for r in rows:
        head = " ".join((r.get("head") or "").split())
        if r["chunk_type"] == "article":
            num = _clause_num(r.get("clause_no"))
            node_id = f"clause:{r['id']}"
            m = _CLAUSE_TITLE_RE.match(head)
            label = m.group(1).strip() if m else (r.get("clause_no") or head[:24] or node_id)
            if (
                sections
                and cur_art is not None
                and r.get("clause_no")
                and cur_art["clause_no"] == r["clause_no"]
            ):
                cur_art["subs"].append({
                    "id": node_id, "label": f"{label} (계속)", "node_type": "Clause",
                    "preview": _strip_heading(head)[:90],
                })
                continue
            # 새 섹션 = 제1조부터 재시작(특약 경계). 단순 번호 하락은 페이지 배치
            # 노이즈(보장종목 반복 등)가 많아 리셋 신호로 쓰지 않는다(실측: 28개 과분할).
            if not sections or (num == 1 and last_num is not None and last_num > 1):
                sections.append([])
            if num is not None:
                last_num = num
            cur_art = {
                "id": node_id, "label": label, "clause_no": r.get("clause_no"),
                "node_type": "Clause", "preview": _strip_heading(head)[:90], "subs": [],
            }
            sections[-1].append(cur_art)
        else:
            item = {
                "id": f"subclause:{r['id']}",
                "label": _sub_label(
                    r.get("clause_no"), r.get("sub_no"), r["chunk_type"], r.get("page_start")
                ),
                "node_type": "SubClause",
                "preview": _strip_heading(head)[:90],
            }
            (cur_art["subs"] if cur_art is not None else intro).append(item)
    def _strip_label_marker(items: list[dict[str, Any]]) -> None:
        """미리보기 선두가 라벨 끝 마커와 겹치면('제3조 ②' + '② …') 중복 제거."""
        for it in items:
            pv = it.get("preview") or ""
            tail = it["label"].split()[-1] if it.get("label") else ""
            if tail and pv.startswith(tail):
                it["preview"] = pv[len(tail):].lstrip() or pv

    for arts in sections:
        for a in arts:
            # 하위항 청크는 부모 조 본문 앞부분을 컨텍스트로 복제한다(인제스트) —
            # 부모 미리보기와의 공통 접두를 걷어내면 '( 1) 상해급여 ① …'처럼
            # 변별 구간부터 시작한다. 표(|) 미리보기는 접두가 달라 자연히 비대상.
            parent_pv = a.get("preview") or ""
            for sub in a["subs"]:
                pv = sub.get("preview") or ""
                common = os.path.commonprefix([parent_pv, pv])
                if len(common) >= 16:
                    sub["preview"] = pv[len(common):].lstrip() or pv
            _dedupe_previews(a["subs"])
            _strip_label_marker(a["subs"])
    _dedupe_previews(intro)
    _strip_label_marker(intro)
    return intro, sections


_STRUCT_TTL_S = 60.0
_struct_cache: dict[str, Any] = {"at": 0.0, "structure": None}


def _document_structure() -> dict[str, Any]:
    """SQLite 청크로 문서 계층 복원 (TTL 캐시) — 트리·라벨·섹션 스코프의 단일 소스.

    Returns:
        {"labels": {노드id: 라벨}, "info": {노드id: {label,node_type,preview}},
         "children": {노드id: [{id,label,node_type,preview}]},
         "section_members": {섹션id: [하위 노드id 전부]}}
    """
    import time

    if (
        _struct_cache["structure"] is not None
        and time.monotonic() - _struct_cache["at"] < _STRUCT_TTL_S
    ):
        return _struct_cache["structure"]

    from sqlalchemy import text as sqltext

    from app.infrastructure.core.database import session_scope
    from app.shared.insurers import code_to_name

    with session_scope() as s:
        # 읽기 순서 = 인제스트 삽입 순서. SQLite 는 rowid, PostgreSQL 은 rowid 가 없어
        # ctid(힙 물리 위치 — 청크는 append-only 라 삽입 순서와 일치)로 대체.
        # (rowid 하드코딩이 라이브 PG 에서 500 을 냈던 실사고)
        order_col = "rowid" if s.get_bind().dialect.name == "sqlite" else "ctid"
        rows = [dict(r) for r in s.execute(sqltext(
            "SELECT id, document_id, insurer_id, doc_type, chunk_type, clause_no, sub_no, "
            "page_start, substr(clause_chunks.text, 1, 200) AS head FROM clause_chunks "
            f"ORDER BY document_id, {order_col}"
        )).mappings()]

    labels: dict[str, str] = {}
    info: dict[str, dict[str, Any]] = {}
    children: dict[str, list[dict[str, Any]]] = {}
    section_members: dict[str, list[str]] = {}

    by_doc: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        by_doc.setdefault(r["document_id"], []).append(r)

    def register(entry: dict[str, Any]) -> dict[str, Any]:
        labels[entry["id"]] = entry["label"]
        info[entry["id"]] = {
            "label": entry["label"], "node_type": entry["node_type"],
            "preview": entry.get("preview"),
        }
        return {k: entry.get(k) for k in ("id", "label", "node_type", "preview")}

    def add_section(
        sec_id: str, sec_label: str, arts: list[dict[str, Any]],
        sec_refs: list[dict[str, Any]],
    ) -> None:
        info[sec_id] = {"label": sec_label, "node_type": "Section", "preview": None}
        children[sec_id] = [register(a) for a in arts]
        member_ids: list[str] = []
        for a in arts:
            member_ids.append(a["id"])
            subs = a.get("subs") or []
            children[a["id"]] = [register(sc) for sc in subs]
            member_ids.extend(sc["id"] for sc in subs)
        section_members[sec_id] = member_ids
        sec_refs.append({"id": sec_id, "label": sec_label, "node_type": "Section", "preview": None})

    doc_ko = {"terms": "약관 전문", "summary": "상품요약서", "business": "사업방법서"}
    ins_docs: dict[str, list[tuple[int, str]]] = {}
    for document_id, doc_rows in by_doc.items():
        intro, raw_sections = _build_doc_sections(doc_rows)
        doc_node = f"document:{document_id}"
        sec_refs: list[dict[str, Any]] = []

        if intro:
            add_section(
                f"section:{document_id}:0", f"도입부 · 표지/안내 {len(intro)}개", intro, sec_refs
            )
        # '본문' = 조 수가 가장 많은 섹션. 첫 섹션 고정이면 현대해상처럼 본문 앞에
        # 소책자 섹션(제1조~제5조)이 있는 문서에서 진짜 본문이 '부속'으로 밀린다(실측).
        main_idx = (
            max(range(len(raw_sections)), key=lambda i: len(raw_sections[i]))
            if raw_sections else -1
        )
        part_no = 0
        for si, arts in enumerate(raw_sections, start=1):
            nums = [n for n in (_clause_num(a["clause_no"]) for a in arts) if n is not None]
            rng = f"제{min(nums)}조~제{max(nums)}조" if nums else "조항"
            if si - 1 == main_idx:
                sec_label = f"본문 {rng}"
            else:
                part_no += 1
                sec_label = f"부속 {part_no} · {rng}"
            add_section(f"section:{document_id}:{si}", sec_label, arts, sec_refs)

        doc_label = doc_ko.get(str(doc_rows[0]["doc_type"]), str(doc_rows[0]["doc_type"] or "문서"))
        info[doc_node] = {"label": doc_label, "node_type": "Document", "preview": None}
        children[doc_node] = sec_refs
        ins_docs.setdefault(str(doc_rows[0]["insurer_id"] or ""), []).append(
            (document_id, doc_node)
        )

    for code, ds in sorted(ins_docs.items()):
        ins_node = f"insurer:{code}"
        info[ins_node] = {
            "label": code_to_name(code) or code, "node_type": "Insurer", "preview": None,
        }
        children[ins_node] = [
            {"id": dn, "label": info[dn]["label"], "node_type": "Document", "preview": None}
            for _, dn in sorted(ds)
        ]
    info["root"] = {
        "label": "전체 문서", "node_type": "Root",
        "preview": f"{len(ins_docs)}개 손보사 실손 약관 전체",
    }
    children["root"] = [
        {"id": f"insurer:{c}", "label": info[f"insurer:{c}"]["label"],
         "node_type": "Insurer", "preview": None}
        for c in sorted(ins_docs)
    ]

    structure = {
        "labels": labels, "info": info, "children": children,
        "section_members": section_members,
    }
    _struct_cache["structure"] = structure
    _struct_cache["at"] = time.monotonic()
    return structure


def _bfs_reachable(
    start: str,
    edges: list[dict[str, Any]],
    adjacency: dict[str, list[str]] | None = None,
) -> set[str]:
    """**하향(directed)** BFS 도달 집합 — 스코프 절단용.

    무방향이면 Document 루트에서 Version→Product→Insurer 로 올라간 뒤 형제 문서로
    다시 내려가 스코프가 전체로 번진다. 그래프 엣지가 전부 상위→하위(SELLS→…→CONTAINS
    →HAS_SUBCLAUSE, REFERS_TO 도 조항→별표)라 하향만 따라가면 '그 루트 아래' 서브그래프가
    정확히 잘리고, Insurer 루트의 결과는 무방향과 동일하다.

    adjacency 를 넘기면 재구축을 건너뛴다 — 섹션 스코프는 구성원마다 BFS 를 돌므로
    호출부(fetch_graph)가 캐시된 인접 리스트를 공유해야 한다(미공유 실측: 최대 150ms).
    """
    if adjacency is None:
        adjacency = {}
        for e in edges:
            adjacency.setdefault(e["source"], []).append(e["target"])
    visited = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in adjacency.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(nxt)
    return visited


# Cypher 에서 프리픽스 id 를 직접 계산 — 엣지 행이 문자열 3개로 줄어 Bolt 전송량이
# 양끝 전체 속성 dict 대비 수십 배 작다(실측: 전체 2.1s 의 지배 요인이 엣지 전송).
_CY_NODE_ID = "toLower(labels({v})[0]) + ':' + toString(coalesce({v}.id, {v}.chunk_id))"

# 그래프는 인제스트 때만 변한다 → 짧은 TTL 캐시로 스코프 전환·경로 탐색을 즉시화.
_CACHE_TTL_S = 60.0
_cache: dict[str, Any] = {"at": 0.0, "graph": None}


def _fetch_full_graph() -> dict[str, Any]:
    """Memgraph 전체를 1회 조회 (TTL 캐시). 스코프 절단은 호출부에서 파이썬으로."""
    import time

    if _cache["graph"] is not None and time.monotonic() - _cache["at"] < _CACHE_TTL_S:
        return _cache["graph"]

    settings = get_settings()
    try:
        driver = GraphDatabase.driver(
            settings.graph_uri, auth=(settings.graph_username, settings.graph_password)
        )
        with driver.session() as neo:
            node_rows = neo.run(
                "MATCH (n) RETURN labels(n)[0] AS label, properties(n) AS props"
            ).data()
            edge_rows = neo.run(
                f"MATCH (a)-[r]->(b) RETURN {_CY_NODE_ID.format(v='a')} AS sid, "
                f"type(r) AS rel, {_CY_NODE_ID.format(v='b')} AS tid"
            ).data()
        driver.close()
    except Exception as exc:  # noqa: BLE001 — 드라이버 예외 다양 → 단일 실패 신호로
        raise RuntimeError(f"그래프 스토어 연결 실패: {exc}") from exc

    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in node_rows:
        label, props = row["label"], row["props"] or {}
        if label not in _NODE_FIELDS:
            continue
        nid = _node_id(label, props)
        if nid in seen:
            continue
        seen.add(nid)
        # 주의: 원시 속성 스프레드를 먼저 두고 id/node_type/label 을 뒤에 — Insurer 등의
        # 원시 "id"('samsung')가 프리픽스 id('insurer:samsung')를 덮지 않게(실측 버그).
        nodes.append({
            **{k: props.get(k) for k in _NODE_FIELDS[label] if k in props},
            "id": nid,
            "node_type": label,
            "label": _display_label(label, props),
        })

    edges: list[dict[str, Any]] = []
    for i, row in enumerate(edge_rows):
        if row["sid"] not in seen or row["tid"] not in seen:
            continue
        edges.append({
            "edge_id": f"e{i}",
            "source": row["sid"],
            "target": row["tid"],
            "relation_type": row["rel"],
        })

    # 구조 복원 기반 보정 2종 — 실패해도 그래프 자체는 서빙(원시 데이터 유지, 로깅).
    try:
        struct = _document_structure()
        # (1) Clause/SubClause 라벨 보강 — SubClause 는 그래프 속성이 문서마다 비어
        #     UUID/조번호만 남는다(사용자 실측: '제10조'만 표시·검색 불가).
        struct_labels = struct["labels"]
        for n in nodes:
            if n["node_type"] in ("Clause", "SubClause"):
                enriched = struct_labels.get(n["id"])
                if enriched:
                    n["label"] = enriched
        # (2) HAS_SUBCLAUSE 를 진짜 소속(조→항)으로 교체 — 인제스트가 조 번호 매칭으로
        #     만든 다대다(15.7k)라 '제4조 (준용규정)'에 남의 문서 제4조 항 18개가 붙는
        #     오류(사용자 실측). 항은 CONTAINS(문서→항)로도 연결되어 고아는 안 생긴다.
        true_pairs = sorted(
            (parent_id, c["id"])
            for parent_id, childs in struct["children"].items()
            if parent_id.startswith("clause:")
            for c in childs
        )
        edges = [e for e in edges if e["relation_type"] != "HAS_SUBCLAUSE"]
        for i, (src, dst) in enumerate(true_pairs):
            if src in seen and dst in seen:
                edges.append({
                    "edge_id": f"s{i}",
                    "source": src,
                    "target": dst,
                    "relation_type": "HAS_SUBCLAUSE",
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("admin: 구조 기반 라벨/엣지 보정 실패(원시 그래프 사용): %s", exc)

    graph = {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}
    # 하향 인접 리스트를 함께 캐시 — BFS 호출마다 21k 엣지 재구축 방지.
    # 응답 dict 는 호출부가 새로 조립하므로 이 내부 키는 직렬화되지 않는다.
    adjacency: dict[str, list[str]] = {}
    for e in edges:
        adjacency.setdefault(e["source"], []).append(e["target"])
    graph["_adjacency"] = adjacency
    _cache["graph"] = graph
    _cache["at"] = time.monotonic()
    return graph


def fetch_graph(insurer_id: str | None = None, scope: str | None = None) -> dict[str, Any]:
    """Memgraph 전체(또는 스코프 서브그래프)를 node-link JSON 으로 반환.

    Args:
        insurer_id: 보험사 스코프 축약형 (예: "samsung" → 루트 insurer:samsung)
        scope: 임의 루트 노드 id (예: "document:9") — 지정 시 insurer_id 보다 우선

    Raises:
        RuntimeError: 그래프 스토어 연결 실패 (호출자가 503 으로 변환).
    """
    full = _fetch_full_graph()
    nodes, edges = full["nodes"], full["edges"]

    # 스코프 — 루트 노드에서 하향 도달 가능한 서브그래프만 (구조 기반, 문자열 매칭 없음)
    root = scope or (f"insurer:{insurer_id}" if insurer_id else None)
    if root == "root":  # 트리 가상 루트 = 전체 (절단 없음)
        root = None
    if root:
        seen = {n["id"] for n in nodes}
        adjacency = full.get("_adjacency")
        if root.startswith("section:"):
            # 섹션은 그래프에 없는 합성 노드 — 구조 복원의 구성원들에서 하향 합집합
            try:
                members = _document_structure()["section_members"].get(root, [])
            except Exception as exc:  # noqa: BLE001
                logger.warning("admin: 섹션 스코프 구성원 조회 실패: %s", exc)
                members = []
            reachable: set[str] = set()
            for m in members:
                if m in seen:
                    reachable |= _bfs_reachable(m, edges, adjacency)
        else:
            reachable = _bfs_reachable(root, edges, adjacency) if root in seen else set()
        nodes = [n for n in nodes if n["id"] in reachable]
        kept = {n["id"] for n in nodes}
        edges = [e for e in edges if e["source"] in kept and e["target"] in kept]

    logger.info(
        "admin.fetch_graph: nodes=%d edges=%d (root=%s)", len(nodes), len(edges), root
    )
    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


def list_scopes() -> list[dict[str, Any]]:
    """좌측 스코프 트리용 — 보험사별 문서 목록 (캐시된 전체 그래프에서 구성)."""
    full = _fetch_full_graph()
    by_id = {n["id"]: n for n in full["nodes"]}
    children: dict[str, list[str]] = {}
    for e in full["edges"]:
        children.setdefault(e["source"], []).append(e["target"])

    def descend(nid: str, want: str) -> list[dict[str, Any]]:
        """nid 하위에서 node_type==want 노드들 (하향 BFS)."""
        out, seen, queue = [], {nid}, deque([nid])
        while queue:
            cur = queue.popleft()
            for nxt in children.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                node = by_id.get(nxt)
                if node and node["node_type"] == want:
                    out.append(node)
                else:
                    queue.append(nxt)
        return out

    def clause_sort_key(label: str) -> tuple[int, str]:
        """'제N조 …' 를 조 번호 순으로 정렬 (번호 없으면 뒤로)."""
        m = re.match(r"제\s*(\d+)\s*조", label or "")
        return (int(m.group(1)) if m else 10_000, label or "")

    scopes = []
    insurers = sorted(
        (n for n in full["nodes"] if n["node_type"] == "Insurer"), key=lambda n: n["id"]
    )
    for ins in insurers:
        docs = []
        for d in descend(ins["id"], "Document"):
            # 문서 직속 Clause 목록 — 사이드바 3단계(조항 스코프 진입점).
            # 같은 clause_no 청크가 여러 개(항 단위 분할)라 라벨 기준 dedupe 후 조번호 정렬.
            clause_children = [
                by_id[c]
                for c in children.get(d["id"], [])
                if by_id.get(c, {}).get("node_type") == "Clause"
            ]
            seen_labels: set[str] = set()
            clauses = []
            for c in sorted(clause_children, key=lambda x: clause_sort_key(x["label"])):
                if c["label"] in seen_labels:
                    continue
                seen_labels.add(c["label"])
                sub_count = len(children.get(c["id"], []))
                clauses.append({
                    "node_id": c["id"],
                    "label": c["label"],
                    "child_count": sub_count,
                })
            docs.append({
                "node_id": d["id"],
                "label": d["label"],
                "doc_type": d.get("doc_type"),
                "clause_count": len(clause_children),
                "clauses": clauses,
            })
        scopes.append({
            "insurer_id": ins["id"].removeprefix("insurer:"),
            "node_id": ins["id"],
            "label": ins["label"],
            "documents": sorted(docs, key=lambda x: x["node_id"]),
        })
    return scopes


def shortest_path(graph: dict[str, Any], source: str, target: str) -> dict[str, Any] | None:
    """서빙 뷰와 동일한 데이터에서 무방향 BFS 최단 경로. 없으면 None."""
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for e in graph["edges"]:
        adjacency.setdefault(e["source"], []).append((e["target"], e["edge_id"]))
        adjacency.setdefault(e["target"], []).append((e["source"], e["edge_id"]))
    if source not in adjacency or target not in adjacency:
        return None

    prev: dict[str, tuple[str, str]] = {}  # node -> (이전 노드, 사용 엣지)
    visited = {source}
    queue = deque([source])
    while queue:
        cur = queue.popleft()
        if cur == target:
            break
        for nxt, eid in adjacency.get(cur, []):
            if nxt not in visited:
                visited.add(nxt)
                prev[nxt] = (cur, eid)
                queue.append(nxt)
    if target not in visited:
        return None

    node_path: list[str] = [target]
    edge_path: list[str] = []
    cur = target
    while cur != source:
        parent, eid = prev[cur]
        edge_path.append(eid)
        node_path.append(parent)
        cur = parent
    node_path.reverse()
    edge_path.reverse()
    return {"nodes": node_path, "edges": edge_path, "hop_count": len(edge_path)}


class MemgraphGraphSource:
    """GraphSourcePort 의 Memgraph 어댑터 — 본 모듈 함수들을 포트 계약으로 노출.

    연구팀 TDD 트리 JSON 어댑터가 붙을 때 이 클래스와 같은 모양(ports.GraphSourcePort)만
    구현하면 라우터·UI 무변경 교체(사용자 결정: 헥사고날 seam 선적용).
    """

    def fetch_graph(
        self, insurer_id: str | None = None, scope: str | None = None
    ) -> dict[str, Any]:
        return fetch_graph(insurer_id=insurer_id, scope=scope)

    def list_scopes(self) -> list[dict[str, Any]]:
        return list_scopes()

    def shortest_path(
        self, graph: dict[str, Any], source: str, target: str
    ) -> dict[str, Any] | None:
        return shortest_path(graph, source, target)

    def document_tree(self) -> dict[str, Any]:
        return document_tree()

    def node_content(self, node_id: str) -> dict[str, Any] | None:
        return node_content(node_id)


def get_graph_source() -> MemgraphGraphSource:
    """포트 팩토리 — 어댑터 선택 지점 (현재 Memgraph 고정, 교체 시 여기서 분기)."""
    return MemgraphGraphSource()


def document_tree() -> dict[str, Any]:
    """TDD 트리 패널용 — 루트→보험사→문서→섹션→조→항/표 6단 트리(nodes+edges).

    참고 앱(TDD Graph Explorer) 데이터 계약 이식: {virtual_root, nodes:[{id,label,
    node_type,order,child_count,preview}], edges:[{source,target}]}.
    구조는 SQLite 읽기순서 복원(_document_structure) — 이전의 Memgraph 기반은 문서 아래
    조항 132개가 평탄하게 붙었다(사용자 피드백: depth 세분화).
    """
    structure = _document_structure()
    info, children = structure["info"], structure["children"]
    tree_nodes: list[dict[str, Any]] = []
    tree_edges: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(nid: str, parent: str | None, order: int) -> None:
        if nid in seen:  # 안전 가드 — 구조는 트리지만 만약의 중복 참조 차단
            return
        seen.add(nid)
        meta = info[nid]
        kids = children.get(nid, [])
        tree_nodes.append({
            "id": nid, "label": meta["label"], "node_type": meta["node_type"],
            "order": order, "child_count": len(kids), "preview": meta.get("preview"),
        })
        if parent is not None:
            tree_edges.append({"source": parent, "target": nid})
        for i, k in enumerate(kids):
            walk(k["id"], nid, i)

    walk("root", None, 0)
    return {"virtual_root": "root", "nodes": tree_nodes, "edges": tree_edges}


def node_content(node_id: str) -> dict[str, Any] | None:
    """Inspector 상세용 — 노드 본문(조항 텍스트는 SQLite)과 하위 목록.

    라벨·하위 목록은 구조 복원(_document_structure)이 1차 소스(섹션·루트 같은 합성
    노드 포함). 구조에 없는 노드(Product/Version 등)는 그래프로 폴백한다.
    """
    structure: dict[str, Any] | None = None
    try:
        structure = _document_structure()
    except Exception as exc:  # noqa: BLE001 — 구조 미가용이어도 그래프 폴백으로 서빙
        logger.warning("admin: 문서 구조 복원 실패 — 그래프 폴백: %s", exc)

    if structure is not None and node_id in structure["info"]:
        meta_info = structure["info"][node_id]
        node_type, label = meta_info["node_type"], meta_info["label"]
        children = structure["children"].get(node_id, [])
    else:
        full = _fetch_full_graph()
        by_id = {n["id"]: n for n in full["nodes"]}
        node = by_id.get(node_id)
        if node is None:
            return None
        node_type, label = node["node_type"], node["label"]
        children = [
            {"id": c, "label": by_id[c]["label"], "node_type": by_id[c]["node_type"],
             "preview": None}
            for c in (e["target"] for e in full["edges"] if e["source"] == node_id)
            if c in by_id
        ][:80]

    text: str | None = None
    meta: dict[str, Any] = {}
    if node_id.startswith(("clause:", "subclause:")):
        from app.domains.chunks.models import ClauseChunk
        from app.infrastructure.core.database import session_scope

        chunk_id = node_id.split(":", 1)[1]
        with session_scope() as s:
            row = s.query(ClauseChunk).filter(ClauseChunk.id == chunk_id).first()
            if row is not None:
                text = row.text
                meta = {
                    "clause_no": row.clause_no,
                    "page": f"p.{row.page_start}" + (f"~{row.page_end}" if row.page_end and row.page_end != row.page_start else ""),
                    "token_count": row.token_count,
                }
    return {
        "id": node_id,
        "node_type": node_type,
        "label": label,
        "meta": meta,
        "text": text,
        "children": children,
    }
