# REQ-09: 신뢰도 + UX 보강 (약관 캡처 + 모름 선택지 + OptionsPanel)

- 요청일: 2026-05-25
- 상태: 분석 완료, 설계 진행 중 (외부 디자인 작업 대기)
- 스프린트: 8.6

## 요청 원문
> "약관 근거는 약관 원본 캡쳐본이랑 텍스트로 보여줘야돼. 실제로 약관 원본에서 어떤 부분이 해당이 되는지 알아야지 신뢰도가 높아질거야. 그리고 프론트는 리엑트에 typescripts로 변환해줘. 추가로 선택지를 줄때 모르겠습니다. 이것도 추가해줘. 그리고 이걸 대화 텍스트블럭에 넣는것이 아닌 마치 클로드 플랜모드처럼 하단 중앙부에 선택지가 뜨게 해줘."

## 핵심 목표

- **신뢰도**: 약관 인용을 텍스트뿐 아니라 PDF 페이지 캡처와 함께 보여 사용자가 실제 출처를 시각 확인
- **UX**: ask options 를 메시지 안 inline 이 아닌 하단 중앙 fixed 패널 (Claude Plan 모드 패턴)
- **포용성**: 모든 ask options 에 "모르겠습니다" 의무 추가 — 대부분 사용자가 정확히 모름

## 사용자 시나리오

1. **신뢰도** — 청구 가능성 응답 → 인용 카드 클릭 → "이 답변이 실제 약관 p.19 의 제24조 ③에서 왔구나" 즉시 확인
2. **UX** — ask 응답 → 하단 중앙 큰 chip 패널 → "모르겠습니다" 포함 4 선택지 → 한 번에 선택
3. **포용성** — 노인 사용자 "보험사 정확히 몰라요" → "모르겠습니다" chip 클릭 → unknown_slots 머지 → partial 모드 자연 진입 → 즉시 추정 답변

## 기능 목록

| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | backend `_NEXT_QUESTION_SYSTEM` 에 "모르겠습니다" 옵션 강제 1절 추가 | 필수 | 모든 ask options 마지막에 의무 | **완료** (PM 직접) |
| F-2 | backend Citation.page_image_url + pdf_url 응답 hydrate 검증 | 필수 | Sprint 5 이미 구현 — 점검만 | **완료** (스모크 OK) |
| F-3 | CitationItem 확장 명세 (PDF 캡처 + 텍스트 동시) | 필수 | docs/design/pages/citation-item.md | **완료** (명세서) |
| F-4 | OptionsPanel 신규 명세 (하단 중앙 fixed, Claude Plan 패턴) | 필수 | docs/design/pages/options-panel.md + "모르겠습니다" chip | **완료** (명세서) |
| F-5 | AskCard 변경 명세 (options inline 제거) | 필수 | ui-spec.md § 8.9 컴포넌트 트리 | **완료** (명세서) |
| F-6 | frontend 구현 — 외부 Claude 디자인 작업 | 필수 | 사용자 외부 작업 (다음 zip) | 대기 |
| F-7 | playwright 시연 검증 (4 시나리오 + OptionsPanel + 캡처) | 필수 | frontend 통합 후 | 대기 |

## 기술 결정

- **frontend 스택**: 이미 React + TypeScript (Vite). 사용자가 "TypeScript 로 변환" 요청했으나 이미 적용된 상태. 추가 변환 작업 없음.
- **backend hydrate**: Sprint 5 의 `page_image_url` + `pdf_url` 이미 응답에 포함. frontend 가 활용만 하면 됨.
- **OptionsPanel 등장 조건**: 마지막 assistant 응답 `type='ask'` + `options.length > 0`. 자유 답변 가능 (자유 입력 시 panel 무시 + hide).
- **"모르겠습니다" 처리**: LLM 자체가 옵션에 추가 + 사용자 선택 시 텍스트 그대로 전송 → extract_slots 가 unknown_slots 머지 → partial 모드 자연 진입 (Sprint 6).

## 비고

- 기존 frontend (사용자 외부 작업본) 의 `CitationItem` + `AskCard` 가 위 명세 대로 갱신 필요
- 디자인 명세서 3개 (`citation-item.md`, `options-panel.md`, `ui-spec.md § 8.7~8.9`) 가 외부 디자인 작업 입력
- 운영자가 OpenAI API key 설정 후 다음 ask 부터 자동 "모르겠습니다" 옵션 노출 (backend 재시작 필요)
