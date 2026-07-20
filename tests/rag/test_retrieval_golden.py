"""tests.rag.test_retrieval_golden

Sprint 32 T1 — 검색 골든셋 회귀 게이트.

기본 pytest 실행에는 포함되지 않고(-m eval 필요) 라이브 임베딩 API + 인덱싱된
app.db 를 요구한다. CI/수동: `.venv/bin/python -m pytest -m eval -q`.
정합 검증(validate)은 네트워크 불필요라 항상 실행 가능.
"""

from __future__ import annotations

import pytest
from eval.retrieval_metrics import (
    THRESHOLDS,
    default_retrieve_fn,
    evaluate,
    load_golden,
    validate_against_corpus,
)


def test_golden_set_schema():
    """골든셋 스키마 불변식 — 30문항, 필수 필드, 5개사 커버."""
    items = load_golden()
    assert len(items) == 30
    insurers = {i["insurer_id"] for i in items}
    assert insurers == {"samsung", "hanwha", "hyundai", "meritz", "lotte"}
    for item in items:
        assert item["id"] and item["query"]
        assert item["expected"]["clause_no"], item["id"]


def _corpus_indexed() -> bool:
    """인덱스된 app.db(documents 테이블) 존재 여부 — CI 러너에는 없다(gitignore)."""
    import sqlite3
    from pathlib import Path

    db = Path(__file__).resolve().parents[2] / "app.db"
    if not db.exists():
        return False
    try:
        with sqlite3.connect(db) as conn:
            return bool(
                conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
                ).fetchone()
            )
    except sqlite3.Error:
        return False


@pytest.mark.skipif(not _corpus_indexed(), reason="인덱스된 app.db 필요 (로컬 전용, CI 제외)")
def test_golden_set_corpus_alignment():
    """모든 문항의 정답 청크가 코퍼스에 실존 (인덱스 갱신 시 표류 감지)."""
    fails = validate_against_corpus()
    assert not fails, f"코퍼스 정합 실패: {fails}"


@pytest.mark.eval
def test_retrieval_thresholds():
    """라이브 검색 품질 게이트 — 임계 미달 시 회귀."""
    result = evaluate(default_retrieve_fn)
    m = result.metrics()
    for key, thr in THRESHOLDS.items():
        assert m.get(key, 0) >= thr, f"{key}={m.get(key)} < {thr} (전체: {m})"
