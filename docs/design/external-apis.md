# 외부 API 명세 (Sprint 9~10)

- 작성일: 2026-05-25
- 관련: [REQ-08](../requirements/08_public_service_transition.md), [tech-decisions § Sprint 8~11 추가 결정](tech-decisions.md), [agent-architecture.md](agent-architecture.md)

## 0. 한눈에

| # | API | 가용성 | 통합 우선순위 | 통합 방식 | 캐싱 TTL | 관련 tool |
|:--|:--|:--|:--|:--|:--|:--|
| 1 | **법령정보센터 (law.go.kr) OpenAPI** | ✅ 정식 OpenAPI | Sprint 9 P0 | `httpx` GET | 30일 | `lookup_law_clause` |
| 2 | **KCD 진단코드** (건강보험심사평가원, 공공데이터포털) | ✅ 정식 OpenAPI | Sprint 9 P1 | `httpx` GET (data.go.kr) | 7일 | `get_disease_code` |
| 3 | **손해보험협회 과실비율 인정기준** | ❌ 공식 API 없음 → 정적 데이터 적재 | Sprint 9 P2 | `accident.knia.or.kr` 자료실 → 자체 JSON 적재 | 영구 정적 (분기 갱신) | `get_fault_ratio_standard` |
| 4 | **금감원 공시 — 보험상품 약관 PDF** | ⚠ 전용 API 없음 → 각 보험사 공시실 크롤링 | Sprint 10 P3 | HTML scraping (`httpx` + `selectolax`) | 24시간 | `get_product_meta` |

→ 1·2 는 즉시 통합 가능. 3 은 정적 데이터셋 자체 적재 (가장 안정적). 4 는 가장 까다로움 (각 보험사 공시실 구조 다름) — Sprint 10 으로 분리.

---

## 1. 국가법령정보센터 OpenAPI ✅

- 사이트: https://open.law.go.kr/LSO/openApi/guideList.do
- 등록: 회원가입 → OC (organization code) = 로그인 이메일 ID 사용
- 승인: 신청 후 1~2 영업일 (서비스별로 별도 신청 필요 — 예: "법령 본문 조회" 따로, "법령 목록" 따로)
- 무료 / 일일 한도: **개발 계정 10,000 호출/일** (운영 계정은 활용 사례 등록 후 증액 가능)

### 1.1 우리가 쓸 endpoint

| endpoint | 용도 | 주요 파라미터 |
|:--|:--|:--|
| `lawSearch.do` | 법령명 키워드 검색 (예: "보험업법") | `query`, `display`, `OC` |
| `lawService.do` | 법령 본문 조회 (조항 단위) | `ID`, `JO`, `LM`, `OC` |
| `expcListGuide` | 법령 해석례 목록 (분쟁 시) | `query`, `OC` |

### 1.2 응답 형식

XML 기본, JSON 옵션 (`type=JSON`). 우리는 JSON 사용.

### 1.3 사용 예시 (보험업법 § 4 조회)

```python
import httpx
r = httpx.get(
    "https://www.law.go.kr/DRF/lawService.do",
    params={"OC": "<EMAIL_ID>", "target": "law", "LM": "보험업법", "JO": "000400", "type": "JSON"},
    timeout=5.0,
)
data = r.json()
# data["법령"]["조문"]["조문단위"][i]["조문내용"] 등에서 본문 추출
```

### 1.4 우리 어댑터 설계 (`app/external/law/`)

```
app/external/law/
├── __init__.py
├── client.py     ← httpx wrapper (OC env, timeout, retry, circuit breaker)
├── schemas.py    ← LawClause pydantic (law_name, article_no, sub_no, text, url)
├── service.py    ← lookup_clause(keyword) / fetch_article(law_name, article_no)
└── cache.py      ← cachetools 30d
```

### 1.5 LLM tool 정의 (`lookup_law_clause`)

```json
{
  "type": "function",
  "function": {
    "name": "lookup_law_clause",
    "description": "보험업법·상법 등 법령 조항을 검색해 본문과 출처 URL 을 반환한다. 약관에 명시되지 않은 법적 권리 안내 시 호출.",
    "parameters": {
      "type": "object",
      "properties": {
        "law_name": {"type": "string", "description": "법령명 (예: 보험업법, 상법, 자동차손해배상보장법)"},
        "keyword_or_article": {"type": "string", "description": "검색 키워드 또는 조항 번호 (예: '계약 해지' 또는 '제4조')"}
      },
      "required": ["law_name", "keyword_or_article"]
    }
  }
}
```

### 1.6 장애 대응

- 5xx 또는 timeout → circuit open 60초 → tool 결과 null + LLM 에 "법령 조회 일시 불가" 알림. assessment 는 계속 (약관만으로)
- 4xx (잘못된 OC) → 환경설정 오류 — 운영자 알림 + 503

---

## 2. KCD 진단코드 — 공공데이터포털 ✅

- 사이트: https://www.data.go.kr/data/15119055/openapi.do — **건강보험심사평가원_질병정보서비스**
- 등록: 공공데이터포털 회원가입 → 활용신청 (자동승인 또는 1일 내)
- 무료. 일일 호출 한도 (개발 1,000 / 운영 신청 시 증액)

### 2.1 사용 시나리오

- 사용자: "어제 발목 골절로 입원했어요"
- extract_slots → diagnosis = "발목 골절"
- `get_disease_code(diagnosis="발목 골절")` → KCD-8 코드 "S82.x" + 정식명 "발목뼈의 골절"
- → assessment 시 정확한 진단명 매칭 + 보장 여부 검증

### 2.2 응답 형식

JSON / XML 모두 지원 — JSON 사용. `serviceKey` (활용신청 후 발급) 필수.

### 2.3 어댑터 설계 (`app/external/hira/`)

```
app/external/hira/
├── __init__.py
├── client.py     ← httpx + serviceKey
├── schemas.py    ← DiseaseCode pydantic (kcd_code, official_name, category)
├── service.py    ← lookup_by_name(query)
└── cache.py      ← cachetools 7d
```

### 2.4 LLM tool 정의 (`get_disease_code`)

```json
{
  "type": "function",
  "function": {
    "name": "get_disease_code",
    "description": "한국어 진단명을 KCD-8 코드로 변환. accident_disease 영역에서 정확한 진단 분류 시 호출.",
    "parameters": {
      "type": "object",
      "properties": {
        "diagnosis_korean": {"type": "string", "description": "사용자가 입력한 진단명 (예: '발목 골절')"}
      },
      "required": ["diagnosis_korean"]
    }
  }
}
```

### 2.5 장애 대응

- 공공데이터포털 API 는 5xx 가능. circuit breaker + tool 결과 null. assessment 는 진단명을 평문 그대로 인용

---

## 3. 손해보험협회 과실비율 인정기준 ❌ (공식 API 없음)

- 사이트: https://accident.knia.or.kr — 자동차사고 과실비율 분쟁심의위원회
- **공식 OpenAPI 없음**. 모바일 앱 + 웹 페이지만 제공
- 인정기준은 **금감원 시행세칙 별표 15** (자동차보험표준약관 별표 3) 가 법적 근거 — 정적 데이터셋

### 3.1 대안 — 정적 JSON 자체 적재

손보협회 자료실에서 인정기준 PDF/도표 다운로드 → 도표를 JSON 화 → 우리 repo 에 저장.

```
data/static/fault_ratio/
├── 2024_v1.json     ← {chart_no: 1, scenario: "교차로 직진 동시 진입", base_ratio: [40, 60], modifiers: [...]}
├── 2024_v2.json
└── manifest.json    ← 갱신 일시 + 출처 + 버전
```

분기/연 단위 갱신. PM 이 직접 작업 또는 doc-writer 위임.

### 3.2 어댑터 설계 (`app/external/kidi/`)

```
app/external/kidi/
├── __init__.py
├── schemas.py    ← FaultRatioStandard pydantic
├── service.py    ← lookup_by_scenario(scenario_keyword)
└── data/         ← 위 정적 JSON 의 심볼릭 또는 import
```

### 3.3 LLM tool 정의 (`get_fault_ratio_standard`)

```json
{
  "type": "function",
  "function": {
    "name": "get_fault_ratio_standard",
    "description": "자동차 사고 표준 과실비율을 손보협회 인정기준 도표에서 찾아 반환한다. auto 영역의 사고 유형이 명확할 때 호출.",
    "parameters": {
      "type": "object",
      "properties": {
        "scenario_keyword": {"type": "string", "description": "사고 유형 키워드 (예: '교차로 직진 동시 진입', '주차장 후진 추돌')"}
      },
      "required": ["scenario_keyword"]
    }
  }
}
```

### 3.4 장애 대응

- 정적 데이터라 장애 없음. 매칭 실패 시 null 반환 → LLM 이 약관 인용으로 폴백

### 3.5 갱신 정책

- 분기마다 손보협회 자료실 확인 (PM 운영 task)
- 큰 개정 시 (예: 2023.6 같은 전면 개정) → 별도 sprint task 화

---

## 4. 금감원 공시 — 보험상품 약관 PDF ⚠ (전용 API 없음, 크롤링)

- **OpenDART** (opendart.fss.or.kr) 는 정기보고서/감사보고서 위주. 보험 약관 전용 X
- 보험상품 약관은 **각 보험사 홈페이지 공시실** 에서 제공 (각 보험사마다 URL/구조 다름)
- 금감원 표준약관: https://www.fss.or.kr/fss/bbs/B0000115/list.do (FSS 사이트) — HTML 페이지

### 4.1 대안 — 보험사별 어댑터 패턴

```
app/external/fss/
├── __init__.py
├── client.py            ← httpx + selectolax (HTML scraping)
├── schemas.py           ← ProductMeta (insurer, product_name, version, terms_pdf_url)
├── adapters/
│   ├── hanwha.py        ← 한화손해보험 공시실 어댑터
│   ├── samsung.py       ← 삼성화재 공시실 어댑터
│   ├── kb.py            ← KB손해보험
│   └── ...
├── service.py           ← get_product_meta(insurer, product_name)
└── cache.py             ← cachetools 24h
```

### 4.2 LLM tool 정의 (`get_product_meta`)

```json
{
  "type": "function",
  "function": {
    "name": "get_product_meta",
    "description": "보험사·상품명을 받아 공시실에서 최신 약관 메타 + PDF URL 을 조회. extract_slots 가 잡은 product 가 우리 인덱스에 없을 때 호출 (자동 ingest 후보).",
    "parameters": {
      "type": "object",
      "properties": {
        "insurer": {"type": "string", "description": "보험사명 (예: '한화손해보험')"},
        "product_name": {"type": "string", "description": "상품명 (예: '운전자보험')"}
      },
      "required": ["insurer", "product_name"]
    }
  }
}
```

### 4.3 장애 대응

- 각 보험사 사이트 구조 변경 시 어댑터 깨질 수 있음 → 회귀 테스트 별도 (eval/external/) + 어댑터별 timeout 5s
- 401/403 (robots.txt 변경) → 어댑터 disable + 알림

### 4.4 합법성 / robots.txt

- 각 보험사 robots.txt 확인 필수 (대국민 서비스이므로 법적 risk)
- 크롤링 대신 PR 협업 옵션 검토 (보험사가 직접 API 제공) — Sprint 12+
- **[확인 필요]** 법무 검토: 보험사 공시실 크롤링이 약관규제법·저작권법에 저촉되지 않는지

### 4.5 우선 적재 보험사 (PoC → 운영 확장)

- Sprint 10: hanwha (이미 적재됨), samsung 2개만 어댑터 작성
- Sprint 11+: KB / 현대해상 / DB / 흥국 등 점진 확장

---

## 5. 공통 정책

### 5.1 환경 변수

```
LAW_GO_KR_OC=<email_id>
DATA_GO_KR_SERVICE_KEY=<key>
EXTERNAL_API_TIMEOUT_S=5
EXTERNAL_API_RETRY=2
EXTERNAL_API_CIRCUIT_THRESHOLD=5    # 연속 실패 5회면 open
EXTERNAL_API_CIRCUIT_RESET_S=60     # 60초 후 half-open
```

### 5.2 캐싱 (1단계 cachetools 인메모리)

| API | Cache | TTL | maxsize |
|:--|:--|:--|:--|
| law | TTLCache | 30d | 10000 |
| hira | TTLCache | 7d | 5000 |
| kidi | 정적 dict | 영구 | — |
| fss | TTLCache | 24h | 1000 |

Sprint 10+ Redis 마이그 검토.

### 5.3 circuit breaker (공통)

`pybreaker` 또는 자체 구현. 5회 연속 실패 → 60초 open → half-open 1회 → 성공 시 close.

### 5.4 감사 로그 (audit_log 의 external_api_calls JSONB)

```json
[
  {"api": "law.go.kr", "endpoint": "lawService.do", "cached": false, "latency_ms": 234, "status": 200},
  {"api": "data.go.kr/hira", "endpoint": "diseaseInfoService", "cached": true, "latency_ms": 0, "status": 200}
]
```

→ 분쟁 시 어떤 외부 데이터를 인용했는지 100% 재현 가능.

### 5.5 SLO

- 외부 API 호출 자체로는 API 응답시간이 우리 SLO 에 잡힘 (p95 < 5s)
- 외부 API 다운 → circuit open → tool 결과 null → assessment 계속 (약관만으로) — 사용자 체감 가용성 무영향

---

## 6. Sprint 9 / 10 일정 매핑

| Sprint | 통합 대상 | 작업 |
|:--|:--|:--|
| 9 | law (P0) + hira (P1) + kidi 정적 (P2) | 3 어댑터 + LLM tool 정의 3 + 캐싱 + circuit breaker + rule-based 호출 (Sprint 11 까지는 LLM 미선택) |
| 10 | calc 2개 + fss 크롤링 (P3) | calc_claim_amount + validate_coverage_period (deterministic) + fss 어댑터 (hanwha + samsung 2개) |

---

## 7. [확인 필요] 항목

1. **법령정보센터 OC 발급** — 운영자가 회원가입 + 신청 (1~2일 소요)
2. **공공데이터포털 serviceKey 발급** — 운영자
3. **손보협회 인정기준 PDF 적재** — 누가 도표를 JSON 화? PM 직접 vs doc-writer 위임
4. **공시실 크롤링 법무 검토** — 보험사 robots.txt + 약관규제법 저촉 여부
5. **Redis 도입 시점** — Sprint 10 또는 11

---

## Sources

- [국가법령정보 공동활용 OPEN API 활용가이드](https://open.law.go.kr/LSO/openApi/guideList.do)
- [법제처 국가법령정보 공유서비스 | 공공데이터포털](https://www.data.go.kr/data/15000115/openapi.do)
- [건강보험심사평가원_질병정보서비스 | 공공데이터포털](https://www.data.go.kr/data/15119055/openapi.do)
- [질병분류정보센터 KOICD](https://www.koicd.kr/)
- [자동차사고 과실비율 분쟁심의위원회](https://accident.knia.or.kr/)
- [손해보험협회 과실비율 인정기준 도표](https://www.knia.or.kr/file-manager/101524)
- [금융감독원 보험약관 표준약관](https://www.fss.or.kr/fss/bbs/B0000115/list.do)
- [OPEN DART 시스템](https://opendart.fss.or.kr/intro/main.do)
