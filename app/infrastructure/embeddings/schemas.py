"""app.infrastructure.embeddings.schemas

파일 경로: app/embeddings/schemas.py
목적: OpenAI 임베딩 호출의 입력·출력 pydantic 모델.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EmbeddingRequest(BaseModel):
    """배치 임베딩 요청 — Sprint 2 HTTP API 에서 사용 가능한 표준 형태."""

    texts: list[str] = Field(..., min_length=1, description="임베딩 대상 문자열 리스트")
    model: str | None = Field(
        default=None,
        description="모델명 (None 이면 Settings.embedding_model 사용)",
    )


class EmbeddingResponse(BaseModel):
    """임베딩 응답."""

    embeddings: list[list[float]] = Field(..., description="입력 순서 보존")
    model: str = Field(..., description="실제 사용된 모델명")
    dimension: int = Field(..., description="임베딩 차원 수 (Upstage 4096)")
