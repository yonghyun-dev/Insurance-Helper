# 응답 품질 정책 가이드

- 작성일: 2026-05-24
- 스프린트: 6 (응답 품질 정책 — 모름 처리 + partial assessment)
- 관련 요구사항: [REQ-06](requirements/06_response_quality.md)
- 관련 설계: [tech-decisions.md § Sprint 6](design/tech-decisions.md)

> **면책**: 본 도구의 판단은 참고용이며 최종 청구 가능 여부 결정을 대체하지 않습니다.

---

## 이 문서는 무엇인가요?

Sprint 6에서 추가된 **응답 품질 정책** 기능을 설명합니다. 사용자가 보험 가입 정보를 잘 모르거나 대화가 길어질 때, 어시스턴트가 무한 질문 루프에 빠지지 않고 부분 판단(추정)을 제공하는 동작 원리를 다룹니다.

개발자·운영자 관점에서의 동작 원리, 트러블슈팅, LLM 프롬프트 강제 규칙을 함께 정리했습니다.

---

## 1. "모름" 처리

### 동작 원리

사용자가 특정 슬롯에 대해 명시적으로 모른다고 답하면 어시스턴트가 이를 인식합니다.

**인식하는 표현 예시**:
- "보험사 모르겠어요"
- "과실 비율 잘 몰라요"
- "상품명은 몰라"

`extract_slots` 함수가 이를 인식하면 해당 슬롯명을 `SlotState.unknown_slots` 목록에 추가합니다. 슬롯 값 자체는 `null`로 유지됩니다.

```json
{
  "area": "auto",
  "insurer": null,
  "product": null,
  "unknown_slots": ["insurer", "product"]
}
```

`_compute_missing` 함수가 미충족 필수 슬롯을 계산할 때 `unknown_slots`에 있는 슬롯은 제외합니다. 따라서 같은 질문을 반복하지 않습니다.

### unknown_slots 누적 방식

`unknown_slots`는 대화 전체에 걸쳐 누적됩니다. 새로운 "모름" 표현이 나올 때마다 기존 목록에 추가(중복 제거)됩니다. 사용자가 이후에 해당 정보를 제공하더라도 `unknown_slots`에서 자동 제거되지 않습니다. — 실제 슬롯값이 채워지면 `_compute_missing`가 채워진 값을 보고 missing에서 제외하므로 결과는 동일합니다.

### negative 표현 처리 (0 채움)

"안 했어", "없어", "하루도 안 입원했어" 같은 부정 표현은 "모름"과 다릅니다. 어시스턴트가 이를 0으로 해석합니다.

| 사용자 입력 | 처리 결과 |
|:--|:--|
| "입원 안 했어요" | `hospitalization_days = 0` |
| "통원은 없어요" | `outpatient_visits = 0` |
| "과실 0%예요" | `fault_ratio = 0` |

0은 유효한 값이므로 `_compute_missing`가 충족으로 처리합니다.

---

## 2. partial 모드 — 추정 기반 판단

### 진입 조건

아래 세 조건 중 하나라도 충족하면 partial 모드로 진입합니다. 필수 슬롯이 모두 채워지지 않아도 즉시 판단을 제공합니다.

| # | 조건 | 임계값 | 의미 |
|:--|:--|:--|:--|
| 1 | `unknown_slots` 개수 | ≥ 2 | 사용자가 2개 이상의 슬롯에 "모름" 표시 |
| 2 | ask 턴 수 | ≥ 3 | 어시스턴트가 이미 3번 이상 추가 정보 요청 |
| 3 | 명시 키워드 | 1개 이상 | 사용자 입력에 "그냥", "됐어", "알려줘", "그만", "다 모름" 포함 |

조건 판정 코드 (`app/sessions/service.py`):

```python
_PARTIAL_KEYWORDS = ("그냥", "됐어", "알려줘", "그만", "다 모름")
_PARTIAL_ASK_THRESHOLD = 3
_PARTIAL_UNKNOWN_THRESHOLD = 2

def _should_partial(slots, missing, ask_count, user_text) -> bool:
    if len(slots.unknown_slots) >= _PARTIAL_UNKNOWN_THRESHOLD:
        return True
    if ask_count >= _PARTIAL_ASK_THRESHOLD:
        return True
    return any(kw in user_text for kw in _PARTIAL_KEYWORDS)
```

### partial 진입 시 동작

1. RAG 검색 결과가 1건 이상 있으면 `generate_assessment`를 즉시 호출합니다.
2. LLM이 `confidence='partial'`과 함께 요약 첫 문장에 "정보가 일부 부족하여 추정 기반..." 을 포함한 응답을 생성합니다.
3. `AssistantAssessment.confidence` 필드에 `'partial'`이 반환됩니다.
4. UI에서 노란색 "(추정)" 배지가 표시됩니다.

RAG 검색 결과가 0건이면 partial 모드라도 ask로 분기해서 슬롯 재확인을 유도합니다.

### confidence 필드

`AssistantAssessment.confidence` 필드는 두 값만 가집니다.

| 값 | 의미 | 진입 경로 |
|:--|:--|:--|
| `"full"` | 필수 슬롯 모두 충족, 정상 판단 | 기본값. 기존 동작 유지 |
| `"partial"` | 일부 슬롯 부족, 추정 기반 판단 | `_should_partial` 조건 충족 시 |

기본값이 `"full"`이므로 기존 응답(Sprint 5 이전 포함)은 변경 없이 동작합니다.

---

## 3. LLM 프롬프트 강제 규칙 요약

운영자가 LLM 프롬프트에 적용된 규칙을 이해하면 응답 품질 문제를 진단하기 쉽습니다.

### extract_slots 강제 규칙

| 규칙 | 내용 |
|:--|:--|
| area 추론 우선 | "입원/통원/진단/골절/질병/상해/넘어졌/다쳤/병원" → `area=accident_disease` 자동 추론 |
| 모름 처리 | "모름/몰라/모르겠어" → 해당 슬롯을 `unknown_slots` 배열에만 추가, `slot_updates`에는 넣지 않음 |
| negative=0 | "안 했어/없어/0번" → 해당 정수 슬롯에 0 채움 |
| 추론 금지 | 사용자가 명시하지 않은 필드는 추출하지 않음. 모호하면 생략 |
| 옵션 한국어 강제 | `next_question`의 options는 반드시 한국어 라벨. 영문 코드(`auto/fire`) 사용 금지 |

### next_question 강제 규칙

- 한 번에 1~2개 슬롯만 질문 (사용자 피로 회피)
- `area` 옵션은 `['자동차', '화재', '사고질병']` — 영문 코드 금지
- `expected_slots`는 `SlotState` 정의 필드명만 허용

### generate_assessment 강제 규칙

- `citations` 최소 1건 필수 (`minItems=1`)
- `confidence` 필드: `"partial"` 또는 `"full"` — schema `required`에 포함
- partial 시 `summary` 첫 문장: "정보가 일부 부족하여 추정 기반으로 판단합니다..."로 시작
- `disclaimer` 필드: 면책 문구 자동 포함, 제거 불가

---

## 4. UI — "추정" 배지

### 표시 조건

`AssistantAssessment.confidence === 'partial'`일 때만 배지가 표시됩니다.

```tsx
// AssessmentCard.tsx
const isPartial = p.confidence === 'partial';

{isPartial && (
  <span
    className="assess__partial-badge"
    title="정보가 일부 부족하여 추정 기반 답변입니다"
  >
    추정
  </span>
)}
```

카드 전체에도 `.assess--partial` 클래스가 추가되어 hero 영역에 노란 stripe가 표시됩니다.

### aria-label

```tsx
aria-label={`청구 평가 결과 - 가능성 ${p.likelihood}${isPartial ? ' (추정 — 정보 일부 부족)' : ''}`}
```

스크린리더 사용자도 "(추정 — 정보 일부 부족)"을 인식합니다.

### CSS 클래스 구조

| 클래스 | 적용 위치 | 역할 |
|:--|:--|:--|
| `.assess--partial` | `<article>` | hero band 노란 stripe 색조 변경 |
| `.assess__partial-badge` | `<span>` | 노란 배경 배지. likelihood 값 옆에 표시 |

---

## 5. 전체 대화 흐름 예시 — partial 모드 진입

아래는 사용자가 정보를 충분히 제공하지 못하고 "그냥 알려줘"를 입력해서 partial 모드로 진입하는 흐름입니다.

```
나 ▶ 어제 넘어져서 발목 다쳤어요

어시스턴트 ▶ (턴 1 · gathering)
어떤 보험사의 보험에 가입하셨나요? (예: 한화손해보험, 삼성화재)
옵션: 한화손해보험 · 삼성화재 · KB손해보험 · 직접 입력 · 모름

나 ▶ 모르겠어요
  → insurer → unknown_slots=['insurer']

어시스턴트 ▶ (턴 2 · gathering)
가입하신 상품명을 혹시 알고 계신가요?

나 ▶ 상품명도 몰라요
  → product → unknown_slots=['insurer','product']
  → _should_partial: unknown_slots(2) ≥ 2 → True → partial 모드 진입

어시스턴트 ▶ (턴 2 · answered) 가능성 중간 (추정)
정보가 일부 부족하여 추정 기반으로 판단합니다. 보험사·상품 정보가 확인되면 더 정확한 판단이 가능합니다.
충족 …
약관 근거 …
⚠ 추정 기반 — 보험사·상품 미확인. 실제 약관 확인 필요
본 결과는 참고용이며 최종 청구 가능 여부 판단을 대체하지 않습니다.
```

---

## 6. 트러블슈팅

### "모름"을 입력해도 같은 질문이 반복됩니다

- **원인**: `extract_slots` LLM이 "모름" 표현을 인식하지 못해 `unknown_slots`에 추가하지 않은 경우입니다.
- **확인**: `GET /api/v1/sessions/{id}`로 `slots.unknown_slots` 필드를 확인합니다.
- **조치**: LLM 프롬프트 규칙 6-a가 적용되고 있는지 `app/sessions/llm.py`의 `_extract_slots_system` 함수를 확인합니다.

### partial 모드로 진입하지 않습니다

- **원인 1**: ask 횟수가 아직 3 미만이고 `unknown_slots`도 2 미만인 경우입니다.
- **원인 2**: 사용자 입력에 `_PARTIAL_KEYWORDS` 키워드가 없는 경우입니다.
- **확인**: 서버 로그에서 `post_message: missing=... unknown=... ask_count=...` 행을 확인합니다.

### partial 응답에 인용이 없다는 오류가 발생합니다

- **원인**: RAG 검색 결과가 0건인 경우입니다. partial 모드에서도 `citations` 최소 1건은 필수입니다.
- **동작**: 0건이면 partial 대신 ask로 분기해서 보험사/상품 정보 재확인을 유도합니다.
- **조치**: `ica list --scope chunks`로 약관이 실제로 적재되었는지 확인합니다. 적재가 안 된 경우 `ica ingest`를 실행합니다.

### UI에 "(추정)" 배지가 표시되지 않습니다

- **원인**: `AssistantAssessment.confidence`가 `'partial'`이 아닌 경우입니다.
- **확인**: API 응답 JSON에서 `assistant.confidence` 필드를 직접 확인합니다.
- **조치**: partial 진입 조건 3가지를 모두 충족하지 못했거나, 프론트엔드 타입 파일(`types/api.ts`)의 `confidence` 필드 정의를 확인합니다.

---

## Sprint 7 보완 — 응답 톤 가이드

Sprint 6 partial 모드와 Sprint 7 톤 정책은 **보완 관계**입니다.

- **Sprint 6 partial 모드**: 사용자 정보가 일부 있을 때, 추정 기반으로 판단을 제공합니다.
- **Sprint 7 톤 정책**: 사용자 정보가 없거나 부족할 때, 시스템이 능동적으로 안내합니다.

두 정책은 함께 적용되어 어떤 상황에서든 사용자 경험을 일관되게 만들어 줍니다.

### 톤 4원칙

모든 user-facing 응답(ask / no_match / partial / assessment)에 아래 원칙이 강제됩니다.

| 원칙 | 금지 | 권장 |
|:--|:--|:--|
| 능동적 안내 | "다시 확인해 주세요" / "정확히 알려주세요" | "정확한 안내를 위해 ... 정보를 확인하고 싶습니다" |
| 책임 비전가 금지 | "입력 정보가 부족합니다" (사용자 책임) | "현재 정보만으로는 일반적인 약관 기준에 따라 안내드리겠습니다" |
| 정확성·범용성 명시 | (구분 없음) | 정보 충족 → "정확하게 안내드립니다" / 부족 → "일반적인 기준으로 안내드립니다" |
| 친절체 + 존댓말 | 명령형 / 반말 | "~드리겠습니다" / "~주시면 좋겠습니다" / "~안내드립니다" |

### 적용 위치

| 함수 / 위치 | 변경 방식 |
|:--|:--|
| `_build_no_match_ask` (`app/sessions/service.py`) | 하드코딩 메시지 재작성. "다시 확인해 주세요" → "알고 계신 정보가 있다면 알려주시면 정확하게 안내드리겠습니다" |
| `_NEXT_QUESTION_SYSTEM` (`app/sessions/llm.py`) | 시스템 프롬프트 끝에 "톤 가이드 (강제)" 절 추가. 친절체 + 능동 안내 강제 |
| `_ASSESSMENT_SYSTEM` (`app/sessions/llm.py`) | partial 시 summary 첫 문장 톤 강제. "정확한 답변에는 ... 현재 정보로 일반적인 약관 기준에 따라 안내드리겠습니다" |
| `extract_slots` | 변경 없음 — tool args만 반환, user-facing 메시지 없음 |

### RAG ≥ 1 강제 유지

Sprint 7 톤 보완 이후에도 citation 없는 답변은 허용되지 않습니다. RAG 검색 결과가 0건이면 partial 모드라도 ask로 분기합니다. 이는 Sprint 6 결정 4를 그대로 보존한 것입니다.

- citation 없는 답변 = LLM 일반지식 의존 = 환각 위험 ↑
- 사용자 경험 향상은 톤 보완만으로도 충분 (schema 변경 없음, 회귀 0)

### 비용 영향

| 항목 | 수치 |
|:--|:--|
| LLM 호출 추가 | 0 (시스템 프롬프트 텍스트만 추가) |
| 토큰 증가 | `_NEXT_QUESTION_SYSTEM` + `_ASSESSMENT_SYSTEM` 각 ~80 토큰. 턴당 ~$0.00001 |
| schema 변경 | 0 |
| 회귀 | 0 (응답 구조 동일, 메시지 텍스트만 다름) |
| frontend 변경 | 0 |

---

## 7. 운영자 참고 — 임계값 조정

partial 모드 임계값은 `app/sessions/service.py`에 상수로 정의되어 있습니다.

```python
_PARTIAL_KEYWORDS: tuple[str, ...] = ("그냥", "됐어", "알려줘", "그만", "다 모름")
_PARTIAL_ASK_THRESHOLD: int = 3   # ask 횟수 임계값
_PARTIAL_UNKNOWN_THRESHOLD: int = 2  # unknown_slots 임계값
```

PoC 단계 기본값입니다. 실서비스에서 사용자 패턴을 확인한 후 조정할 수 있습니다.

- `_PARTIAL_ASK_THRESHOLD`를 낮추면 더 빨리 partial 모드로 진입합니다.
- `_PARTIAL_UNKNOWN_THRESHOLD`를 높이면 더 많은 "모름"이 쌓여야 partial 모드가 됩니다.
- `_PARTIAL_KEYWORDS`에 키워드를 추가하면 인식 범위가 넓어집니다.

---

## 관련 문서

| 문서 | 내용 |
|:--|:--|
| [`docs/usage_sessions.md`](usage_sessions.md) | 세션 API curl 예시 + 슬롯 표 + 에러 코드 |
| [`docs/design/tech-decisions.md § Sprint 6`](design/tech-decisions.md) | 설계 결정 상세 (모름 처리 / confidence schema / partial 조건) |
| [`docs/requirements/06_response_quality.md`](requirements/06_response_quality.md) | 요구사항 F-1~F-8 원문 |
| [`docs/design/ui-spec.md § 3.6`](design/ui-spec.md) | AssessmentCard partial badge UI 명세 |
| [`docs/design/ui-api-flow.md § 4`](design/ui-api-flow.md) | TypeScript 타입 (`AssistantAssessment.confidence`) |
