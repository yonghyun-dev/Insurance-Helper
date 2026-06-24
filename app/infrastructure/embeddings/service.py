"""app.infrastructure.embeddings.service

파일 경로: app/embeddings/service.py
목적: 임베딩 호출 어댑터 (Sprint 16 1b — Upstage solar-embedding 4096-d 전용).
주요 기능:
    - `embed_texts(texts, role=...)` 배치 임베딩 (passage=색인 / query=검색)
    - 재시도(tenacity) + 한도 보호
주요 의존성: openai(호환), tenacity

설계 메모:
    - 클라이언트/키/base_url 은 app.infrastructure.llm.client.get_embedding_client() 중앙 팩토리에 위임
      (embedding_provider=upstage 기본, OpenAI 폴백 없음 — 국내 모델 전용 정책).
    - Upstage 는 query/passage 모델이 분리됨: 색인=embedding-passage, 검색=embedding-query (4096-d).
    - Upstage 한도: 배치 ≤100, 입력 ≤4000토큰. → BATCH_SIZE=100.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import tiktoken
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.infrastructure.core.config import get_settings
from app.infrastructure.core.exceptions import EmbeddingError
from app.infrastructure.core.logging import get_logger
from app.infrastructure.llm.client import get_embedding_client

logger = get_logger(__name__)

# Upstage 임베딩 한도(배치 100). OpenAI(2048)보다 보수적 — Upstage 가 더 작은 제약.
BATCH_SIZE = 100

# Upstage 임베딩 입력 최대 4000 토큰. 기존 청크는 OpenAI(8191) 기준이라 일부 초과 →
# 토크나이저 차이 마진 포함 3800 으로 안전 절단(passage 색인 한정 — query 는 짧음).
MAX_INPUT_TOKENS = 3800

EmbeddingRole = Literal["passage", "query"]


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    """입력 토큰 절단용 인코더 (cl100k_base — Upstage 토큰수의 근사 프록시)."""
    return tiktoken.get_encoding("cl100k_base")


def _truncate(text: str) -> str:
    """Upstage 4000 토큰 한도 초과 입력을 MAX_INPUT_TOKENS 로 절단한다."""
    enc = _encoder()
    tokens = enc.encode(text)
    if len(tokens) <= MAX_INPUT_TOKENS:
        return text
    logger.warning("임베딩 입력 절단: %d → %d 토큰", len(tokens), MAX_INPUT_TOKENS)
    return enc.decode(tokens[:MAX_INPUT_TOKENS])


def _get_client() -> OpenAI:
    """임베딩 클라이언트 — 중앙 팩토리(app.infrastructure.llm.client)에 위임.

    제품 임베딩은 Upstage 전용(embedding_provider=upstage 기본), OpenAI 폴백 없음.
    심볼명 유지 — 테스트가 본 함수를 패치한다. 캐시는 팩토리가 담당.
    """
    return get_embedding_client()


def _model_for_role(role: EmbeddingRole) -> str:
    """role 에 따른 Upstage 임베딩 모델명. query → embedding-query / passage → embedding-passage."""
    settings = get_settings()
    if role == "query":
        return settings.upstage_embedding_query_model
    return settings.upstage_embedding_passage_model


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _embed_batch(client: OpenAI, model: str, texts: list[str]) -> list[list[float]]:
    """배치 1개 임베딩 호출. 일시적 네트워크 오류는 3회 재시도."""
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


def embed_texts(texts: list[str], *, role: EmbeddingRole = "passage") -> list[list[float]]:
    """여러 텍스트를 배치로 임베딩한다.

    Args:
        texts: 임베딩할 문자열 리스트.
        role: "passage"(색인·기본) 또는 "query"(검색). Upstage 는 모델이 분리됨.

    Returns:
        각 입력 텍스트에 대응하는 임베딩 벡터 리스트 (순서 보존).

    Raises:
        ConfigurationError: API 키 누락 (팩토리에서).
        EmbeddingError: 모든 재시도 실패 또는 응답 개수 불일치.
    """
    if not texts:
        return []

    client = _get_client()
    model = _model_for_role(role)
    safe_texts = [_truncate(t) for t in texts]

    all_embeddings: list[list[float]] = []
    total_batches = (len(safe_texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        batch = safe_texts[start:start + BATCH_SIZE]
        try:
            embeddings = _embed_batch(client, model, batch)
        except Exception as exc:
            raise EmbeddingError(
                f"임베딩 호출 실패 (batch {batch_idx + 1}/{total_batches}): {exc}"
            ) from exc

        if len(embeddings) != len(batch):
            raise EmbeddingError(
                f"임베딩 응답 개수 불일치: 요청 {len(batch)}, 응답 {len(embeddings)}"
            )

        all_embeddings.extend(embeddings)
        logger.info(
            "임베딩 batch %d/%d 완료 (role=%s model=%s 텍스트 %d개)",
            batch_idx + 1, total_batches, role, model, len(batch),
        )

    return all_embeddings
