# REQ-14: 사용자 건강보험 API 연동 (NHIS/HIRA/의료마이데이터)

- 요청일: 2026-05-26
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 18
- 출처: 사용자 점검 — "사용자 건강보험 API 로 가져오기" + 챔피언 제안서 "공공데이터 API 자동 수집" 의 의료 데이터 트랙

## 요청 원문

> 사용자 건강보험 API 로 가져오기. API 로 가져오는 건 가져온다는 가정하에 진행을 해보자.

## 핵심 목표

로그인 사용자의 **최근 진료 내역**을 외부 API (의료마이데이터 / NHIS / HIRA) 에서 가져와, 청구 가능성 판단의 핵심 슬롯 (병원·진단·진료기간·입원일수·청구금액 등) 을 자동 prefill 한다. 사용자는 사고 경위·과실비율 등 시나리오 정보만 자연어로 입력하면 된다.

API 발급/사업자 인증은 별도 트랙. **응답 받는다는 전제로 처리 흐름·매핑·UI·테스트 전부 더미 어댑터로 선행 구축**한다. 실 어댑터 교체는 env 토글 한 줄.

## 사용자 시나리오

1. 로그인 사용자가 채팅 진입 시 "**최근 진료 내역 가져오기**" 버튼 노출
2. 클릭 → backend `GET /api/v1/auth/me/health-history` → HealthDataAdapter 호출
3. 진료 카드 N개 표시 (날짜·병원·진단·금액)
4. 사용자가 청구할 진료 1건 선택 → SlotState 자동 prefill (병원/진단/진료기간/입원일수/청구금액/area=accident_disease)
5. 보험사·상품·증권번호는 마이데이터(REQ-10) prefill → 거의 자동 완성 → 사고 경위만 채팅 입력

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | 응답 스키마 fixture (의료마이데이터/HIRA 표준 가정) | 필수 | 3 시나리오 (단일 진료/다건 진료/만성질환 다수) | 미시작 |
| F-2 | HealthDataAdapter Protocol + DummyAdapter + RealAdapter skeleton | 필수 | env 토글 HEALTH_DATA_BACKEND=dummy\|real | 미시작 |
| F-3 | `GET /me/health-history` 엔드포인트 (auth Depends) | 필수 | 비로그인 401, 로그인 시 진료 N건 반환 | 미시작 |
| F-4 | 응답 → SlotState 매핑 유틸 | 필수 | 진료 1건 → SlotState 부분 dict | 미시작 |
| F-5 | frontend — 진료 카드 + "이 진료 선택" 버튼 | 권장 | useSession 에 applyHealthRecord(record) 추가 | 미시작 |
| F-6 | 회귀 — 비로그인 흐름 영향 0 | 필수 | 기존 sessions API 변경 0 | 미시작 |
| F-7 | RealAdapter 활성 (실 API key + 사업자 인증 완료 후) | 후순위 | env 한 줄 변경, 인터페이스 동일 | 미시작 |

## 기술 결정

### 응답 스키마 (가정)

한국 의료마이데이터 표준 + HIRA open API 응답 구조 기반. HL7 FHIR R4 와도 호환되도록 필드명 단순화:

```json
{
  "user_external_id": "userid-001",
  "fetched_at": "2026-05-26T12:00:00Z",
  "treatments": [
    {
      "treatment_id": "T-2024-001",
      "treatment_date": "2024-01-15",
      "treatment_period": "2024-01-15 ~ 2024-01-20",
      "hospital_name": "서울대학교병원",
      "hospital_code": "11250001",
      "department": "정형외과",
      "diagnosis_codes": ["S82.5"],
      "diagnosis_names": ["발목 골절"],
      "is_hospitalization": true,
      "hospitalization_days": 5,
      "outpatient_visits": 0,
      "total_cost": 1500000,
      "patient_paid": 200000
    }
  ]
}
```

### 어댑터 분리 (Sprint 14 마이데이터 패턴 그대로 복제)

- `app/external/health_data/adapter.py` — `HealthDataAdapter` Protocol + DummyAdapter (fixture) + RealAdapter skeleton (raise HealthDataNotConfiguredError)
- env 토글 `HEALTH_DATA_BACKEND=dummy|real` (기본 dummy)
- DummyAdapter fixture 경로: `tests/fixtures/health_data/users.json`

### 슬롯 매핑 (claim_amount = patient_paid)

- `patient_paid` 가 실제 환자 부담분 = 청구 가능 금액
- `total_cost` 는 정보 표시용 (UI 카드에 노출, slot 미사용)
- `diagnosis_codes[0]` → `diagnosis_code` (KCD-7 첫 코드)
- `diagnosis_names[0]` → `diagnosis` (첫 진단명, 한국어)
- 다른 필드는 1:1 매핑

### 응답 형식

```json
{
  "treatments": [
    {
      "treatment_id": "T-2024-001",
      "treatment_date": "2024-01-15",
      "hospital_name": "서울대학교병원",
      "diagnosis_summary": "발목 골절",
      "is_hospitalization": true,
      "claim_amount": 200000,
      "_slot_mapping": {
        "hospital": "서울대학교병원",
        "diagnosis": "발목 골절",
        "diagnosis_code": "S82.5",
        "incident_date": "2024-01-15",
        "treatment_period": "2024-01-15 ~ 2024-01-20",
        "hospitalization_days": 5,
        "outpatient_visits": 0,
        "claim_amount": 200000,
        "area": "accident_disease"
      }
    }
  ]
}
```

`_slot_mapping` 은 frontend 가 사용자 선택 시 그대로 `slots` 에 머지하기 위한 사전 계산 결과.

## 의존성

- 외부: 의료마이데이터 사업자 신청 + API key 발급 (사용자 직접 작업, F-7 활성화 조건)
- 내부: Sprint 14 (로그인 + auth.deps) 완성 → user_external_id 기반 호출 가능 ✓
- 내부: Sprint 17 (SlotState 22 필드) 완성 → hospital/diagnosis_code/treatment_period 슬롯 매핑 즉시 가능 ✓

## 리스크

| 리스크 | 영향 | 대응 |
|:--|:--|:--|
| 실제 API 응답이 가정한 스키마와 다름 | 중 | RealAdapter 활성 시 응답 → DummyAdapter 와 동일한 형태로 변환하는 normalizer 1단계 추가 |
| `patient_paid` 의 정의가 보험사마다 다름 | 낮 | mapper 에서 None/0 fallback 명시 |
| 만성질환 진료 다수 시 어떤 1건 선택? | 낮 | UI 가 사용자에게 선택 강제 (자동 선택 X) |

## 비고

- 본 REQ 는 챔피언 제안서 "Data Layer — 공공데이터 API 자동 수집" 의 의료 트랙 후속
- REQ-10 (금융 마이데이터 — 보험 가입 정보) 와 직교. 둘 다 prefill 흐름이지만 출처/스코프 다름.
- Sprint 18 진입 시 PM 분석 문서 (PM-22) 별도 작성
