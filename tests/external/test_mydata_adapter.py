"""tests.external.test_mydata_adapter

app/external/mydata/adapter.py 단위 테스트.

테스트 대상:
    - DummyAdapter — fixture 로드 + user_id 매칭 + 미존재 빈 리스트
    - RealAdapter — 모든 호출 MydataNotConfiguredError
    - get_mydata_adapter 팩토리 — Settings.mydata_backend 분기
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from app.infrastructure.external.mydata.adapter import (
    DummyAdapter,
    MydataNotConfiguredError,
    RealAdapter,
    clear_cache,
    get_mydata_adapter,
)


@pytest.fixture
def temp_fixture(tmp_path: Path) -> Path:
    data = {
        "1": [
            {
                "insurer_id": "hanwha",
                "insurer_name": "한화손해보험",
                "product_id": "auto_personal",
                "product_name": "개인용 자동차보험",
                "policy_no": "TEST-001",
                "area": "auto",
                "valid_from": "2026-01-01",
                "valid_to": None,
            }
        ],
        "2": [],
    }
    p = tmp_path / "users.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestDummyAdapter:
    def test_fetch_returns_list_for_existing_user(self, temp_fixture):
        adapter = DummyAdapter(temp_fixture)
        result = adapter.fetch_insurances("1")
        assert len(result) == 1
        assert result[0]["insurer_id"] == "hanwha"
        assert result[0]["area"] == "auto"

    def test_fetch_returns_empty_for_missing_user(self, temp_fixture):
        adapter = DummyAdapter(temp_fixture)
        result = adapter.fetch_insurances("999")
        assert result == []

    def test_fetch_returns_empty_for_user_with_no_insurances(self, temp_fixture):
        adapter = DummyAdapter(temp_fixture)
        result = adapter.fetch_insurances("2")
        assert result == []

    def test_missing_fixture_file_returns_empty(self, tmp_path: Path):
        adapter = DummyAdapter(tmp_path / "nonexistent.json")
        result = adapter.fetch_insurances("1")
        assert result == []


class TestRealAdapter:
    def test_raises_not_configured_error(self):
        adapter = RealAdapter()
        with pytest.raises(MydataNotConfiguredError, match="사업자 인증 대기"):
            adapter.fetch_insurances("1")


class TestGetMydataAdapterFactory:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    def test_returns_dummy_when_settings_dummy(self):
        with patch("app.infrastructure.external.mydata.adapter.get_settings") as mock_s:
            mock_s.return_value.mydata_backend = "dummy"
            adapter = get_mydata_adapter()
            assert isinstance(adapter, DummyAdapter)

    def test_returns_real_when_settings_real(self):
        with patch("app.infrastructure.external.mydata.adapter.get_settings") as mock_s:
            mock_s.return_value.mydata_backend = "real"
            adapter = get_mydata_adapter()
            assert isinstance(adapter, RealAdapter)

    def test_factory_cached(self):
        with patch("app.infrastructure.external.mydata.adapter.get_settings") as mock_s:
            mock_s.return_value.mydata_backend = "dummy"
            a1 = get_mydata_adapter()
            a2 = get_mydata_adapter()
            assert a1 is a2


class TestProductionFixture:
    """실제 data/demo/mydata.json (10 페르소나) 검증. 실손 전용 — 각자 실손 1건."""

    def test_p01_samsung_silson(self):
        adapter = DummyAdapter()
        result = adapter.fetch_insurances("p01")
        assert len(result) == 1
        assert result[0]["area"] == "accident_disease"
        assert result[0]["insurer_id"] == "samsung"
        assert result[0]["product_id"] == "samsung_silson"

    def test_p02_db_silson(self):
        adapter = DummyAdapter()
        result = adapter.fetch_insurances("p02")
        assert len(result) == 1
        assert result[0]["insurer_id"] == "db"
        assert result[0]["product_id"] == "db_silson"

    def test_all_personas_single_indexed_silson(self):
        """모든 페르소나가 인덱싱된 5개 보험사 실손 1건씩 보유 (실손 중복가입 금지 반영)."""
        adapter = DummyAdapter()
        insurers = {"samsung", "db", "hyundai", "meritz", "hanwha"}
        for pid in (f"p{n:02d}" for n in range(1, 11)):
            result = adapter.fetch_insurances(pid)
            assert len(result) == 1
            ins = result[0]
            assert ins["area"] == "accident_disease"
            assert ins["insurer_id"] in insurers
            assert ins["product_id"] == f"{ins['insurer_id']}_silson"
            assert ins["product_name"] == "실손의료보험"
