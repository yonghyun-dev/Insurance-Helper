"""tests.embeddings.test_service

app/embeddings/service.py 단위 테스트 — Sprint 16 1b (Upstage 임베딩, query/passage 분리).

검증 핵심:
    - _model_for_role: provider/role 에 따른 모델명 해석 (upstage query/passage, openai 단일)
    - embed_texts: 배치(100) 분할 + 순서 보존 + role 모델 전달
    - 빈 입력 → []
"""

from __future__ import annotations

from types import SimpleNamespace

import app.infrastructure.core.config as _cfg
import app.infrastructure.embeddings.service as svc


def _settings(**kw):
    return _cfg.Settings(_env_file=None, **kw)


class _RecordingClient:
    """embeddings.create 호출을 기록하는 가짜 OpenAI 호환 클라이언트."""

    def __init__(self, dim: int = 8):
        self.dim = dim
        self.calls: list[dict] = []
        outer = self

        class _Embeddings:
            def create(self, model, input):  # noqa: A002  # OpenAI SDK 시그니처
                outer.calls.append({"model": model, "n": len(input)})
                data = [SimpleNamespace(embedding=[float(i)] * outer.dim) for i in range(len(input))]
                return SimpleNamespace(data=data)

        self.embeddings = _Embeddings()


class TestModelForRole:
    def test_upstage_query_model(self, monkeypatch):
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        assert svc._model_for_role("query") == "embedding-query"

    def test_upstage_passage_model(self, monkeypatch):
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        assert svc._model_for_role("passage") == "embedding-passage"

    def test_upstage_respects_overrides(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "get_settings",
            lambda: _settings(
                embedding_provider="upstage",
                upstage_embedding_query_model="embedding-query-250101",
            ),
        )
        assert svc._model_for_role("query") == "embedding-query-250101"

    def test_openai_single_model_ignores_role(self, monkeypatch):
        monkeypatch.setattr(
            svc,
            "get_settings",
            lambda: _settings(embedding_provider="openai", embedding_model="text-embedding-3-small"),
        )
        assert svc._model_for_role("query") == "text-embedding-3-small"
        assert svc._model_for_role("passage") == "text-embedding-3-small"


class TestEmbedTexts:
    def test_empty_returns_empty(self):
        assert svc.embed_texts([]) == []

    def test_passage_is_default_role(self, monkeypatch):
        client = _RecordingClient()
        monkeypatch.setattr(svc, "_get_client", lambda: client)
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        svc.embed_texts(["a", "b"])
        assert client.calls[0]["model"] == "embedding-passage"

    def test_query_role_uses_query_model(self, monkeypatch):
        client = _RecordingClient()
        monkeypatch.setattr(svc, "_get_client", lambda: client)
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        svc.embed_texts(["질문"], role="query")
        assert client.calls[0]["model"] == "embedding-query"

    def test_batching_splits_at_100(self, monkeypatch):
        client = _RecordingClient()
        monkeypatch.setattr(svc, "_get_client", lambda: client)
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        out = svc.embed_texts([f"t{i}" for i in range(250)])
        assert len(out) == 250  # 순서·개수 보존
        assert [c["n"] for c in client.calls] == [100, 100, 50]  # 3 배치

    def test_batch_size_is_100(self):
        assert svc.BATCH_SIZE == 100


class TestTruncate:
    """Upstage 4000 토큰 한도 — 초과 입력 절단 (passage 색인)."""

    def test_short_text_unchanged(self):
        assert svc._truncate("짧은 약관 문장") == "짧은 약관 문장"

    def test_long_text_capped(self):
        long_text = "보험 약관 조항 " * 5000  # 3800 토큰 초과
        out = svc._truncate(long_text)
        assert len(svc._encoder().encode(out)) <= svc.MAX_INPUT_TOKENS

    def test_embed_truncates_before_call(self, monkeypatch):
        client = _RecordingClient()
        monkeypatch.setattr(svc, "_get_client", lambda: client)
        monkeypatch.setattr(svc, "get_settings", lambda: _settings(embedding_provider="upstage"))
        out = svc.embed_texts(["보험 약관 조항 " * 5000])  # 초과 입력 1건
        assert len(out) == 1  # 절단 후 정상 임베딩
