"""app.domains.chunks.chunker

파일 경로: app/chunks/chunker.py
목적: StructuredDocument 트리를 의미 단위 Chunk 리스트로 변환한다. 단순 토큰 슬라이딩이
      아니라 article/annex/table 경계를 우선 보존하고, 토큰 한도 초과 시 paragraph 단위로
      분할하면서 부모 article 컨텍스트를 prefix 로 유지한다.

주요 기능:
    - `chunk_document(struct, max_tokens)` 진입점
    - article 청크: 본문 + 모든 자식 paragraph/item 합본 (한도 내일 때)
    - 한도 초과 시 paragraph 단위 분할 — 각 청크는 "[제N조 제목] ① 항 본문 + 자식 호" 형태
    - 단서/예외 절은 같은 paragraph 청크에 머문다 (구조 인식이 이미 누적해둠)
    - 표(table) 청크: 캡션 + 행렬을 markdown 형식으로 직렬화
    - 별표(annex) 청크: article과 동일 정책

설계 메모:
    - 토큰 카운팅은 tiktoken `cl100k_base`(OpenAI 임베딩 호환). 모델별 보정은 향후.
    - PoC 기본 max_tokens=1000 — text-embedding-3-small 정확도/문맥 균형점.
    - Chunk 모델은 schemas.py 에 pydantic 으로 정의 (도메인 응집).
"""

from __future__ import annotations

import uuid

import tiktoken

from app.domains.chunks.schemas import (
    Chunk,
    ChunkType,
    RawTable,
    StructuredDocument,
    StructureNode,
)
from app.infrastructure.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_TOKENS = 1000
MIN_CHUNK_TOKENS = 30  # 너무 짧은 단편(예: 빈 article 헤더)은 검색 노이즈가 되어 제외
HARD_TOKEN_LIMIT = 7000  # OpenAI 임베딩 한도(8191) 아래로 안전 마진 — 강제 분할 임계
SPLIT_OVERLAP_TOKENS = 80  # 강제 분할 시 문맥 유지를 위한 오버랩
_ENCODING_NAME = "cl100k_base"


def chunk_document(
    struct: StructuredDocument,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[Chunk]:
    """StructuredDocument 를 의미 단위 Chunk 리스트로 변환한다.

    Args:
        struct: structure.recognize_structure 결과.
        max_tokens: 1청크 최대 토큰 수. 초과 시 paragraph 단위 분할.

    Returns:
        Chunk 리스트. 검색/임베딩에 그대로 투입 가능.
    """
    encoder = tiktoken.get_encoding(_ENCODING_NAME)
    chunks: list[Chunk] = []

    for root_id in struct.root_ids:
        root = struct.by_id(root_id)
        if root.chunk_type == ChunkType.ARTICLE or root.chunk_type == ChunkType.ANNEX:
            chunks.extend(_chunk_article(struct, root, encoder, max_tokens))
        elif root.chunk_type == ChunkType.TABLE:
            chunks.append(_chunk_table(root, encoder))
        # 그 외 OTHER 등은 무시

    # 후처리 1: 강제 분할 — 임베딩 API 한도 초과 청크 차단 (Sprint 1 PoC 안전 장치)
    chunks = _enforce_hard_limit(chunks, encoder)

    # 후처리 2: 너무 짧은 청크 필터링
    filtered = [c for c in chunks if c.token_count >= MIN_CHUNK_TOKENS]
    dropped = len(chunks) - len(filtered)
    logger.info(
        "청킹 완료: %s (총 %d, 채택 %d, 최소토큰 미만 폐기 %d)",
        struct.file_path,
        len(chunks),
        len(filtered),
        dropped,
    )
    return filtered


def _enforce_hard_limit(chunks: list[Chunk], encoder: tiktoken.Encoding) -> list[Chunk]:
    """HARD_TOKEN_LIMIT 를 넘는 청크를 토큰 수 기준으로 강제 분할한다.

    구조 기반 분할(article/paragraph 단위) 후에도 한도를 넘는 케이스(예: 별표가
    본문에 통째로 누적된 경우)를 막기 위한 마지막 안전 장치다. 의미 경계를 잃지만
    임베딩 API 호출 자체가 실패하는 것보다 낫다.
    """
    result: list[Chunk] = []
    for chunk in chunks:
        if chunk.token_count <= HARD_TOKEN_LIMIT:
            result.append(chunk)
            continue
        result.extend(_split_by_tokens(chunk, encoder))
    return result


def _split_by_tokens(chunk: Chunk, encoder: tiktoken.Encoding) -> list[Chunk]:
    """1개 청크를 HARD_TOKEN_LIMIT 단위(오버랩 포함)로 잘라 여러 청크로 만든다."""
    token_ids = encoder.encode(chunk.text)
    pieces: list[Chunk] = []
    step = HARD_TOKEN_LIMIT - SPLIT_OVERLAP_TOKENS
    start = 0
    part_no = 1
    while start < len(token_ids):
        end = min(start + HARD_TOKEN_LIMIT, len(token_ids))
        piece_text = encoder.decode(token_ids[start:end])
        sub_no = f"{chunk.sub_no or ''}#part-{part_no}".lstrip("#")
        pieces.append(
            Chunk(
                id=str(uuid.uuid4()),
                chunk_type=chunk.chunk_type,
                clause_no=chunk.clause_no,
                sub_no=sub_no,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                token_count=end - start,
                text=piece_text,
                parent_chunk_id=chunk.parent_chunk_id,
            )
        )
        if end == len(token_ids):
            break
        start += step
        part_no += 1
    logger.warning(
        "강제 분할: %s %s (%dt → %d개 조각)",
        chunk.chunk_type.value, chunk.clause_no, chunk.token_count, len(pieces),
    )
    return pieces


def _chunk_article(
    struct: StructuredDocument,
    article: StructureNode,
    encoder: tiktoken.Encoding,
    max_tokens: int,
) -> list[Chunk]:
    """1개 article(또는 annex)을 청크로 변환한다. 한도 내면 통합, 초과 시 paragraph 분할."""
    combined_text = _flatten_article_text(struct, article)
    combined_tokens = len(encoder.encode(combined_text))

    if combined_tokens <= max_tokens:
        # 통합 청크 1개
        return [
            Chunk(
                id=str(uuid.uuid4()),
                chunk_type=article.chunk_type,
                clause_no=article.clause_no,
                sub_no=None,
                page_start=article.page_start,
                page_end=_compute_page_end(struct, article),
                token_count=combined_tokens,
                text=combined_text,
            )
        ]

    # 한도 초과 → paragraph 단위 분할, 각 청크에 부모 article 헤더 prefix
    article_header = _article_header(article)
    chunks: list[Chunk] = []

    # article 본문(누적 텍스트) 자체를 한 청크로 생성.
    # 본문 자체가 max_tokens를 넘는 케이스(예: 별표가 본문에 누적된 경우)는 후처리
    # `_enforce_hard_limit`가 HARD_TOKEN_LIMIT 기준 강제 분할로 받아낸다.
    if article.text:
        head_text = article.text
        chunks.append(
            Chunk(
                id=str(uuid.uuid4()),
                chunk_type=article.chunk_type,
                clause_no=article.clause_no,
                sub_no=None,
                page_start=article.page_start,
                page_end=article.page_end,
                token_count=len(encoder.encode(head_text)),
                text=head_text,
            )
        )

    for child_id in article.children_ids:
        child = struct.by_id(child_id)
        if child.chunk_type == ChunkType.TABLE:
            chunks.append(_chunk_table(child, encoder))
            continue
        if child.chunk_type != ChunkType.PARAGRAPH:
            continue
        paragraph_text = _flatten_paragraph_text(struct, child)
        text_with_header = f"{article_header}\n{paragraph_text}".strip()
        chunks.append(
            Chunk(
                id=str(uuid.uuid4()),
                chunk_type=ChunkType.PARAGRAPH,
                clause_no=child.clause_no,
                sub_no=child.sub_no,
                page_start=child.page_start,
                page_end=child.page_end,
                token_count=len(encoder.encode(text_with_header)),
                text=text_with_header,
            )
        )

    return chunks


def _flatten_article_text(struct: StructuredDocument, article: StructureNode) -> str:
    """article 본문 + 모든 paragraph/item 자손 텍스트를 합쳐 1개 문자열로."""
    header = _article_header(article)
    parts: list[str] = [header] if header else []

    # article.text 의 첫 줄(=헤더)을 제거한 나머지를 본문으로 사용. removeprefix 보다 안전.
    first_newline = article.text.find("\n")
    body = article.text[first_newline + 1:].strip() if first_newline >= 0 else ""
    if body:
        parts.append(body)

    for child_id in article.children_ids:
        child = struct.by_id(child_id)
        if child.chunk_type == ChunkType.PARAGRAPH:
            parts.append(_flatten_paragraph_text(struct, child))
        elif child.chunk_type == ChunkType.ITEM:
            parts.append(_render_item(child))
        # table 은 별도 청크로 분리되므로 합치지 않음
    return "\n".join(p for p in parts if p)


def _flatten_paragraph_text(struct: StructuredDocument, paragraph: StructureNode) -> str:
    """paragraph 본문 + 자식 item 텍스트를 합친다."""
    parts: list[str] = []
    if paragraph.sub_no:
        parts.append(f"{paragraph.sub_no} {paragraph.text}".strip())
    else:
        parts.append(paragraph.text)
    for child_id in paragraph.children_ids:
        child = struct.by_id(child_id)
        if child.chunk_type == ChunkType.ITEM:
            parts.append(_render_item(child))
    return "\n".join(parts)


def _render_item(item: StructureNode) -> str:
    """호/목 1개를 'sub_no 본문' 형태로 직렬화."""
    if item.sub_no:
        return f"  {item.sub_no} {item.text}".strip()
    return item.text


def _article_header(article: StructureNode) -> str:
    """article 청크의 prefix 로 쓰는 헤더 (예: '제15조 (보험금 지급)').

    article.text 의 첫 줄을 그대로 사용한다. 약관 조항명은 대부분 한 줄짜리이며
    임의로 자르면 의미 손실(괄호·단서 끊김)이 크다. 줄 단위 prefix 라 토큰 비용도 미미.
    """
    if not article.clause_no:
        return ""
    first_line = article.text.split("\n", 1)[0].strip()
    if first_line.startswith(article.clause_no):
        return first_line
    return article.clause_no


def _compute_page_end(struct: StructuredDocument, article: StructureNode) -> int:
    """article + 모든 자손의 page_end 최댓값."""
    max_page = article.page_end
    for child_id in article.children_ids:
        child = struct.by_id(child_id)
        if child.page_end > max_page:
            max_page = child.page_end
    return max_page


def _chunk_table(node: StructureNode, encoder: tiktoken.Encoding) -> Chunk:
    """표 노드를 1개 청크로 직렬화 (markdown 형식)."""
    table = node.raw_table
    text = _render_table_markdown(table, fallback_caption=node.text)
    return Chunk(
        id=str(uuid.uuid4()),
        chunk_type=ChunkType.TABLE,
        clause_no=node.clause_no,
        sub_no=None,
        page_start=node.page_start,
        page_end=node.page_end,
        token_count=len(encoder.encode(text)),
        text=text,
    )


def _render_table_markdown(table: RawTable | None, fallback_caption: str) -> str:
    """표를 markdown 형태로 직렬화. 표가 None 이면 캡션만."""
    if table is None or not table.rows:
        return fallback_caption or "(빈 표)"
    caption = table.caption or fallback_caption or ""
    lines: list[str] = []
    if caption:
        lines.append(f"[표] {caption}")
    # markdown 헤더/구분/본문
    header = table.rows[0]
    body = table.rows[1:]
    lines.append("| " + " | ".join(_cell(c) for c in header) + " |")
    lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in body:
        # 행 길이가 헤더와 다르면 패딩
        padded = (row + [""] * len(header))[: len(header)]
        lines.append("| " + " | ".join(_cell(c) for c in padded) + " |")
    return "\n".join(lines)


def _cell(value: str) -> str:
    """markdown 표 셀 이스케이프 (파이프와 줄바꿈 제거)."""
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()
