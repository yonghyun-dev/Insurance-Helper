"""app.domains.chunks.schemas

파일 경로: app/chunks/schemas.py
목적: 약관 청크 도메인의 입력·중간·출력 pydantic 모델.

주요 객체:
    파서 출력 (parser.py)        : RawTable / RawPage / RawDocument
    구조 인식 (structure.py)     : StructureNode / StructuredDocument
    청킹 결과 (chunker.py)       : Chunk
    HTTP/CLI 응답                : ChunkRead

원칙(domain-architecture):
    - 모든 schemas.py 는 pydantic BaseModel 사용 (일관성)
    - models.py(SQLAlchemy ORM)와 책임 분리: models = DB 테이블, schemas = 도메인 데이터 형태

설계 참고:
    - docs/design/data-model.md `clause_chunks` 스키마와 호환되도록 필드 명명 유지
    - StructuredDocument 는 by_id(O(1)) 헬퍼 메서드를 제공
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


class ChunkType(StrEnum):
    """청크 유형. SQLite `clause_chunks.chunk_type` CHECK 제약과 동일."""

    ARTICLE = "article"  # 제N조 본문
    PARAGRAPH = "paragraph"  # 항 (①②③)
    ITEM = "item"  # 호/목 ("1." "(1)" "가.")
    TABLE = "table"  # 표
    ANNEX = "annex"  # 별표/부록
    OTHER = "other"  # 기타


class RawTable(BaseModel):
    """파서가 추출한 표 1개."""

    page: int = Field(..., ge=1)
    rows: list[list[str]] = Field(default_factory=list, description="행 × 열 텍스트")
    caption: str | None = Field(default=None, description="주변 본문에서 추정한 캡션")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="(x0, y0, x1, y1) — pdfplumber bbox"
    )


class RawPage(BaseModel):
    """파서가 추출한 페이지 1개."""

    page: int = Field(..., ge=1, description="1부터 시작")
    text: str = Field(..., description="헤더/푸터 제거된 본문 텍스트")
    raw_text: str = Field(..., description="헤더/푸터 포함 원본")
    tables: list[RawTable] = Field(default_factory=list)
    width: float = Field(default=0.0)
    height: float = Field(default=0.0)


class RawDocument(BaseModel):
    """파서 출력. 파일 단위 원시 파싱 결과."""

    file_path: str
    page_count: int = Field(..., ge=0)
    pages: list[RawPage] = Field(default_factory=list)
    parser_version: str = Field(..., description="재처리 추적용")
    metadata: dict[str, str] = Field(default_factory=dict, description="producer/title 등")


class StructureNode(BaseModel):
    """구조 인식 트리의 노드.

    `parent` 는 상호 참조 그래프를 피하기 위해 직접 보관하지 않고 ID 로만 표현한다.
    """

    id: str = Field(..., description="UUID")
    chunk_type: ChunkType
    clause_no: str | None = Field(default=None, description="예: '제15조'")
    sub_no: str | None = Field(default=None, description="예: '①', '1.', '가.'")
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    text: str = Field(default="")
    parent_id: str | None = Field(default=None)
    children_ids: list[str] = Field(default_factory=list)
    raw_table: RawTable | None = Field(default=None, description="chunk_type==TABLE 일 때만")


class StructuredDocument(BaseModel):
    """구조 인식 결과. RawDocument 를 트리로 정리한 산출물.

    `by_id` O(1) 조회를 위해 내부 `_id_index` 를 lazy 로 보유한다 (PrivateAttr).
    `nodes` 를 외부에서 직접 수정하면 인덱스가 stale 해지므로, 수정이 필요하면
    새 `StructuredDocument` 를 생성해라.
    """

    file_path: str
    parser_version: str
    nodes: list[StructureNode] = Field(default_factory=list)
    root_ids: list[str] = Field(default_factory=list)

    _id_index: dict[str, StructureNode] | None = PrivateAttr(default=None)

    def by_id(self, node_id: str) -> StructureNode:
        """노드 ID로 직접 조회 (트리 탐색용)."""
        if self._id_index is None:
            self._id_index = {n.id: n for n in self.nodes}
        try:
            return self._id_index[node_id]
        except KeyError as exc:
            raise KeyError(f"StructureNode not found: {node_id}") from exc


class Chunk(BaseModel):
    """청킹 결과 1건. data-model.md `clause_chunks` 스키마와 매핑.

    `document_id` 는 청킹 단계에서는 비어 있고, ingest 단계에서 SQLite INSERT 후
    채워진다. 임베딩·벡터 DB 적재는 본 Chunk 를 입력으로 받는다.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    chunk_type: ChunkType
    clause_no: str | None = None
    sub_no: str | None = None
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    token_count: int = Field(..., ge=0)
    text: str
    parent_chunk_id: str | None = None
    document_id: int | None = None
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)


class ChunkRead(BaseModel):
    """HTTP/CLI 응답용 청크 표현 — 향후 Sprint 2 search router 에서 사용."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: int
    chunk_type: str
    clause_no: str | None = None
    sub_no: str | None = None
    page_start: int
    page_end: int
    token_count: int
    text: str
