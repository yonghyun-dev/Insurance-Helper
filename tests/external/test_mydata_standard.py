"""마이데이터 표준 API 정합 (Sprint 35) — normalizer + RealAdapter.

'승인 후 base_url/token 만 설정하면 동일하게 동작' 주장을 코드로 보증:
표준 규격 모양(insu_num/prod_name/insu_status/issue_date/exp_date)의 응답이
DummyAdapter 와 동일한 InsuranceDict 로 정규화되는지 검증한다.
"""

from __future__ import annotations

import pytest
from app.infrastructure.external.mydata.adapter import (
    MydataNotConfiguredError,
    RealAdapter,
    derive_generation,
    normalize_standard_insurance,
)


class TestDeriveGeneration:
    """실손 세대 파생 — 판매시기 경계값."""

    @pytest.mark.parametrize(
        ("issue_date", "expected"),
        [
            ("20090930", 1),  # 1세대(구실손) 마지막 날
            ("20091001", 2),  # 2세대(표준화) 시작
            ("20170331", 2),
            ("20170401", 3),  # 3세대(착한실손) 시작
            ("20210630", 3),
            ("20210701", 4),  # 4세대 시작
            ("2024-01-01", 4),  # ISO 표기도 허용
        ],
    )
    def test_boundaries(self, issue_date, expected):
        assert derive_generation(issue_date) == expected

    def test_invalid_returns_none(self):
        assert derive_generation("") is None
        assert derive_generation("작년쯤") is None


class TestNormalizeStandardInsurance:
    def _item(self, **over):
        base = {
            "insu_num": "SILSON-2024-0001",
            "prod_name": "무배당 삼성화재 실손의료비보험(2304.3)",
            "insu_type": "05",
            "insu_status": "02",
        }
        base.update(over)
        return base

    def test_maps_standard_fields_to_internal_schema(self):
        rec = normalize_standard_insurance(
            self._item(), basic={"issue_date": "20240101", "exp_date": "99991231"}
        )
        assert rec == {
            "insurer_id": "samsung",
            "insurer_name": "삼성화재",
            "product_id": "samsung_silson",
            "product_name": "실손의료보험",
            "policy_no": "SILSON-2024-0001",
            "area": "accident_disease",
            "valid_from": "2024-01-01",
            "valid_to": None,  # 99991231 = 무기한
            "generation": 4,
        }

    def test_generation_derived_from_issue_date(self):
        rec = normalize_standard_insurance(
            self._item(prod_name="현대해상 실손의료보험"),
            basic={"issue_date": "20210301", "exp_date": "20360301"},
        )
        assert rec is not None
        assert rec["insurer_id"] == "hyundai"
        assert rec["generation"] == 3
        assert rec["valid_to"] == "2036-03-01"

    def test_non_silson_excluded(self):
        assert normalize_standard_insurance(self._item(prod_name="삼성화재 자동차보험")) is None

    def test_inactive_contract_excluded(self):
        # 04=실효 — 정상(02) 아닌 계약은 판정 대상에서 제외
        assert normalize_standard_insurance(self._item(insu_status="04")) is None

    def test_unmapped_insurer_excluded(self):
        assert normalize_standard_insurance(self._item(prod_name="DB손해보험 실손의료보험")) is None


class TestRealAdapter:
    def test_unconfigured_raises(self, monkeypatch):
        # base_url/token 미설정 → 기존 skeleton 과 동일하게 NotConfigured
        monkeypatch.setenv("MYDATA_API_BASE_URL", "")
        monkeypatch.setenv("MYDATA_API_TOKEN", "")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()
        with pytest.raises(MydataNotConfiguredError):
            RealAdapter().fetch_insurances("p01")
        get_settings.cache_clear()

    def test_configured_calls_standard_endpoints_and_normalizes(self, monkeypatch):
        """base_url/token 설정 시 — 표준 응답이 InsuranceDict 로 정규화되어 반환."""
        monkeypatch.setenv("MYDATA_API_BASE_URL", "https://api.example-insu.test")
        monkeypatch.setenv("MYDATA_API_TOKEN", "test-token")
        from app.infrastructure.core.config import get_settings

        get_settings.cache_clear()

        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer test-token"
            if request.url.path == "/v2/insu/insurances":
                return httpx.Response(200, json={
                    "org_code": "TEST_ORG",
                    "insu_list": [
                        {"insu_num": "SIL-1", "prod_name": "메리츠화재 실손의료비보험",
                         "insu_type": "05", "insu_status": "02"},
                        {"insu_num": "AUTO-1", "prod_name": "메리츠 자동차보험",
                         "insu_type": "01", "insu_status": "02"},
                    ],
                })
            if request.url.path == "/v2/insu/insurances/basic":
                return httpx.Response(200, json={"issue_date": "20150301", "exp_date": "20300301"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        real_client = httpx.Client

        def patched_client(*args, **kwargs):
            kwargs["transport"] = transport
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", patched_client)
        try:
            out = RealAdapter().fetch_insurances("p01")
        finally:
            get_settings.cache_clear()

        assert len(out) == 1  # 자동차보험은 스코프 밖 → 제외
        rec = out[0]
        assert rec["insurer_id"] == "meritz"
        assert rec["policy_no"] == "SIL-1"
        assert rec["generation"] == 2  # 2015-03 체결 → 2세대
        assert rec["valid_from"] == "2015-03-01"
