"""app.domains.chunks.structure

파일 경로: app/chunks/structure.py
목적: RawDocument 의 페이지 텍스트를 보험약관 구조(제N조 / 항 / 호 / 별표)로
      인식하여 StructureNode 트리를 만든다. 청킹(Task 3)이 이 트리를 입력으로 받는다.

주요 기능:
    - `recognize_structure(raw)` 진입점
    - 라인 단위 정규식 매칭으로 article / paragraph / item / annex 경계 식별
    - 경계 사이 본문을 부모 노드에 누적
    - 표(RawTable)는 발견 페이지의 article/annex 하위 TABLE 노드로 부착

설계 메모:
    - "제N조 (제목)" 패턴이 article. 항은 ①②③ 또는 "1." 또는 "(1)" 형식
    - 본문 라인이 어디에도 속하지 않으면 가장 최근 article/paragraph 에 attach
    - 단서/예외 절("단, ...")은 별도 노드로 끊지 않고 같은 항에 머문다
      → Task 3 청킹에서 같은 청크로 결합 정책 유지
"""

from __future__ import annotations

import re
import uuid

from app.domains.chunks.schemas import (
    ChunkType,
    RawDocument,
    RawTable,
    StructuredDocument,
    StructureNode,
)
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

# "제 15 조 (보험금 지급)" / "제15조" / "제15조의2" 형식 지원
# 그룹1은 "15" 또는 "15의2" 형태로 잡힌다. 본문 표기는 "조의N" 이지만 라인 구성은
# "제 N(의 M) 조 (제목)" 이므로 "(?:의\s*\d+)?" 가 "조" 앞에 위치한다.
_ARTICLE_RE = re.compile(r"^\s*제\s*(\d+(?:\s*의\s*\d+)?)\s*조\b\s*(\([^)]*\))?\s*")

# 항(paragraph): ①②③ 만 — 보험약관 표준 표기
# "(1)" 형식은 호로 쓰이는 경우가 압도적이므로 item 에 양보 (실제 데이터 분석으로 확정)
_PARAGRAPH_RE = re.compile(r"^\s*([①-⑳])\s+")

# 호/목(item): "1." "2." "1)" "(1)" / "가." "나." "(가)" — paragraph 보다 한 단계 안쪽
# 한글은 호 표기에 실제 쓰이는 14자(가~하)만 화이트리스트로 좁혀 false positive 차단
_ITEM_RE = re.compile(r"^\s*(\d+[.)]|\(\d+\)|[가-하]\.|\([가-하]\))\s+")

# 별표 시작 헤더: "[별표 1] 보장한도표" 또는 페이지 단독 "별표 1 ..."
# 단, 본문 중간의 "<별표1>"·"<별표 2>" 같은 참조는 시작 헤더가 아님 → ^에서 시작하고 < 로 시작 X
_ANNEX_RE = re.compile(r"^\s*\[?\s*별표\s*(\d+)\s*\]?\s+(?!\d)([^\n<]{1,80})$")

# 목차 라인 판정용:
#   - 한 줄에 "제N조" 가 2회 이상 등장 (예: "제40조 (..) 제41조(..) ..")
#   - 또는 라인이 점선/공백 + 페이지 번호로 끝남 (예: "............... 22")
_TOC_MULTIPLE_ARTICLES_RE = re.compile(r"제\s*\d+\s*조.+제\s*\d+\s*조")
_TOC_PAGE_NUMBER_TAIL_RE = re.compile(r"[\.…·∙·•‧⋯\s]{3,}\d+\s*$")


def _is_toc_line(line: str) -> bool:
    """목차스러운 라인은 article/paragraph 매칭에서 제외한다.

    보험약관 PDF는 본문 앞에 목차 페이지가 있어서 그대로 두면 거짓 article 이
    다수 생성된다. 목차의 두 가지 전형을 휴리스틱으로 걸러낸다.

    Args:
        line: 한 라인의 stripped 텍스트.
    Returns:
        목차 라인이면 True, 아니면 False.
    """
    if _TOC_MULTIPLE_ARTICLES_RE.search(line):
        return True
    return bool(_TOC_PAGE_NUMBER_TAIL_RE.search(line))


def recognize_structure(raw: RawDocument) -> StructuredDocument:
    """RawDocument 를 StructureNode 트리로 변환한다.

    Args:
        raw: parser.parse_pdf 결과.

    Returns:
        StructuredDocument: 평탄화된 노드 리스트 + 최상위 노드 ID.
    """
    nodes: list[StructureNode] = []
    nodes_by_id: dict[str, StructureNode] = {}  # 부모 lookup O(1) — 코퍼스 확장 대비
    root_ids: list[str] = []

    current_article: StructureNode | None = None
    current_paragraph: StructureNode | None = None

    def _new_node(
        chunk_type: ChunkType,
        clause_no: str | None,
        sub_no: str | None,
        text: str,
        page_start: int,
        page_end: int,
        parent_id: str | None,
        raw_table: RawTable | None = None,
    ) -> StructureNode:
        node = StructureNode(
            id=str(uuid.uuid4()),
            chunk_type=chunk_type,
            clause_no=clause_no,
            sub_no=sub_no,
            page_start=page_start,
            page_end=page_end,
            text=text.strip(),
            parent_id=parent_id,
            raw_table=raw_table,
        )
        nodes.append(node)
        nodes_by_id[node.id] = node
        if parent_id is None:
            root_ids.append(node.id)
        else:
            nodes_by_id[parent_id].children_ids.append(node.id)
        return node

    for page in raw.pages:
        for line in page.text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            # 목차 라인은 article/paragraph/item 매칭에서 제외 (거짓 노드 생성 방지)
            if _is_toc_line(stripped):
                continue

            annex_match = _ANNEX_RE.match(stripped)
            article_match = _ARTICLE_RE.match(stripped)
            paragraph_match = _PARAGRAPH_RE.match(stripped)
            item_match = _ITEM_RE.match(stripped)

            if annex_match:
                annex_no = f"별표 {annex_match.group(1)}"
                title = annex_match.group(2).strip()
                current_article = _new_node(
                    chunk_type=ChunkType.ANNEX,
                    clause_no=annex_no,
                    sub_no=None,
                    text=f"{annex_no} {title}".strip(),
                    page_start=page.page,
                    page_end=page.page,
                    parent_id=None,
                )
                current_paragraph = None
                continue

            if article_match:
                clause_no = f"제{article_match.group(1)}조"
                title = (article_match.group(2) or "").strip()
                current_article = _new_node(
                    chunk_type=ChunkType.ARTICLE,
                    clause_no=clause_no,
                    sub_no=None,
                    text=f"{clause_no} {title}".strip(),
                    page_start=page.page,
                    page_end=page.page,
                    parent_id=None,
                )
                current_paragraph = None
                continue

            if paragraph_match and current_article is not None:
                sub_no = paragraph_match.group(1)
                body = stripped[paragraph_match.end() :].strip()
                current_paragraph = _new_node(
                    chunk_type=ChunkType.PARAGRAPH,
                    clause_no=current_article.clause_no,
                    sub_no=sub_no,
                    text=body,
                    page_start=page.page,
                    page_end=page.page,
                    parent_id=current_article.id,
                )
                continue

            if item_match and (current_paragraph or current_article) is not None:
                sub_no = item_match.group(1)
                body = stripped[item_match.end() :].strip()
                parent = current_paragraph or current_article
                # parent 는 위 조건으로 None 이 아님이 보장됨
                assert parent is not None
                _new_node(
                    chunk_type=ChunkType.ITEM,
                    clause_no=parent.clause_no,
                    sub_no=sub_no,
                    text=body,
                    page_start=page.page,
                    page_end=page.page,
                    parent_id=parent.id,
                )
                continue

            # 매칭되지 않은 본문 라인 → 가장 가까운 paragraph/article 에 누적
            target = current_paragraph or current_article
            if target is not None:
                target.text = (target.text + " " + stripped).strip()
                target.page_end = page.page

        # 페이지 내 표를 article/annex 의 하위 TABLE 노드로 부착
        for table in page.tables:
            anchor = current_article  # annex 도 article 슬롯에 들어 있다
            _new_node(
                chunk_type=ChunkType.TABLE,
                clause_no=anchor.clause_no if anchor else None,
                sub_no=None,
                text=table.caption or "",
                page_start=table.page,
                page_end=table.page,
                parent_id=anchor.id if anchor else None,
                raw_table=table,
            )

    logger.info(
        "구조 인식 완료: %s (노드 %d, 최상위 %d)",
        raw.file_path,
        len(nodes),
        len(root_ids),
    )

    return StructuredDocument(
        file_path=raw.file_path,
        parser_version=raw.parser_version,
        nodes=nodes,
        root_ids=root_ids,
    )
