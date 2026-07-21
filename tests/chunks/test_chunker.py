"""tests.chunks.test_chunker

app/chunks/chunker.py 단위 테스트.

테스트 대상:
    - chunk_document: 토큰 한도 내/초과/별표 누적 시나리오
    - _enforce_hard_limit: HARD_TOKEN_LIMIT 초과 청크 강제 분할
    - _split_by_tokens: 오버랩 포함 분할, 조각 수 검증
"""

from __future__ import annotations

import uuid

import tiktoken
from app.domains.chunks.chunker import (
    DEFAULT_MAX_TOKENS,
    HARD_TOKEN_LIMIT,
    MIN_CHUNK_TOKENS,
    SPLIT_OVERLAP_TOKENS,
    _enforce_hard_limit,
    _split_by_tokens,
    chunk_document,
)
from app.domains.chunks.schemas import Chunk, ChunkType, StructureNode

from tests.conftest import make_article_node, make_structured_document

_ENCODER = tiktoken.get_encoding("cl100k_base")


def _make_chunk(text: str, chunk_type: ChunkType = ChunkType.ARTICLE, token_count: int | None = None) -> Chunk:
    """테스트용 Chunk 를 생성한다."""
    tc = token_count if token_count is not None else len(_ENCODER.encode(text))
    return Chunk(
        id=str(uuid.uuid4()),
        chunk_type=chunk_type,
        clause_no="제1조",
        page_start=1,
        page_end=1,
        token_count=tc,
        text=text,
    )


def _make_long_text(token_count: int) -> str:
    """정확히 token_count 개 토큰에 해당하는 텍스트를 생성한다.

    BPE 토큰 병합을 피하기 위해 매번 다른 숫자를 포함한 다양한 단어 패턴을 사용한다.
    """
    # 매 반복마다 다른 숫자를 넣어 BPE 병합 방지
    parts = [
        f"clause {i} terms auto fire policy cover claim risk loss pay deal "
        for i in range(token_count // 10 + 200)
    ]
    text = "".join(parts)
    token_ids = _ENCODER.encode(text)
    if len(token_ids) < token_count:
        # 부족하면 padding 추가
        extra = " policy claim loss risk " * (token_count - len(token_ids) + 100)
        text = text + extra
        token_ids = _ENCODER.encode(text)
    sliced = token_ids[:token_count]
    return _ENCODER.decode(sliced)


# ===========================================================================
# chunk_document — 정상 케이스
# ===========================================================================


class TestChunkDocumentHappyPath:
    """chunk_document 정상 동작 검증."""

    def test_single_article_within_limit_returns_one_chunk(self):
        # 토큰 한도 내 단순 조항 → 1개 청크
        text = "제1조 (보험금 지급)\n보험사고 발생 시 보험금을 지급합니다."
        article = make_article_node(text=text)
        struct = make_structured_document([article])

        chunks = chunk_document(struct, max_tokens=DEFAULT_MAX_TOKENS)

        # MIN_CHUNK_TOKENS 이상이어야 채택
        # 짧은 텍스트면 필터링될 수 있으므로 텍스트 토큰 수 확인
        tokens = len(_ENCODER.encode(text))
        if tokens >= MIN_CHUNK_TOKENS:
            assert len(chunks) == 1
            assert chunks[0].chunk_type == ChunkType.ARTICLE

    def test_chunk_preserves_clause_no(self):
        # 청크에 clause_no 가 보존됨
        text = "제5조 (면책사유)\n" + "본문 " * 20
        article = make_article_node(clause_no="제5조", text=text)
        struct = make_structured_document([article])

        chunks = chunk_document(struct, max_tokens=DEFAULT_MAX_TOKENS)

        assert any(c.clause_no == "제5조" for c in chunks)

    def test_multiple_articles_return_multiple_chunks(self):
        # 조항 2개 → 청크 2개 이상
        nodes = []
        root_ids = []
        for i in range(1, 3):
            article = make_article_node(
                clause_no=f"제{i}조",
                text=f"제{i}조 (조항{i})\n" + f"내용입니다 조항{i}. " * 15,
            )
            nodes.append(article)
            root_ids.append(article.id)

        struct = make_structured_document(nodes, root_ids=root_ids)
        chunks = chunk_document(struct, max_tokens=DEFAULT_MAX_TOKENS)

        assert len(chunks) >= 2

    def test_table_node_creates_table_chunk(self):
        # TABLE 타입 루트 노드 → TABLE 청크
        from app.domains.chunks.schemas import RawTable

        table_node = StructureNode(
            id=str(uuid.uuid4()),
            chunk_type=ChunkType.TABLE,
            clause_no="제1조",
            page_start=1,
            page_end=1,
            text="보장 한도",
            raw_table=RawTable(
                page=1,
                rows=[["항목", "금액"], ["사망", "1억"]],
                caption="보장 한도",
            ),
        )
        struct = make_structured_document([table_node], root_ids=[table_node.id])
        chunks = chunk_document(struct, max_tokens=DEFAULT_MAX_TOKENS)

        assert len(chunks) == 1
        assert chunks[0].chunk_type == ChunkType.TABLE
        assert "항목" in chunks[0].text

    def test_chunks_have_valid_page_range(self):
        # 청크의 page_start <= page_end 이어야 함
        text = "제1조 (보험금)\n" + "내용 " * 30
        article = make_article_node(text=text, page=3)
        struct = make_structured_document([article])

        chunks = chunk_document(struct)
        for c in chunks:
            assert c.page_start <= c.page_end


# ===========================================================================
# chunk_document — 토큰 한도 초과 시나리오
# ===========================================================================


class TestChunkDocumentOverLimit:
    """토큰 한도 초과 시 paragraph 단위 분할 검증."""

    def test_article_over_limit_splits_into_paragraph_chunks(self):
        # 조항 내용이 max_tokens 초과 → paragraph 단위로 분할
        article = StructureNode(
            id=str(uuid.uuid4()),
            chunk_type=ChunkType.ARTICLE,
            clause_no="제1조",
            sub_no=None,
            page_start=1,
            page_end=1,
            text="제1조 (장문 조항)",
        )

        # 여러 paragraph 추가 (각 50 토큰 이상)
        para_ids = []
        nodes = [article]
        for i, char in enumerate(["①", "②", "③"]):
            para = StructureNode(
                id=str(uuid.uuid4()),
                chunk_type=ChunkType.PARAGRAPH,
                clause_no="제1조",
                sub_no=char,
                page_start=1,
                page_end=1,
                text=f"항 내용 {i + 1}입니다. " * 5,
                parent_id=article.id,
            )
            nodes.append(para)
            article.children_ids.append(para.id)
            para_ids.append(para.id)

        struct = make_structured_document(nodes, root_ids=[article.id])
        # max_tokens=5 로 강제 초과
        chunks = chunk_document(struct, max_tokens=5)

        # 분할 시 PARAGRAPH 타입 청크가 생성되어야 함
        para_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
        assert len(para_chunks) > 0

    def test_short_chunks_are_filtered(self):
        # MIN_CHUNK_TOKENS 미만 청크는 필터링됨
        article = make_article_node(text="제1조\n짧")  # 매우 짧음
        struct = make_structured_document([article])

        chunks = chunk_document(struct)

        for c in chunks:
            assert c.token_count >= MIN_CHUNK_TOKENS


# ===========================================================================
# _enforce_hard_limit
# ===========================================================================


class TestEnforceHardLimit:
    """HARD_TOKEN_LIMIT 초과 청크 강제 분할 검증."""

    def test_chunk_within_hard_limit_passes_through(self):
        # HARD_TOKEN_LIMIT 이하 청크는 그대로 통과
        chunk = _make_chunk("짧은 텍스트 내용입니다.")
        result = _enforce_hard_limit([chunk], _ENCODER)

        assert len(result) == 1
        assert result[0].id == chunk.id

    def test_chunk_over_hard_limit_is_split(self):
        # HARD_TOKEN_LIMIT 초과 청크는 분할됨
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 100)
        chunk = _make_chunk(long_text)
        result = _enforce_hard_limit([chunk], _ENCODER)

        assert len(result) >= 2

    def test_split_chunks_total_coverage(self):
        # 분할된 청크의 토큰 합이 원본보다 크거나 같아야 함 (오버랩으로 인해 클 수 있음)
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 500)
        chunk = _make_chunk(long_text)
        result = _enforce_hard_limit([chunk], _ENCODER)

        total_tokens = sum(c.token_count for c in result)
        original_tokens = chunk.token_count
        assert total_tokens >= original_tokens

    def test_mixed_chunks_only_large_ones_split(self):
        # 큰 청크와 작은 청크가 섞여 있으면 큰 것만 분할
        small_chunk = _make_chunk("작은 청크입니다.")
        large_text = _make_long_text(HARD_TOKEN_LIMIT + 100)
        large_chunk = _make_chunk(large_text)

        result = _enforce_hard_limit([small_chunk, large_chunk], _ENCODER)

        # 작은 청크는 그대로 1개, 큰 청크는 2개 이상 → 총 3개 이상
        assert len(result) >= 3
        assert result[0].id == small_chunk.id


# ===========================================================================
# _split_by_tokens
# ===========================================================================


class TestSplitByTokens:
    """_split_by_tokens 오버랩 검증."""

    def test_split_creates_multiple_pieces(self):
        # HARD_TOKEN_LIMIT 초과 텍스트 → 2개 이상 조각
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 200)
        chunk = _make_chunk(long_text)
        pieces = _split_by_tokens(chunk, _ENCODER)

        assert len(pieces) >= 2

    def test_each_piece_within_hard_limit(self):
        # 각 조각은 HARD_TOKEN_LIMIT 이하
        long_text = _make_long_text(HARD_TOKEN_LIMIT * 2 + 100)
        chunk = _make_chunk(long_text)
        pieces = _split_by_tokens(chunk, _ENCODER)

        for p in pieces:
            assert p.token_count <= HARD_TOKEN_LIMIT

    def test_pieces_have_part_number_in_sub_no(self):
        # 각 조각의 sub_no 에 "part-N" 포함
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 200)
        chunk = _make_chunk(long_text)
        pieces = _split_by_tokens(chunk, _ENCODER)

        for piece in pieces:
            assert "part-" in piece.sub_no

    def test_overlap_means_second_piece_starts_before_first_ends(self):
        # 오버랩으로 인해 2번째 조각의 시작이 1번째 조각 끝과 겹침
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 200)
        chunk = _make_chunk(long_text)
        pieces = _split_by_tokens(chunk, _ENCODER)

        # 오버랩 확인: 2번째 조각 텍스트의 앞부분이 1번째 조각 텍스트 뒤에 있어야 함
        if len(pieces) >= 2:
            piece1_tokens = _ENCODER.encode(pieces[0].text)
            piece2_tokens = _ENCODER.encode(pieces[1].text)

            # step = HARD_TOKEN_LIMIT - SPLIT_OVERLAP_TOKENS
            # 2번째 조각은 step 위치에서 시작 → piece1 의 마지막 SPLIT_OVERLAP_TOKENS 개가 piece2 앞에 있어야 함
            overlap_from_piece1 = piece1_tokens[-SPLIT_OVERLAP_TOKENS:]
            overlap_in_piece2 = piece2_tokens[:SPLIT_OVERLAP_TOKENS]
            assert overlap_from_piece1 == overlap_in_piece2

    def test_chunk_type_and_clause_preserved(self):
        # 분할 후 chunk_type, clause_no 유지
        long_text = _make_long_text(HARD_TOKEN_LIMIT + 200)
        chunk = _make_chunk(long_text, chunk_type=ChunkType.ARTICLE)
        pieces = _split_by_tokens(chunk, _ENCODER)

        for p in pieces:
            assert p.chunk_type == ChunkType.ARTICLE
            assert p.clause_no == chunk.clause_no

    def test_single_piece_when_text_exactly_fits(self):
        # 텍스트가 HARD_TOKEN_LIMIT 이하면 조각 1개
        text = _make_long_text(HARD_TOKEN_LIMIT - 10)
        chunk = _make_chunk(text)
        # _split_by_tokens 는 HARD_TOKEN_LIMIT 초과일 때만 호출하는 게 의도이나
        # HARD_TOKEN_LIMIT 이하 입력 시 조각 1개만 나와야 함
        pieces = _split_by_tokens(chunk, _ENCODER)
        assert len(pieces) == 1


class TestTokenLimitInvariant:
    """PM-43 — 강제 분할 임계가 임베딩 한도보다 작음을 구조적으로 보장(silent break 방지)."""

    def test_hard_limit_below_embedding_max(self):
        from app.domains.chunks.chunker import HARD_TOKEN_LIMIT
        from app.infrastructure.embeddings.service import MAX_INPUT_TOKENS

        # 청크 꼬리가 임베딩에서 잘려 검색 사각지대가 되는 일(7000/8191 사고)을 차단
        assert HARD_TOKEN_LIMIT < MAX_INPUT_TOKENS

    def test_hard_limit_derived_not_hardcoded(self):
        # 임베딩 한도를 바꾸면 임계도 따라가야 한다(손 결합 제거 확인)
        from app.domains.chunks import chunker
        from app.infrastructure.embeddings.service import MAX_INPUT_TOKENS

        assert chunker.HARD_TOKEN_LIMIT == MAX_INPUT_TOKENS - chunker._EMBED_SAFETY_MARGIN
