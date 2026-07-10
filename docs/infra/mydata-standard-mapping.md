# 마이데이터 표준 API 정합 — 매핑 명세 (Sprint 35)

> **핵심 주장(심사 방어)**: 우리는 금융 마이데이터 **표준 API 규격을 따르는 정규화 계층을 이미 구현**했다.
> 현재는 마이데이터사업자 승인을 받지 못해 실 API 를 직접 호출하지 못할 뿐이며,
> **승인 후 `.env` 의 주소·토큰 2개만 설정하면**(코드 무변경) RealAdapter 가 표준 규격 응답을
> 받아 더미와 동일한 내부 스키마로 반환한다 — 호출부(가입현황·seed·판정)는 전혀 손대지 않는다.

## 1. 규격 출처

- 금융보안원 **마이데이터 테스트베드** — [보험 업권 정보제공 API 규격](https://developers.mydatakorea.org/mdtb/apg/mac/bas/FSAG0403?id=3)
- 사용 API 2종:

| API | 메서드·경로 | 사용 응답 필드 |
|:--|:--|:--|
| 보험 목록 조회 | `GET /v2/insu/insurances` | `insu_num`(증권번호) · `prod_name`(상품명) · `insu_type`(보험종류) · `insu_status`(계약상태: 02 정상/04 실효/05 만기/06 소멸) |
| 보험 기본정보 조회 | `POST /v2/insu/insurances/basic` | `issue_date`(계약체결일) · `exp_date`(만기일) |

## 2. 필드 매핑표 (표준 → 내부 `InsuranceDict`)

구현: `app/infrastructure/external/mydata/adapter.py` `normalize_standard_insurance()`

| 표준 필드 | 내부 필드 | 변환 규칙 |
|:--|:--|:--|
| `insu_num` | `policy_no` | 그대로 |
| `prod_name` | `product_name` | 실손 스코프 확인 후 `"실손의료보험"` 표준화 |
| `org_code` (또는 `prod_name` 폴백) | `insurer_id` / `insurer_name` | 기관코드 매핑표(`_ORG_CODE_TO_INSURER`) → 미등록 시 상품명 내 보험사명 패턴 매칭 |
| — (파생) | `product_id` | `{insurer_id}_silson` (약관 인덱스 폴더 규약) |
| `issue_date` (YYYYMMDD) | `valid_from` | ISO 변환 |
| `exp_date` | `valid_to` | ISO 변환, `9999*`(무기한 관행) → null |
| `issue_date` (파생) | **`generation`** | **세대 파생 규칙** (아래 §3) — 표준 API 에 없는 값 |
| `insu_status` | — (필터) | `02`(정상)만 통과 — 실효/만기/소멸 제외 |
| `insu_type`/`prod_name` | — (필터) | 실손만 통과 (자동차 등 스코프 밖 제외, ADR-006) |

## 3. 실손 세대 파생 규칙 (`derive_generation`)

표준 API 는 "실손 몇 세대"를 직접 주지 않는다. 실손은 **판매시기로 세대가 확정**되므로 계약체결일로 결정론 파생:

| 계약체결일 | 세대 |
|:--|:--|
| ~ 2009-09-30 | 1세대 (구실손) |
| 2009-10-01 ~ 2017-03-31 | 2세대 (표준화 실손) |
| 2017-04-01 ~ 2021-06-30 | 3세대 (착한실손) |
| 2021-07-01 ~ | 4세대 |

→ 이 값이 다중 실손 비교(세대별 자기부담률)와 coverage 룰 엔진의 핵심 입력.

## 4. 전환 절차 (승인 후 해야 할 일)

1. `.env` 에 3줄:
   ```
   MYDATA_BACKEND=real
   MYDATA_API_BASE_URL=https://<정보제공자 API 도메인>
   MYDATA_API_TOKEN=<전송요구 접근토큰>
   ```
2. `_ORG_CODE_TO_INSURER` 에 종합포털 발급 **기관코드** 5건 기입 (없어도 상품명 폴백으로 동작).
3. 끝 — DummyAdapter 와 동일한 `InsuranceDict` 가 나오므로 가입현황 화면·slot seed·판정·비교 전부 무변경.

## 5. 검증

- `tests/external/test_mydata_standard.py` **15건** — 세대 파생 경계 7 · 표준응답→내부 스키마 정규화 5 · RealAdapter 미설정 예외 + **httpx MockTransport 로 표준 엔드포인트 호출→정규화 왕복** 2 (+헤더 Bearer 검증).
- 더미 경로 회귀 0 (기존 어댑터 테스트 유지).

## 6. 정직한 잔여 항목 (승인 후 확정 필요)

- **기관코드 실값** — 종합포털 발급 후 `_ORG_CODE_TO_INSURER` 갱신 (현재 상품명 폴백으로 커버).
- **인증 세부** — 전송요구 OAuth 토큰 발급/갱신 플로우, `x-api-tran-id` 등 공통 헤더는 승인 후 테스트베드 검증 단계에서 추가 (현재 Bearer 토큰 헤더까지 구현).
- 건강보험(`health_data`) 쪽은 의료 마이데이터(건강정보 고속도로) 규격 확정 시 동일 패턴으로 normalizer 추가 예정 (어댑터 경계 동일).
