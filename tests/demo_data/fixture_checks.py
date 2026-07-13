"""데모 사용자 데이터 3테이블(personas/mydata/health) 조인 무결성 검증 헬퍼.

구조 (external_id 가 FK 인 1:N 조인):
    personas.json  — 사용자 (external_id PK, 이름+전화 복합 유니크)
    mydata.json    — 가입 보험  { external_id: [InsuranceDict, ...] }
    health.json    — 진료 기록  { external_id: {user_external_id, treatments:[...]} }

검증 함수를 분리해 둔 이유: fixture 상시 검사(pytest) + 의도적으로 깨진 레코드가
잡히는지 negative 테스트 양쪽에서 재사용.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo"

_INSURANCE_REQUIRED = {
    "insurer_id", "insurer_name", "product_id", "product_name",
    "policy_no", "area", "valid_from", "valid_to", "generation",
}
_TREATMENT_REQUIRED = {
    "treatment_id", "treatment_date", "treatment_period", "hospital_name",
    "hospital_code", "department", "diagnosis_codes", "diagnosis_names",
    "is_hospitalization", "hospitalization_days", "outpatient_visits",
    "total_cost", "patient_paid",
}
_KNOWN_INSURERS = {"samsung", "hyundai", "meritz", "lotte", "hanwha"}
_PHONE_RE = re.compile(r"^010-\d{4}-\d{4}$")
_HOSPITAL_CODE_RE = re.compile(r"^\d{8}$")
_KCD_RE = re.compile(r"^[A-Z]\d{2}(\.\d+)?$")


def load_tables() -> tuple[list[dict], dict[str, list[dict]], dict[str, dict]]:
    personas = json.loads((DEMO_DIR / "personas.json").read_text(encoding="utf-8"))
    mydata = json.loads((DEMO_DIR / "mydata.json").read_text(encoding="utf-8"))
    health = json.loads((DEMO_DIR / "health.json").read_text(encoding="utf-8"))
    return personas, mydata, health


def _iso(d: str) -> date:
    return date.fromisoformat(d)


def check_join_integrity(personas, mydata, health) -> list[str]:
    """세 테이블의 키 정합 — 모든 페르소나에 보험·기록 row 존재(빈 리스트 허용), 고아 키 금지."""
    errors: list[str] = []
    pids = [x["external_id"] for x in personas]
    pset = set(pids)
    if len(pids) != len(pset):
        errors.append("personas.external_id 중복")
    for missing in pset - set(mydata):
        errors.append(f"mydata 에 {missing} 없음 (조인 결손)")
    for orphan in set(mydata) - pset:
        errors.append(f"mydata 고아 키 {orphan}")
    for missing in pset - set(health):
        errors.append(f"health 에 {missing} 없음 (조인 결손)")
    for orphan in set(health) - pset:
        errors.append(f"health 고아 키 {orphan}")
    for eid, rec in health.items():
        if not isinstance(rec, dict):
            errors.append(f"health[{eid}] 형태 위반: dict 여야 함 (실제 {type(rec).__name__})")
            continue
        if rec.get("user_external_id") != eid:
            errors.append(f"health[{eid}].user_external_id 불일치: {rec.get('user_external_id')}")
    return errors


def check_personas(personas) -> list[str]:
    errors: list[str] = []
    seen_namephone: set[tuple[str, str]] = set()
    for x in personas:
        key = (x.get("name", ""), x.get("phone", ""))
        if key in seen_namephone:
            errors.append(f"이름+전화 복합키 중복: {key}")
        seen_namephone.add(key)
        if not _PHONE_RE.match(x.get("phone", "")):
            errors.append(f"{x.get('external_id')}: 전화 형식 위반 {x.get('phone')}")
        if not re.match(r"^\d{4}\.\d{2}\.\d{2}$", x.get("dob", "")):
            errors.append(f"{x.get('external_id')}: dob 형식 위반 {x.get('dob')}")
    return errors


def check_insurances(mydata) -> list[str]:
    """보험 행 스키마·날짜·세대 교차 검증 (derive_generation 재사용)."""
    from app.infrastructure.external.mydata.adapter import derive_generation

    errors: list[str] = []
    policy_nos: set[str] = set()
    for eid, rows in mydata.items():
        for r in rows:
            miss = _INSURANCE_REQUIRED - set(r)
            if miss:
                errors.append(f"{eid}/{r.get('policy_no')}: 필드 누락 {sorted(miss)}")
                continue
            if r["policy_no"] in policy_nos:
                errors.append(f"policy_no 전역 중복: {r['policy_no']}")
            policy_nos.add(r["policy_no"])
            if r["insurer_id"] not in _KNOWN_INSURERS:
                errors.append(f"{eid}/{r['policy_no']}: 미지 보험사 {r['insurer_id']}")
            if r["area"] != "accident_disease":
                errors.append(f"{eid}/{r['policy_no']}: area 위반 {r['area']}")
            try:
                vf = _iso(r["valid_from"])
            except (ValueError, TypeError):
                errors.append(f"{eid}/{r['policy_no']}: valid_from 파싱 불가 {r['valid_from']}")
                continue
            if r["valid_to"] is not None:
                try:
                    vt = _iso(r["valid_to"])
                    if vt < vf:
                        errors.append(f"{eid}/{r['policy_no']}: valid_to < valid_from")
                except (ValueError, TypeError):
                    errors.append(f"{eid}/{r['policy_no']}: valid_to 파싱 불가 {r['valid_to']}")
            gen = r["generation"]
            if gen is not None:
                if gen not in (1, 2, 3, 4):
                    errors.append(f"{eid}/{r['policy_no']}: generation 범위 위반 {gen}")
                # 세대 ↔ 가입일 교차 검증 — 표준 API normalizer 와 동일 규칙
                expected = derive_generation(r["valid_from"])
                if expected is not None and expected != gen:
                    errors.append(
                        f"{eid}/{r['policy_no']}: generation {gen} ≠ 가입일 기준 {expected}"
                    )
    return errors


def check_treatments(health, today: date | None = None) -> list[str]:
    errors: list[str] = []
    today = today or date(2026, 7, 13)
    tids: set[str] = set()
    for eid, rec in health.items():
        if not isinstance(rec, dict):
            errors.append(f"{eid}: health 레코드 형태 위반 (dict 아님)")
            continue
        for t in rec.get("treatments", []):
            miss = _TREATMENT_REQUIRED - set(t)
            if miss:
                errors.append(f"{eid}/{t.get('treatment_id')}: 필드 누락 {sorted(miss)}")
                continue
            if t["treatment_id"] in tids:
                errors.append(f"treatment_id 전역 중복: {t['treatment_id']}")
            tids.add(t["treatment_id"])
            try:
                td = _iso(t["treatment_date"])
            except (ValueError, TypeError):
                errors.append(f"{eid}/{t['treatment_id']}: treatment_date 파싱 불가")
                continue
            if td > today:
                errors.append(f"{eid}/{t['treatment_id']}: 미래 진료일 {t['treatment_date']}")
            if not str(t["treatment_period"]).startswith(t["treatment_date"]):
                errors.append(f"{eid}/{t['treatment_id']}: period 시작일 ≠ 진료일")
            if not _HOSPITAL_CODE_RE.match(str(t["hospital_code"])):
                errors.append(f"{eid}/{t['treatment_id']}: hospital_code 형식 위반 {t['hospital_code']}")
            for code in t["diagnosis_codes"]:
                if not _KCD_RE.match(code):
                    errors.append(f"{eid}/{t['treatment_id']}: KCD 코드 형식 위반 {code}")
            if t["patient_paid"] > t["total_cost"]:
                errors.append(f"{eid}/{t['treatment_id']}: patient_paid > total_cost")
            if t["patient_paid"] < 0 or t["total_cost"] < 0:
                errors.append(f"{eid}/{t['treatment_id']}: 음수 금액")
            if t["is_hospitalization"] != (t["hospitalization_days"] > 0):
                errors.append(f"{eid}/{t['treatment_id']}: is_hospitalization ↔ 일수 모순")
    return errors


def check_all() -> list[str]:
    personas, mydata, health = load_tables()
    return (
        check_join_integrity(personas, mydata, health)
        + check_personas(personas)
        + check_insurances(mydata)
        + check_treatments(health)
    )
