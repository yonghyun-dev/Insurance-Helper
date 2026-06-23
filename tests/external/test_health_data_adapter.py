"""tests.external.test_health_data_adapter

Sprint 18 — HealthDataAdapter (Dummy + Real skeleton) + mapper 회귀.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.infrastructure.external.health_data import adapter as adapter_mod
from app.infrastructure.external.health_data.adapter import (
    DummyAdapter,
    HealthDataNotConfiguredError,
    RealAdapter,
    TreatmentDict,
)
from app.infrastructure.external.health_data.mapper import treatment_to_card, treatment_to_slot_dict

# ---------------------------------------------------------------------------
# DummyAdapter
# ---------------------------------------------------------------------------


class TestDummyAdapter:
    def test_user1_single_treatment(self):
        a = DummyAdapter()
        ts = a.fetch_treatments("1")
        assert len(ts) == 1
        assert ts[0]["treatment_id"] == "T-2024-001"
        assert ts[0]["hospital_name"] == "서울대학교병원"
        assert ts[0]["diagnosis_names"] == ["발목 골절"]
        assert ts[0]["patient_paid"] == 200000

    def test_user2_multiple_treatments(self):
        a = DummyAdapter()
        ts = a.fetch_treatments("2")
        assert len(ts) == 3
        # 입원/외래 혼합
        in_hospital = [t for t in ts if t["is_hospitalization"]]
        assert len(in_hospital) == 1
        assert in_hospital[0]["diagnosis_names"] == ["급성 충수염"]

    def test_user3_chronic_multiple_diagnosis(self):
        a = DummyAdapter()
        ts = a.fetch_treatments("3")
        assert len(ts) == 2
        # 다중 진단 케이스
        last = ts[-1]
        assert last["diagnosis_codes"] == ["E11.9", "I10"]
        assert last["diagnosis_names"] == ["당뇨병", "본태성 고혈압"]

    def test_unknown_user_returns_empty(self):
        a = DummyAdapter()
        assert a.fetch_treatments("9999") == []

    def test_custom_fixture_path(self, tmp_path: Path):
        custom = tmp_path / "h.json"
        custom.write_text(
            json.dumps({"42": {"user_external_id": "42", "treatments": []}}),
            encoding="utf-8",
        )
        a = DummyAdapter(fixture_path=custom)
        assert a.fetch_treatments("42") == []
        assert a.fetch_treatments("1") == []  # 다른 fixture 격리

    def test_missing_fixture_returns_empty(self, tmp_path: Path):
        nonexistent = tmp_path / "nope.json"
        a = DummyAdapter(fixture_path=nonexistent)
        assert a.fetch_treatments("1") == []


# ---------------------------------------------------------------------------
# RealAdapter
# ---------------------------------------------------------------------------


class TestRealAdapter:
    def test_raises_not_configured(self):
        a = RealAdapter()
        with pytest.raises(HealthDataNotConfiguredError):
            a.fetch_treatments("1")


# ---------------------------------------------------------------------------
# 팩토리
# ---------------------------------------------------------------------------


class TestFactory:
    def test_default_dummy(self, monkeypatch: pytest.MonkeyPatch):
        adapter_mod.clear_cache()
        a = adapter_mod.get_health_data_adapter()
        assert isinstance(a, DummyAdapter)

    def test_real_via_env(self, monkeypatch: pytest.MonkeyPatch):
        from app.infrastructure.core import config

        adapter_mod.clear_cache()
        # Settings 직접 패치 (env 토글 시뮬)
        monkeypatch.setenv("HEALTH_DATA_BACKEND", "real")
        config.get_settings.cache_clear()
        try:
            a = adapter_mod.get_health_data_adapter()
            assert isinstance(a, RealAdapter)
        finally:
            adapter_mod.clear_cache()
            config.get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------


def _sample_treatment() -> TreatmentDict:
    return TreatmentDict(
        treatment_id="T-X",
        treatment_date="2024-01-15",
        treatment_period="2024-01-15 ~ 2024-01-20",
        hospital_name="서울대학교병원",
        hospital_code="11250001",
        department="정형외과",
        diagnosis_codes=["S82.5"],
        diagnosis_names=["발목 골절"],
        is_hospitalization=True,
        hospitalization_days=5,
        outpatient_visits=0,
        total_cost=1500000,
        patient_paid=200000,
    )


class TestMapper:
    def test_slot_dict_maps_core_fields(self):
        d = treatment_to_slot_dict(_sample_treatment())
        assert d["area"] == "accident_disease"
        assert d["hospital"] == "서울대학교병원"
        assert d["diagnosis"] == "발목 골절"
        assert d["diagnosis_code"] == "S82.5"
        assert d["incident_date"] == "2024-01-15"
        assert d["treatment_period"] == "2024-01-15 ~ 2024-01-20"
        assert d["hospitalization_days"] == 5
        assert d["outpatient_visits"] == 0
        assert d["claim_amount"] == 200000  # patient_paid, not total_cost

    def test_slot_dict_skips_empty_diagnosis(self):
        t = _sample_treatment()
        t["diagnosis_codes"] = []
        t["diagnosis_names"] = []
        d = treatment_to_slot_dict(t)
        assert "diagnosis" not in d
        assert "diagnosis_code" not in d
        assert d["hospital"] == "서울대학교병원"

    def test_card_includes_summary_and_slot_mapping(self):
        c = treatment_to_card(_sample_treatment())
        assert c["treatment_id"] == "T-X"
        assert c["diagnosis_summary"] == "발목 골절"
        assert c["claim_amount"] == 200000
        assert c["total_cost"] == 1500000
        assert c["slot_mapping"]["claim_amount"] == 200000
        assert c["slot_mapping"]["area"] == "accident_disease"

    def test_card_multi_diagnosis_joined(self):
        t = _sample_treatment()
        t["diagnosis_names"] = ["당뇨병", "본태성 고혈압"]
        c = treatment_to_card(t)
        assert c["diagnosis_summary"] == "당뇨병, 본태성 고혈압"

    def test_card_empty_diagnosis_fallback(self):
        t = _sample_treatment()
        t["diagnosis_codes"] = []
        t["diagnosis_names"] = []
        c = treatment_to_card(t)
        assert c["diagnosis_summary"] == "진단명 없음"
