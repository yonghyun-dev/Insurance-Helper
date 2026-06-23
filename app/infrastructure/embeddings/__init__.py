"""app.infrastructure.embeddings

파일 경로: app/embeddings/__init__.py
목적: OpenAI 임베딩 호출 어댑터.
"""

from app.infrastructure.embeddings.schemas import EmbeddingRequest, EmbeddingResponse
from app.infrastructure.embeddings.service import BATCH_SIZE, embed_texts

__all__ = ["BATCH_SIZE", "EmbeddingRequest", "EmbeddingResponse", "embed_texts"]
