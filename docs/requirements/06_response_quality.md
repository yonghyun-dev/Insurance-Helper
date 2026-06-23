# REQ-06: 응답 품질 정책 — 모름 처리 + partial assessment + area 추론 강화

- 요청일: 2026-05-24
- 상태: 분석 완료, 설계 진행 중
- 스프린트: 6

## 요청 원문

> "나머지 진행해줘" — Sprint 3/4 데모에서 발견한 응답 품질 갭 4건 해소:
> - **#C** "몰라"/"모르겠어" 응답 인지 못함 → 같은 질문 무한 반복
> - **#D** "입원 안 했어" → 0 처리 실패 → 같은 질문 반복
> - **#E** 슬롯 부족 시 partial/범용 답변 없음 — 무한 질문 모드
> - **#F** "걷다가 넘어졌어" → area=accident_disease 추론 실패 (Sprint 4 데모)

## 핵심 목표

- 노인·일반 사용자가 자신의 가입 정보를 잘 모를 때도 **범용 답변 제공** ("정보가 빈약하니까 일반적으로 말씀드리고, 더 자세히 주면 어떻게 도와드리겠다")
- 무한 ask 루프 방지 — "모름" 명시 또는 일정 시도 초과 시 partial assessment 강제
- area 자동 추론 정확도 ↑ — extract_slots 프롬프트 보강

## 사용자 시나리오 (개선 대상)

1. "길에서 넘어졌어" → area=accident_disease 자동 추론 (현재 영문 옵션 노출 X)
2. "보험사 몰라" → 명시적 "모름" 처리 → 같은 질문 재요청 안 함
3. 슬롯 60% 채워졌고 사용자가 "다 모름" 표시 → **partial assessment** ("정보 부족으로 추정 가능성: 중간 — 다음 정보를 추가하시면 더 정확합니다")
4. "입원 안 함" → hospitalization_days=0 인식 → 슬롯 충족

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | extract_slots "모름" 인식 | 필수 | `_UNKNOWN_VALUES = {"모름","몰라","모르겠어",...}` → SlotState 에 `unknown_slots: set[str]` 추가, 해당 슬롯은 missing 에서 제외 | 설계 |
| F-2 | extract_slots negative 인식 | 필수 | "안 했어"/"없어"/"0번" → 정수 슬롯 0 채움 | 설계 |
| F-3 | extract_slots area 추론 강화 | 필수 | "넘어졌어/다쳤어/병원" → area=accident_disease 자동. few-shot 예시 추가 | 설계 |
| F-4 | partial assessment 모드 | 필수 | `AssistantAssessment.confidence: Literal['partial','full']` + summary 에 부족 정보 안내 | 설계 |
| F-5 | service 분기 정책 — partial 진입 조건 | 필수 | (a) 사용자가 "모름" 표시한 슬롯 ≥ 2 / (b) ask 횟수 ≥ 3 / (c) 사용자 명시 "그냥 알려줘" → partial | 설계 |
| F-6 | next_question 한국어 옵션 강제 | 권장 | area 옵션을 영문 코드(`auto`/`fire`) 가 아닌 한국어(`자동차`/`화재`/`사고질병`) — Sprint 4 데모서 자연 회복 확인했지만 명시 강제 | 설계 |
| F-7 | LLM 프롬프트 4종 갱신 | 필수 | extract_slots/next_question/generate_assessment + 새 helper | 설계 |
| F-8 | frontend confidence 표시 | 권장 | "partial" 시 badge (예: "추정") + summary 강조 | 설계 |
| F-9 | 옵션 동적 생성 | 백로그 | next_question 의 `options` 에 placeholder ("보험사1/2/3") 대신 등록 보험사 list — `GET /documents/products` 활용 | Sprint 7+ |

## 비기능 요구사항

- **회귀 0** — 기존 499 tests + ruff 0 유지. assessment 모드 (full) 기본 동작 무변경
- **schema 호환** — `confidence` 는 default 'full' 로 optional 추가 (Sprint 5 의 page_image_url 패턴)
- **LLM 비용** — 큰 변경 없음 (프롬프트 변경만, 추가 호출 X)
- **frontend 영향** — 컴포넌트 1개 (AssessmentCard) 의 partial 표시 추가 (PM 직접 또는 사양서만 갱신)

## PoC 범위

- backend: `app/sessions/{schemas,service,llm}.py` 변경 + LLM 프롬프트 4종 갱신
- frontend: AssessmentCard 의 partial badge 1개 (선택 — 사양서 갱신만 가능)
- 옵션 동적 생성 (F-9) 은 Sprint 7+ 백로그

## 기술 결정 (요약 — 상세는 tech-decisions § Sprint 6)

- **SlotState 확장 vs 별도 필드** — `unknown_slots: list[str]` (Set 은 pydantic 직렬화 어려움) 채택. extract_slots 가 직접 채움
- **partial 진입 조건** — service.py 의 `_compute_missing` 결과에 더해 (a) unknown 슬롯 / (b) ask 횟수 임계 / (c) 사용자 명시 "그냥" 단어 인식
- **confidence schema** — `Literal['partial', 'full']` default 'full'. assessment.summary 가 부족 슬롯 한 줄 안내 포함

## 리스크

1. **LLM 프롬프트 변경 → 기존 동작 회귀** — Sprint 2 의 351 sessions tests 깨질 가능성. test-writer 가 monkeypatch 로 LLM mock 하지만 실제 호출 시점은 sprint 안에서 playwright 로 회귀 확인
2. **partial assessment 가 citations 빈 array** — schema `minItems=1` 강제와 충돌. **결정**: partial 모드는 `minItems=1` 유지하되 chunks 결과가 0건이면 `_build_no_match_ask` 분기 (기존 동작). 즉 "RAG 결과 있으면 partial 가능, 없으면 ask" 정책
3. **frontend 변경 → Claude 디자인 동기화** — Sprint 5 처럼 PM 직접 1개 컴포넌트 수정 권장
4. **AssistantAssessment schema 변경 → JSON Schema 갱신** — `_ASSESSMENT_RESPONSE_SCHEMA` 에 confidence optional 추가 필요

## 가정

- partial assessment 도 citations 1건 이상 필요 (RAG 결과 0 → ask 분기 유지)
- "모름" 표시는 사용자 자연어 입력 기반 (UI 별도 버튼 X)
- frontend partial badge 는 디자인 자유 (사양서만 갱신, 사용자가 원하면 Claude 디자인 재호출)
