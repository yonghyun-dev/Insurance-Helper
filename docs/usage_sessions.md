# 세션 API 사용 가이드

- 작성일: 2026-05-24
- 스프린트: 2 (멀티턴 대화 + RAG 응답 PoC)
- 관련 설계: [api-spec.md](design/api-spec.md), [data-model.md](design/data-model.md)

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 시작하기 전에

이 가이드는 Sprint 2에서 추가된 멀티턴 대화 기능을 사용하는 방법을 설명합니다.

서버를 먼저 실행해야 HTTP API를 사용할 수 있습니다:

```bash
uvicorn app.main:app --reload --port 8000
```

서버가 실행되면 `http://localhost:8000/api/v1` 에서 API를 사용할 수 있습니다.
터미널 대화(`ica chat`)는 서버 없이 바로 사용할 수 있습니다.

---

## 세션이란?

세션(Session)은 사용자와 어시스턴트가 나누는 대화 묶음입니다.

- 세션이 생성되면 고유한 `session_id`(UUID 형태)가 부여됩니다
- 모든 대화는 이 `session_id`를 통해 연결됩니다
- **세션은 메모리에만 저장되며 30분 동안 활동이 없으면 자동으로 사라집니다**
- 서버를 재시작하면 모든 세션이 사라집니다
- 개인정보 보호를 위해 입력 내용은 서버 영구 저장소에 남지 않습니다

---

## HTTP API 사용법

### 1. 세션 생성 — `POST /api/v1/sessions`

새 대화를 시작합니다.

#### 빈 세션 생성 (첫 메시지 없이)

```bash
curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{}'
```

응답 예시:

```json
{
  "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
  "created_at": "2026-05-24T09:00:00Z",
  "ttl_seconds": 1800,
  "first_response": null
}
```

#### 첫 메시지를 함께 보내기 (`initial_message` 포함)

첫 메시지를 함께 보내면 세션 생성과 동시에 첫 응답을 받을 수 있습니다.

```bash
curl -s -X POST http://localhost:8000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"initial_message": "어제 빙판길에서 미끄러져 발목 골절로 입원했어요. 자동차보험으로 보험금 받을 수 있나요?"}'
```

응답 예시 (어시스턴트가 추가 정보를 요청하는 경우):

```json
{
  "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
  "created_at": "2026-05-24T09:00:00Z",
  "ttl_seconds": 1800,
  "first_response": {
    "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
    "turn": 1,
    "assistant": {
      "type": "ask",
      "message": "어떤 보험사의 자동차보험에 가입하셨나요? 예: 한화손해보험, 삼성화재",
      "expected_slots": ["insurer"],
      "options": []
    },
    "slots": {
      "area": "auto",
      "insurer": null,
      "product": null,
      "version": null,
      "incident_date": "2026-05-23",
      "evidence": [],
      "incident_type": null,
      "fault_ratio": null,
      "damage_type": null,
      "loss_type": null,
      "damaged_items": [],
      "cause": null,
      "diagnosis": null,
      "hospitalization_days": null,
      "outpatient_visits": null
    },
    "status": "gathering"
  }
}
```

응답에서 `area: "auto"`가 이미 채워진 것을 볼 수 있습니다. 어시스턴트가 첫 메시지에서 "자동차보험"이라는 단어를 인식해 슬롯을 자동으로 채웠습니다.

---

### 2. 메시지 전송 — `POST /api/v1/sessions/{session_id}/messages`

대화를 이어갑니다. 위에서 받은 `session_id`를 URL에 넣으세요.

#### ask 응답을 받는 경우 (정보 수집 중)

```bash
curl -s -X POST http://localhost:8000/api/v1/sessions/7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c/messages \
  -H "Content-Type: application/json" \
  -d '{"text": "한화손해보험이요. 개인용 자동차보험 가입했어요."}'
```

응답 예시 (`ask` 모드 — 아직 정보 수집 중):

```json
{
  "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
  "turn": 2,
  "assistant": {
    "type": "ask",
    "message": "사고 유형이 어떻게 되나요?",
    "expected_slots": ["incident_type", "damage_type"],
    "options": ["추돌", "단독사고", "대물사고", "대인사고"]
  },
  "slots": {
    "area": "auto",
    "insurer": "한화손해보험",
    "product": "개인용자동차보험",
    "version": null,
    "incident_date": "2026-05-23",
    "evidence": [],
    "incident_type": null,
    "fault_ratio": null,
    "damage_type": null,
    ...
  },
  "status": "gathering"
}
```

#### assessment 응답을 받는 경우 (정보 충족, 최종 판단)

필수 슬롯이 모두 채워지면 어시스턴트가 가능성 판단을 내립니다.

```bash
curl -s -X POST http://localhost:8000/api/v1/sessions/7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c/messages \
  -H "Content-Type: application/json" \
  -d '{"text": "단독사고였고 자차 처리 원해요. 과실은 100% 제 잘못이에요."}'
```

응답 예시 (`assessment` 모드 — 최종 판단):

```json
{
  "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
  "turn": 4,
  "assistant": {
    "type": "assessment",
    "likelihood": "높음",
    "summary": "자차 보장 조건에 부합합니다. 단독사고 자차 처리는 가입 특약 범위 내에서 지급될 가능성이 높습니다.",
    "satisfied": [
      "사고 유형 '단독사고' — 자차 보장 대상",
      "자차 손해 처리 요청 — 해당 특약 가입 확인 필요"
    ],
    "unsatisfied": [
      "자차 특약 가입 여부 미확인 — 보험증권 또는 보험사 앱에서 확인 필요"
    ],
    "citations": [
      {
        "chunk_id": "3f8a1c2e-4b5d-...",
        "insurer": "한화손해보험",
        "product": "개인용자동차보험(공동물건)",
        "version": "2026-03-01_present",
        "doc_type": "terms",
        "clause": "제15조",
        "sub_no": "①",
        "text": "보험금 지급 사유는 다음과 같다 ...",
        "page": 12
      }
    ],
    "next_steps": [
      "보험증권에서 자차 특약(자기차량손해) 가입 여부 확인",
      "사고 현장 사진 및 수리 견적서 보관",
      "보험사 콜센터 또는 앱에서 사고 접수"
    ],
    "disclaimer": "본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다."
  },
  "slots": {
    "area": "auto",
    "insurer": "한화손해보험",
    "product": "개인용자동차보험",
    "incident_date": "2026-05-23",
    "incident_type": "단독",
    "fault_ratio": 100,
    "damage_type": "자차",
    ...
  },
  "status": "answered"
}
```

---

### 3. 세션 상태 조회 — `GET /api/v1/sessions/{session_id}`

디버그 목적으로 세션의 현재 상태, 채워진 슬롯, 대화 이력을 확인할 수 있습니다.

```bash
curl -s http://localhost:8000/api/v1/sessions/7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c
```

응답 예시:

```json
{
  "session_id": "7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c",
  "created_at": "2026-05-24T09:00:00Z",
  "last_activity_at": "2026-05-24T09:05:30Z",
  "status": "answered",
  "slots": {
    "area": "auto",
    "insurer": "한화손해보험",
    "product": "개인용자동차보험",
    "incident_date": "2026-05-23",
    "incident_type": "단독",
    "fault_ratio": 100,
    "damage_type": "자차",
    "version": null,
    "evidence": [],
    "loss_type": null,
    "damaged_items": [],
    "cause": null,
    "diagnosis": null,
    "hospitalization_days": null,
    "outpatient_visits": null
  },
  "history": [
    {
      "role": "user",
      "content": "어제 빙판길에서 미끄러져 발목 골절로 입원했어요. 자동차보험으로 보험금 받을 수 있나요?",
      "created_at": "2026-05-24T09:00:00Z",
      "response_type": null
    },
    {
      "role": "assistant",
      "content": "어떤 보험사의 자동차보험에 가입하셨나요?",
      "created_at": "2026-05-24T09:00:01Z",
      "response_type": "ask"
    }
  ]
}
```

---

### 4. 세션 폐기 — `DELETE /api/v1/sessions/{session_id}`

대화가 끝났으면 세션을 명시적으로 삭제합니다.

```bash
curl -s -X DELETE http://localhost:8000/api/v1/sessions/7f3e8c2a-1b4d-4e5f-9a2c-3d6e7f8a9b0c
```

성공하면 응답 본문 없이 `204 No Content`를 반환합니다.

이 요청은 **멱등**합니다. 이미 만료되거나 없는 세션을 삭제해도 에러가 발생하지 않고 동일하게 204를 반환합니다.

---

## CLI `ica chat` 사용법

서버 없이 터미널에서 바로 멀티턴 대화를 할 수 있습니다. HTTP API와 동일한 로직을 사용하지만 네트워크 요청 없이 직접 서비스 레이어를 호출합니다.

### 실행

```bash
ica chat
```

### 실제 대화 흐름 예시 — 자동차 사고 시나리오

아래는 자동차 사고로 자차 처리를 문의하는 실제 흐름입니다.

```
세션 시작: 7f3e8c2a-... (/quit 또는 Ctrl+C 로 종료)
자연어로 자유롭게 입력하세요. 예: '어제 빙판에 미끄러져 발목 골절로 입원했어요'

나 ▶ 어제 빙판길에서 미끄러져 단독사고 났어요. 자동차보험 처리 가능한가요?

어시스턴트 ▶ (턴 1 · gathering)
어떤 보험사의 자동차보험에 가입하셨나요? 예: 한화손해보험, 삼성화재
옵션: 한화손해보험 · 삼성화재 · KB손해보험 · 직접 입력

나 ▶ 한화손해보험이요

어시스턴트 ▶ (턴 2 · gathering)
사고로 인한 피해가 어떻게 되나요? (차량 손해인지, 상대방 피해인지 등)
옵션: 자차(내 차 수리) · 대물(상대방 차/물건) · 대인(사람 부상) · 모두 해당

나 ▶ 자차 처리요. 제 과실이 100%예요.

어시스턴트 ▶ (턴 3 · answered) 가능성 높음
요약 자차 보장 조건에 부합합니다. 단독사고 자차 처리는 가입 특약 범위 내에서 지급될 가능성이 높습니다.
충족
  • 사고 유형 '단독사고' — 자차 보장 대상
  • 자차 손해 처리 요청
미충족
  • 자차 특약(자기차량손해) 가입 여부 미확인
인용 (1)
  한화손해보험 · 개인용자동차보험(공동물건) · 제15조 ① p.12
    보험금 지급 사유는 다음과 같다 ...
다음 단계
  → 보험증권에서 자차 특약 가입 여부 확인
  → 사고 현장 사진 및 수리 견적서 보관
  → 보험사 콜센터 또는 앱에서 사고 접수
본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다.

na ▶ /quit
세션 종료: 7f3e8c2a-...
```

### 종료 방법

대화를 끝내려면 다음 중 하나를 입력하세요:

- `/quit`
- `/exit`
- `:q`
- `Ctrl+C`

종료하면 세션이 자동으로 폐기됩니다.

---

## 응답 모드 2가지

어시스턴트 응답은 항상 두 가지 모드 중 하나입니다.

### ask 모드 — 정보 수집 중

필수 슬롯이 아직 채워지지 않았을 때 어시스턴트가 추가 정보를 요청합니다.

```json
{
  "type": "ask",
  "message": "사고 당시 본인 과실 비율을 알고 계신가요?",
  "expected_slots": ["fault_ratio"],
  "options": ["0%", "10%", "20~50%", "50%+", "모름"]
}
```

| 필드 | 설명 |
|:--|:--|
| `type` | 항상 `"ask"` |
| `message` | 어시스턴트가 보내는 자연어 질문 |
| `expected_slots` | 이 질문으로 채우려는 슬롯 이름 (1~2개) |
| `options` | 선택지가 명확할 때 제공. 없으면 빈 배열 |

### assessment 모드 — 최종 판단

필수 슬롯이 모두 채워지면 RAG 검색 + LLM 분석으로 가능성 판단을 내립니다.

```json
{
  "type": "assessment",
  "likelihood": "높음",
  "summary": "...",
  "satisfied": ["..."],
  "unsatisfied": ["..."],
  "citations": [...],
  "next_steps": ["..."],
  "disclaimer": "본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다."
}
```

| 필드 | 설명 |
|:--|:--|
| `type` | 항상 `"assessment"` |
| `likelihood` | 가능성 등급: `"높음"` / `"중간"` / `"낮음"` |
| `summary` | 판단 요약 (한 문단) |
| `satisfied` | 보장 조건을 충족하는 항목 목록 |
| `unsatisfied` | 충족되지 않거나 확인이 필요한 항목 목록 |
| `citations` | 판단의 근거가 된 약관 조항 인용 목록 (최소 1건) |
| `next_steps` | 다음 단계 행동 가이드 |
| `disclaimer` | 면책 문구 (자동 포함, 매 응답마다 반드시 노출) |

**면책 문구는 모든 assessment 응답에 자동으로 포함됩니다.** 개발자가 별도로 추가할 필요가 없습니다.

---

## 슬롯 표 — 영역별 필수 슬롯

슬롯(Slot)은 어시스턴트가 판단을 내리기 위해 수집해야 하는 정보입니다. 영역(area)에 따라 필요한 슬롯이 다릅니다.

### 공통 슬롯 (모든 영역)

| 슬롯 이름 | 설명 | 예시 |
|:--|:--|:--|
| `area` | 보험 영역 코드. 가장 먼저 결정 | `"auto"` / `"fire"` / `"accident_disease"` |
| `insurer` | 보험사 이름 | `"한화손해보험"` |
| `product` | 상품명 | `"개인용자동차보험(공동물건)"` |
| `version` | 약관 버전 (모르면 활성 버전 자동 선택) | `"2026-03-01_present"` |
| `incident_date` | 사고/진단 날짜 | `"2026-05-23"` |
| `evidence` | 보유 증빙 자료 목록 (권장) | `["진단서", "입원확인서"]` |

### auto 전용 슬롯 (자동차보험)

| 슬롯 이름 | 설명 | 예시 |
|:--|:--|:--|
| `incident_type` | 사고 유형 | `"추돌"` / `"단독"` / `"대물"` / `"대인"` |
| `fault_ratio` | 본인 과실 비율 0~100 (%) | `30` |
| `damage_type` | 청구 피해 유형 | `"자차"` / `"대물"` / `"대인"` |

### fire 전용 슬롯 (화재보험)

| 슬롯 이름 | 설명 | 예시 |
|:--|:--|:--|
| `loss_type` | 피해 유형 | `"전소"` / `"부분소실"` / `"도난"` / `"누수"` |
| `damaged_items` | 피해 물품 목록 | `["냉장고", "TV", "소파"]` |
| `cause` | 사고 원인 | `"전기 합선"` |

### accident_disease 전용 슬롯 (상해·질병보험)

| 슬롯 이름 | 설명 | 예시 |
|:--|:--|:--|
| `diagnosis` | 진단명 | `"발목 골절"` |
| `hospitalization_days` | 입원 일수 | `5` |
| `outpatient_visits` | 통원 횟수 | `3` |

슬롯은 한 번에 하나씩 모두 입력하지 않아도 됩니다. 여러 턴에 걸쳐 자연스럽게 대화하면 어시스턴트가 슬롯을 채워갑니다.

---

## 에러 응답

### 에러 응답 형태

모든 에러 응답은 아래 형태를 따릅니다:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "세션을 찾을 수 없습니다: 7f3e8c2a-..."
  }
}
```

### 주요 에러 코드

| HTTP 상태 코드 | 에러 코드 | 발생 시점 | 해결 방법 |
|:--|:--|:--|:--|
| 404 | `SESSION_NOT_FOUND` | 세션 ID가 없거나 TTL 만료 | `POST /sessions`로 새 세션 생성 |
| 503 | `LLM_UNAVAILABLE` | OpenAI API 호출 실패 | 잠시 후 재시도. `.env`의 `OPENAI_API_KEY` 확인 |
| 422 | `INSUFFICIENT_CONTEXT` | 어시스턴트가 판단 불가 (매우 드문 경우) | 더 많은 정보를 추가로 입력 |
| 400 | `VALIDATION_ERROR` | 요청 본문 형식 오류 | `text` 필드가 비어있지 않은지 확인 |

---

## TTL 및 세션 휘발성

| 항목 | 내용 |
|:--|:--|
| TTL (Time-To-Live) | 30분 (마지막 활동 기준). 환경변수 `SESSION_TTL_SECONDS`로 변경 가능 |
| 만료 기준 | 마지막 메시지 전송 후 30분 경과 시 |
| 만료 시 동작 | 세션 자동 폐기. 이후 해당 세션 ID로 요청하면 `SESSION_NOT_FOUND` 에러 |
| 서버 재시작 시 | 모든 세션 즉시 소멸 (메모리 저장) |
| 영구 저장 여부 | 없음. 개인정보 보호를 위해 의도적으로 휘발성 설계 |

30분이 지났거나 세션이 사라진 경우, `POST /api/v1/sessions`로 새 세션을 만들고 처음부터 다시 대화를 시작하면 됩니다.

---

## 면책 안내

> **본 도구의 모든 판단은 참고용입니다.**
>
> 어시스턴트가 제공하는 가능성 등급(높음/중간/낮음)과 약관 조항 인용은 약관 원문에 기반한 참고 정보이며, 실제 보험금 지급 여부를 보장하지 않습니다.
>
> 보험금 청구 여부의 최종 판단은 해당 보험사 또는 전문 손해사정사에게 문의하시기 바랍니다.

`assessment` 응답의 `disclaimer` 필드에 면책 문구가 자동으로 포함되므로, 이 내용을 사용자에게 반드시 노출해야 합니다.
