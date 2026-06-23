# REQ-15: 프론트엔드 리디자인 통합 + 백엔드 신규 기능

- 요청일: 2026-06-15
- 상태: 분석 완료, 설계 대기
- 스프린트: 20~23 (제안)

## 요청 원문
> 일단 프론트 페이지 먼저 바꾸는 작업하자. (사용자가 별도 제작한 `github.com/dfocus-ai/Insurance-Helper` 디자인 목업을 현재 동작 프론트에 통합)
> "백엔드가 없는 기능은 새로 추가해서 만들어야지"
> 마이데이터는 받아왔다는 가정으로 더미로 진행. 자동 접수도 가정(A)으로.

## 핵심 목표
- 새 dfocus 디자인(목업, 백엔드 미연동)을 채택하고, 기존 동작 프론트의 백엔드 연동 로직을 **이식**해 "예쁘면서 실제 동작하는" 프론트로 만든다.
- 새 디자인이 가정하지만 백엔드에 없는 기능(서류 체크리스트, 청구 요약)은 **실제 백엔드 신규 기능**으로 만든다.
- 마이데이터/건강보험/자동접수는 **"받아온/처리된 가정"(더미)** 으로 시연 완성도 확보. 실연동은 운영 전환 시.

## 두 코드베이스 현황 (조사 결과)
- **새 디자인** `/home/edgar/dev/dfocus-frontend/insurance-helper-react`: React18+Vite+react-router+clsx. 디자인 시스템 완비(Button/Modal/Tabs/Accordion/Field 등) + 멀티스텝 흐름(Welcome→Identity→Situation→Loading→Chat→Review) + 채팅 패턴(InfoCard/ActionCard/DocChecklist/StateCard/MessageBubble). **백엔드 호출 전무** — `scenarioMessages.tsx` 하드코딩 시나리오(main/docs/unclear/low).
- **기존 프론트** `/home/edgar/dev/Insurance-Helper/frontend`: 백엔드 완전 연동. `api/client.ts`(8 엔드포인트) + `types/api.ts` + `useSession.ts`(세션/멀티턴/복구/OCR/Toast) + 컴포넌트(AssessmentCard/CitationList/AskCard/OptionsPanel/HealthHistoryPanel/ChatInput 등). 디자인 단순.

## 채팅 모델 불일치 (가장 중요)
- 새 디자인 = **시나리오 분기**(고정 카드). 백엔드 = **ask→assessment 멀티턴 루프**. → ChatPage를 실제 응답으로 구동하도록 **재배선** 필요. 하드코딩 시나리오 제거.

## 기능 목록
| # | 기능 | 우선순위 | 설명 | 상태 |
|:--|:--|:--|:--|:--|
| F-1 | 새 앱 골격 도입 + 백엔드 계층 이식 | 필수 | api/client·types·useSession을 새 앱에 이식. `frontend/`교체, 구버전 `frontend_legacy/`백업 | 미시작 |
| F-2 | ChatPage 재배선 | 필수 | scenarioMessages 하드코딩 제거 → ask/assessment 루프. 디자인패턴(MessageBubble/InfoCard/ActionCard/StateCard)에 백엔드 데이터 매핑 | 미시작 |
| F-3 | 인용(Citation) 컴포넌트 신규 | 필수 | 새 디자인 시스템 기반 인용 카드 — 약관 원문+PDF 캡처 썸네일+원본 링크 | 미시작 |
| F-4 | 진입 흐름 연결 | 필수 | Welcome→Situation→createSession 첫 메시지, Loading→실 응답 대기 | 미시작 |
| F-5 | Identity 데모 게이트 + 배경 자동 로그인 | 필수 | 화면은 통과 게이트. 통과 시 데모 계정 JWT 쿠키 조용히 획득 → 더미 마이데이터/건강보험 흐름 확보 | 미시작 |
| F-6 | OCR 업로드 + 건강보험 패널 이식 | 필수 | ChatInput 첨부 업로드, HealthHistoryPanel(더미 진료내역) | 미시작 |
| F-7 | **[신규 백엔드] 필요서류 체크리스트** | 필수 | 평가 결과 기반 구조화된 서류 목록 생성 endpoint(서류명+상태: 자동확인/업로드필요/선택). DocChecklist 구동 | 미시작 |
| F-8 | **[신규 백엔드] 청구 준비 요약** | 필수 | 대상 정책+사유+약관근거+서류 집계 endpoint. Review 페이지 구동 | 미시작 |
| F-9 | **[신규 백엔드] 청구 접수(가정)** | 필수 | "접수 완료"까지 더미 처리(실 전송 없음). 운영 전환 시 실연동 | 미시작 |
| F-10 | 법적 페이지 + 접근성 이식 | 필수 | Disclaimer/Privacy/Sources/Accessibility + 폰트크기(WCAG 2.1 AA) | 미시작 |

## 기술 결정
- **스택**: 새 앱 스택 채택 (React18+Vite+react-router-dom+clsx). 기존은 react만 → react-router 추가됨.
- **백엔드 연동 자산 이식**: client.ts(credentials:'include', VITE_API_BASE_URL), types/api.ts, useSession 상태머신 그대로.
- **신규 백엔드 기능**: 도메인 응집 원칙 따라 `app/claims/`(가칭) 신규 — 서류 체크리스트/청구 요약/접수(가정). 또는 sessions 도메인 확장 (설계에서 확정).
- **인증**: 데모 게이트 + 배경 자동 로그인(기존 JWT signup/login 재사용). 실 본인인증/마이데이터는 운영 전환 시.

## 비고
- H-1(로그인 UI 부재) 갭을 IdentityPage가 자연 해소.
- 자동접수 = 마이데이터와 동일하게 "가정" 처리(사용자 결정 A).
- 본 작업은 Sprint 16(Upstage LLM) 과 독립. 순서는 사용자 결정.
