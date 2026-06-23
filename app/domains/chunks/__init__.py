"""app.domains.chunks

파일 경로: app/chunks/__init__.py
목적: 약관 청크 도메인 — PDF 파싱(parser), 구조 인식(structure), 청킹(chunker),
      pydantic schemas, SQLAlchemy 모델, CRUD/service/router 까지 한 도메인에 응집.

호출 흐름:
    parser → structure → chunker (도메인 내부)
    service.process_pdf() → 외부 도메인(ingestion 등)이 사용하는 표준 진입점
"""

from app.domains.chunks.models import CHUNK_TYPES, ClauseChunk
from app.domains.chunks.schemas import (
    Chunk,
    ChunkRead,
    ChunkType,
    RawDocument,
    RawPage,
    RawTable,
    StructuredDocument,
    StructureNode,
)

__all__ = [
    "CHUNK_TYPES",
    "Chunk",
    "ChunkRead",
    "ChunkType",
    "ClauseChunk",
    "RawDocument",
    "RawPage",
    "RawTable",
    "StructuredDocument",
    "StructureNode",
]
