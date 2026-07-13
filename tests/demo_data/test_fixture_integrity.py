"""데모 사용자 데이터 3테이블 조인 무결성 테스트지 (Sprint 36 데이터 트랙).

personas / mydata / health 는 external_id 를 FK 로 하는 1:N 조인 구조다.
지금까지 이 정합이 '우연히' 맞았을 뿐 검증이 없었다 — 본 스위트가 상시 강제한다.
검증 규칙은 fixture_checks.py 에 분리 (negative 테스트에서 재사용).
"""

from __future__ import annotations

from datetime import date

from tests.demo_data import fixture_checks as fc


class TestJoinIntegrity:
    """세 테이블의 키 정합 — 조인 결손·고아 키 0."""

    def test_all_tables_join_clean(self):
        personas, mydata, health = fc.load_tables()
        assert fc.check_join_integrity(personas, mydata, health) == []

    def test_orphan_key_detected(self):
        personas, mydata, health = fc.load_tables()
        mydata = dict(mydata)
        mydata["p99"] = []  # 고아 키 주입
        errs = fc.check_join_integrity(personas, mydata, health)
        assert any("고아 키 p99" in e for e in errs)

    def test_missing_row_detected(self):
        personas, mydata, health = fc.load_tables()
        health = {k: v for k, v in health.items() if k != "p01"}  # 조인 결손 주입
        errs = fc.check_join_integrity(personas, mydata, health)
        assert any("health 에 p01 없음" in e for e in errs)

    def test_fk_mismatch_detected(self):
        personas, mydata, health = fc.load_tables()
        health = {**health, "p01": {**health["p01"], "user_external_id": "p02"}}
        errs = fc.check_join_integrity(personas, mydata, health)
        assert any("user_external_id 불일치" in e for e in errs)


class TestPersonaTable:
    def test_personas_valid(self):
        personas, _, _ = fc.load_tables()
        assert fc.check_personas(personas) == []

    def test_duplicate_name_phone_detected(self):
        personas, _, _ = fc.load_tables()
        dup = dict(personas[0])
        dup["external_id"] = "p98"
        errs = fc.check_personas([*personas, dup])
        assert any("복합키 중복" in e for e in errs)

    def test_same_name_different_phone_allowed(self):
        """동명이인(김민서 p01/p16)은 전화가 다르면 허용 — 복합키 설계 검증."""
        personas, _, _ = fc.load_tables()
        kims = [x for x in personas if x["name"] == "김민서"]
        assert len(kims) == 2
        assert len({x["phone"] for x in kims}) == 2

    def test_bad_phone_detected(self):
        errs = fc.check_personas([
            {"external_id": "px", "name": "홍길동", "phone": "01012345678", "dob": "1990.01.01"}
        ])
        assert any("전화 형식 위반" in e for e in errs)


class TestInsuranceTable:
    def test_insurances_valid(self):
        _, mydata, _ = fc.load_tables()
        assert fc.check_insurances(mydata) == []

    def test_generation_cross_check_detected(self):
        """세대 ↔ 가입일 모순 주입 — derive_generation 교차검증이 잡는지."""
        errs = fc.check_insurances({"px": [{
            "insurer_id": "samsung", "insurer_name": "삼성화재",
            "product_id": "samsung_silson", "product_name": "실손의료보험",
            "policy_no": "X-1", "area": "accident_disease",
            "valid_from": "2024-01-01", "valid_to": None, "generation": 2,  # 2024 가입인데 2세대?
        }]})
        assert any("generation 2 ≠ 가입일 기준 4" in e for e in errs)

    def test_valid_to_before_from_detected(self):
        errs = fc.check_insurances({"px": [{
            "insurer_id": "samsung", "insurer_name": "삼성화재",
            "product_id": "samsung_silson", "product_name": "실손의료보험",
            "policy_no": "X-2", "area": "accident_disease",
            "valid_from": "2024-01-01", "valid_to": "2023-01-01", "generation": 4,
        }]})
        assert any("valid_to < valid_from" in e for e in errs)

    def test_duplicate_policy_no_detected(self):
        _, mydata, _ = fc.load_tables()
        first = next(rows[0] for rows in mydata.values() if rows)
        errs = fc.check_insurances({"a": [dict(first)], "b": [dict(first, insurer_id=first["insurer_id"])]})
        assert any("policy_no 전역 중복" in e for e in errs)


class TestTreatmentTable:
    def test_treatments_valid(self):
        _, _, health = fc.load_tables()
        assert fc.check_treatments(health) == []

    def test_future_date_detected(self):
        errs = fc.check_treatments({"px": {"user_external_id": "px", "treatments": [{
            "treatment_id": "T-X", "treatment_date": "2027-01-01",
            "treatment_period": "2027-01-01 ~ 2027-01-01", "hospital_name": "미래병원",
            "hospital_code": "11110000", "department": "내과",
            "diagnosis_codes": ["J20.9"], "diagnosis_names": ["기관지염"],
            "is_hospitalization": False, "hospitalization_days": 0,
            "outpatient_visits": 1, "total_cost": 10000, "patient_paid": 5000,
        }]}}, today=date(2026, 7, 13))
        assert any("미래 진료일" in e for e in errs)

    def test_paid_exceeds_total_detected(self):
        errs = fc.check_treatments({"px": {"user_external_id": "px", "treatments": [{
            "treatment_id": "T-Y", "treatment_date": "2026-01-01",
            "treatment_period": "2026-01-01 ~ 2026-01-01", "hospital_name": "테스트병원",
            "hospital_code": "11110000", "department": "내과",
            "diagnosis_codes": ["J20.9"], "diagnosis_names": ["기관지염"],
            "is_hospitalization": False, "hospitalization_days": 0,
            "outpatient_visits": 1, "total_cost": 10000, "patient_paid": 99999,
        }]}}, today=date(2026, 7, 13))
        assert any("patient_paid > total_cost" in e for e in errs)

    def test_hospitalization_flag_mismatch_detected(self):
        errs = fc.check_treatments({"px": {"user_external_id": "px", "treatments": [{
            "treatment_id": "T-Z", "treatment_date": "2026-01-01",
            "treatment_period": "2026-01-01 ~ 2026-01-01", "hospital_name": "테스트병원",
            "hospital_code": "11110000", "department": "내과",
            "diagnosis_codes": ["J20.9"], "diagnosis_names": ["기관지염"],
            "is_hospitalization": True, "hospitalization_days": 0,  # 모순
            "outpatient_visits": 1, "total_cost": 10000, "patient_paid": 5000,
        }]}}, today=date(2026, 7, 13))
        assert any("모순" in e for e in errs)

    def test_bad_kcd_code_detected(self):
        errs = fc.check_treatments({"px": {"user_external_id": "px", "treatments": [{
            "treatment_id": "T-W", "treatment_date": "2026-01-01",
            "treatment_period": "2026-01-01 ~ 2026-01-01", "hospital_name": "테스트병원",
            "hospital_code": "11110000", "department": "내과",
            "diagnosis_codes": ["감기"], "diagnosis_names": ["감기"],
            "is_hospitalization": False, "hospitalization_days": 0,
            "outpatient_visits": 1, "total_cost": 10000, "patient_paid": 5000,
        }]}}, today=date(2026, 7, 13))
        assert any("KCD 코드 형식 위반" in e for e in errs)


class TestBoundaryPersonaMatrix:
    """경계 페르소나 5종이 의도한 데이터 상태를 정확히 갖는지 (테스트지 자체 검증)."""

    def test_p12_insurance_without_records(self):
        _, mydata, health = fc.load_tables()
        assert len(mydata["p12"]) == 1
        assert health["p12"]["treatments"] == []

    def test_p13_expired_policy_with_post_expiry_treatment(self):
        _, mydata, health = fc.load_tables()
        ins = mydata["p13"][0]
        t = health["p13"]["treatments"][0]
        assert ins["valid_to"] is not None
        assert t["treatment_date"] > ins["valid_to"], "진료일이 만기 이후여야 함"

    def test_p14_treatment_before_enrollment(self):
        _, mydata, health = fc.load_tables()
        ins = mydata["p14"][0]
        t = health["p14"]["treatments"][0]
        assert t["treatment_date"] < ins["valid_from"], "진료일이 가입 이전이어야 함"

    def test_p15_records_without_insurance(self):
        _, mydata, health = fc.load_tables()
        assert mydata["p15"] == []
        assert len(health["p15"]["treatments"]) == 2

    def test_p11_nothing(self):
        _, mydata, health = fc.load_tables()
        assert mydata["p11"] == []
        assert health["p11"]["treatments"] == []


class TestBoundaryAdapterBehavior:
    """경계 페르소나에 대한 어댑터·매칭 동작 (조인 소비자 검증)."""

    def test_p12_adapter_returns_insurance_but_no_treatments(self):
        from app.infrastructure.external.health_data.adapter import get_health_data_adapter
        from app.infrastructure.external.mydata.adapter import get_mydata_adapter

        assert len(get_mydata_adapter().fetch_insurances("p12")) == 1
        treatments = get_health_data_adapter().fetch_treatments("p12")
        assert treatments == []

    def test_p15_adapter_returns_treatments_but_no_insurance(self):
        from app.infrastructure.external.health_data.adapter import get_health_data_adapter
        from app.infrastructure.external.mydata.adapter import get_mydata_adapter

        assert get_mydata_adapter().fetch_insurances("p15") == []
        assert len(get_health_data_adapter().fetch_treatments("p15")) == 2

    def test_homonym_login_resolves_by_phone(self, monkeypatch):
        """동명이인 김민서 — 이름+전화 복합키로 서로 다른 external_id 매칭."""
        from app.domains.auth import personas as pe

        regs = {(x["name"], x["phone"]): x["external_id"] for x in pe.list_personas()}
        assert regs[("김민서", "010-1234-5678")] == "p01"
        assert regs[("김민서", "010-6666-7777")] == "p16"
