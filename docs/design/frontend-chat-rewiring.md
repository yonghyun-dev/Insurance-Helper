# 설계: 채팅 재배선 매핑 (새 dfocus 디자인 ↔ 백엔드 ask/assessment)

- 작성일: 2026-06-15
- 관련: REQ-15, PM-24, Sprint 20
- 목적: 새 디자인의 **시나리오 분기 목업 채팅**을 백엔드의 **ask→assessment 멀티턴 루프**로 구동하도록, UI 패턴 ↔ 백엔드 데이터의 1:1 매핑을 확정한다.

---

## 0. 두 모델 대조 (재확인)

| | 새 디자인 (현재) | 백엔드 (목표 구동) |
|:--|:--|:--|
| 메시지 출처 | `buildScenarioMessages()` 하드코딩 (main/docs/unclear/low) | `useSession` 의 `ChatMessage[]` (실 응답) |
| 진행 | `onSwitch(scenario)` 로 카드 교체 | `sendMessage(text)` → `SessionResponse` 누적 |
| 봇 응답 종류 | 자유 ReactNode (InfoCard/ActionCard/StateCard 섞음) | `AssistantAsk` 또는 `AssistantAssessment` (discriminated union) |
| 입력 | `Composer.onSend` → setTimeout 가짜 응답 | `Composer.onSend` → 실 API |
| 사이드바 단계 | `SCENARIO_RAIL` 고정 | 세션 `status`/`slots` 에서 파생 |

**결론**: `scenarioMessages.tsx` 의 `buildScenarioMessages` / `SCENARIO_RAIL` 등 하드코딩 데이터는 **제거**하고, ChatPage 는 `useSession` 의 상태를 구독해 메시지 타입별로 디자인 패턴을 렌더한다.

---

## 1. 타깃 아키텍처

```
useSession (이식)            ChatPage (재배선)             디자인 패턴 (재사용/신규)
─────────────              ───────────────             ──────────────────────
messages: ChatMessage[]  → map(renderMessage)        → MessageBubble + (타입별 본문)
isSending                → typing indicator          → TypingBubble
sendMessage(text)        ← Composer.onSend
uploadFile(file)         ← Composer.onAttach
slots / status / turn    → deriveRail()              → StepNavigator / ChatHead / sideStatus
lastAsk.options          → (ask 본문 내 선택지)       → ActionCards
```

- ChatPage 는 자체 `messages` state 를 버리고 **`useSession()` 을 호출**해 그 상태를 그린다.
- 기존 `nowKo()`(현재시각)는 ISO 입력을 못 받음 → **신규 헬퍼 `koTime(iso)`** 작성해 `created_at` → "오후 2:31" 변환 (M1).
- 봇 이름은 `'보험길잡이'`, 사용자 이름은 데모 흐름의 `user.name` 사용.

### 1.1 MessageBubble 공통 변환 (C1 — 필수)
`MessageBubble.tsx` 의 `role`/`name`/`time` 은 **모두 필수**이며 `role` 은 `'bot'|'user'`(백엔드 union 은 `'user'|'assistant'`). 모든 타입 렌더에서 아래 변환을 적용:
```
role  = m.role === 'user' ? 'user' : 'bot'
name  = m.role === 'user' ? user.name : '보험길잡이'
time  = koTime(m.created_at)
initial = m.role === 'user' ? user.name?.[0] : undefined   // bot 은 아이콘
```

### 1.2 useSession 반환값 — 추가 사용 (M3)
§1 골격 외에 다음도 사용: `isRestoring`(초기 세션 복원 중 → Composer disable/스플래시), `toasts`/`removeToast`/`pushToast`(만료·오류 안내 렌더), `startNewSession`(아래 reset 경로).

---

## 2. ChatMessage 타입별 렌더 매핑 (핵심)

`useSession` 의 `ChatMessage` union (types/api.ts:187) → 각 타입을 `MessageBubble` 로 감싸고 본문을 다음과 같이 구성.

### 2.1 `{role:'user'}` — 사용자 메시지
- `MessageBubble role="user" initial={user.name[0]}`
- 본문: `<p>{content}</p>`
- `attachment` 있으면: 썸네일(`<img src={dataUrl}>`) + 파일명 → 클릭 시 라이트박스 (ImageLightbox 이식)

### 2.2 `{role:'assistant', type:'ask'}` — 슬롯 질문 → **AskBlock (신규 조합)**
`payload: AssistantAsk { message, expected_slots, options }`

| 백엔드 필드 | 새 디자인 표현 |
|:--|:--|
| `message` | `<p>{message}</p>` (질문 텍스트) |
| `options` (비어있지 않으면) | `<ActionCards columns={options.length<=2?2:1}>` + 각 option → `<ActionCard icon="information" title={option} onClick={()=>sendMessage(option)} />` |
| `options` (빈 배열) | 선택지 카드 없음 — Composer 자유 입력으로 답변 |
| `expected_slots` | (선택) 디버그/접근성 라벨로만. 화면 비표시 |

> **M5**: ask 카드의 ActionCard 들은 `isSending` 동안 비활성(중복 클릭 방지). 또한 가장 최근 ask 만 클릭 가능하게 할지(이전 ask 카드는 표시만) 구현 시 정리 — 최소한 `disabled={isSending}`.

> 기존 디자인의 "통원/입원" ActionCards 가 정확히 이 역할 — 단 `onSwitch('docs')` 대신 `sendMessage(optionText)` 로 교체.
> "모름/모르겠습니다" 옵션은 backend 가 options 에 포함해 보냄 → 동일하게 ActionCard 로 렌더 (별도 색 처리는 Sprint 23 접근성에서).

### 2.3 `{role:'assistant', type:'assessment'}` — 평가 결과 → **AssessmentBlock (신규 조합)**
`payload: AssistantAssessment { likelihood, summary, satisfied[], unsatisfied[], citations[], next_steps[], disclaimer }`

순서대로 조합:

| # | 백엔드 필드 | 새 디자인 표현 | 비고 |
|:--|:--|:--|:--|
| 1 | `likelihood` + `summary` | `StateCard kind={LIKELIHOOD_KIND[likelihood]} title={"청구 가능성: "+likelihood}>{summary}</StateCard>` | **색 매핑 주의** ↓ |
| 2 | `satisfied[]` | InfoCard 대체 — "충족 항목" 제목 + 체크 리스트 (`checkmark` 아이콘 행) | 빈 배열이면 섹션 생략 |
| 3 | `unsatisfied[]` | "미충족·확인 필요 항목" 제목 + 경고 리스트 (`warning-filled`) | 빈 배열이면 생략 |
| 4 | `citations[]` | **`<CitationList>` (신규 컴포넌트, §3)** | minItems=1 보장 |
| 5 | `next_steps[]` | "다음 단계" 제목 + 번호 리스트(`<ol>`) | Sprint 22 에서 DocChecklist 연계 검토 |
| 6 | `disclaimer` | `<p class="disclaimer" role="note">` 항상 표시 | **제거 금지** |

**likelihood → StateCard kind 매핑** (I1 — 정정):
구프론트는 **3색 — 높음=녹색 / 중간=앰버 / 낮음=회색**(빨강 없음, `index.css:620-649`). 이 3단계 구분을 보존하기 위해 StateCard 의 3 kind 를 사용:
```
높음 → 'success'   (녹색)
중간 → 'warning'   (앰버) — info 로 합치지 않음. 중간의 경고 신호 보존
낮음 → 'info'      (차분/회색 계열) — 'error'(빨강) 사용 안 함
```
> 이는 "정책 계승"이 아니라 구프론트 3색 의미를 새 StateCard kind 로 **매핑**한 것. 색만으로 등급을 전달하지 않으며 항상 "청구 가능성: {등급}" 텍스트 동반.

### 2.4 `{role:'assistant', type:'loading'}` — 로딩
- `MessageBubble role="bot" name="보험길잡이" time={koTime(created_at)}` + `<TypingBubble />`
- **M4 — 단일 경로**: `useSession` 이 전송 중 `type:'loading'` 메시지를 큐에 넣고 응답 도착 시 `ingestResponse` 가 제거(`useSession.ts:85`). 따라서 **`type:'loading'` 렌더만** 사용하고, 별도 `isSending` 기반 말미 TypingBubble 은 두지 않는다(중복 방지).

### 2.5 `{role:'assistant', type:'error'}` — 오류 → StateCard(error)
`{ code, message, retryText }`
- `<StateCard kind="error" title="일시적인 문제가 발생했어요">{message}` + `actions={<Button onClick={()=>retryLast(retryText)}>다시 시도</Button>}</StateCard>`

---

## 3. 신규 컴포넌트: CitationList (디자인 시스템 기반)

기존 `CitationItem/CitationList` 의 **로직**을 새 디자인 시스템 스타일로 재구현. (새 디자인엔 인용 컴포넌트가 없음 → 신규)

Props: `{ citations: Citation[] }`
표시 필드 (Citation):
- 헤더: `{insurer} · {product} · {clause}{sub_no?` ${sub_no}`:''}` + 우측 `원본 PDF` 링크(`{pdf_url}#page={page}`)
- 본문: `page_image_url` 있으면 썸네일(`<img>`) + `p.{page}` → **클릭 시 새 탭**(`<a target="_blank" href={pdf_url}#page={page}>`) / 없으면 생략. **(I2 — 라이트박스 아님)** 라이트박스는 §2.1 사용자 첨부 이미지 전용. 인용 캡처는 기존 `CitationItem.tsx:44-63` 와 동일하게 새 탭.
- 인용 원문: `<blockquote>{text}</blockquote>`
- 동작: 첫 1건 펼침, 나머지 토글 (기존 정책 계승)
- 컨테이너: 디자인 시스템 Tile 또는 chat.module.css 스타일 활용, `role="region" aria-label="약관 인용"` **(M2 — 기존 라벨과 통일)**

---

## 4. 사이드바 (StepNavigator / ChatHead / sideStatus) 동적 파생

`SCENARIO_RAIL`/`SCENARIO_HEAD`/`SCENARIO_STATUS` 하드코딩 제거 → 세션 상태에서 파생.

### 4.1 진행 단계(rail) 파생 규칙 — `deriveRail(status, slots, hasAssessment)`
고정 6단계 골격 유지, status 만 동적:
```
1 상황 입력         : 항상 done (Situation 통과)
2 정보 확인(슬롯)    : status==='gathering' → active / 이후 → done
3 청구 가능성 검토   : status==='analyzing' → active / assessment 도착 → done
4 결과 안내          : hasAssessment → done(또는 active)
5 필요 서류 안내      : Sprint 22 연계 (그 전엔 pending)
6 보험사 제출 안내    : Sprint 22 연계 (pending)
```
> Sprint 20 범위: 1~4 동적, 5~6 은 pending 고정. Sprint 22 에서 서류/접수 연계.

### 4.2 ChatHead / sideStatus
- `title`: 고정 "청구 가능성 확인" (또는 상태별 간단 매핑)
- `sub` / `sideStatus`: status 기반 한 줄 (gathering="필요한 정보를 확인하고 있어요" / analyzing="약관과 비교 중이에요" / answered="검토 결과를 안내했어요")
- UserPill `meta`: "인증 완료 · 마이데이터 연동됨" — 데모 가정 유지 (Sprint 21 에서 실제 게이트 연동)

---

## 5. Composer 배선

| Composer prop | 연결 |
|:--|:--|
| `onSend(text)` | `useSession.sendMessage(text)` |
| `onAttach` | **인자 없는 트리거**(`Composer.tsx:21` `()=>void`). ChatPage 가 hidden `<input type=file>` 를 직접 관리 → 파일 선택 시 `useSession.uploadFile(file)` 호출 (I4) — Sprint 21 |
| `attachments` | 업로드 중 파일 칩 (Sprint 21) |
| `disabled` | `isSending \|\| isRestoring` |
| `hint` | 기존 면책 힌트 유지 |

---

## 6. 제거 / 보존 목록

**제거** (Sprint 20):
- `scenarioMessages.tsx` 의 `buildScenarioMessages`, `SCENARIO_RAIL`, `SCENARIO_HEAD`, `SCENARIO_STATUS`, `ChatScenario` 분기
- ChatPage 의 `handleSend`/`handleUpload` setTimeout 가짜 응답, 자체 `messages` state, `scenario` prop 의존
- **AppFlow 정리 (I5)**: `scenario`/`setScenario`/`handleSwitchScenario`/`ChatScenario` import 가 데드코드가 됨 → 함께 제거. **단 "처음으로(reset)" 경로는 보존 필수** — ChatHead `:174` "처음으로"·`onChangeScenario('reset')` 가 welcome 복귀 유일 경로(`AppFlow.tsx:28-31,63`). 대체: ChatPage 에 `onReset` prop 신설 → `useSession.startNewSession()` 호출 + AppFlow 가 welcome 단계로 전환. ChatHead "처음으로"는 `onReset` 에 연결.

**보존/재사용** (그대로 또는 이식):
- 디자인 패턴: AppShell, BrandMark, StepNavigator, UserPill, ChatHead, ChatStream, MessageBubble, TypingBubble, Composer, InfoCard, ActionCard(s), StateCard, DocRow/DocChecklist(Sprint 22)
- 이식: `api/client.ts`, `types/api.ts`, `useSession.ts`, ImageLightbox 로직

**신규**:
- CitationList (§3), AskBlock 조합(§2.2), AssessmentBlock 조합(§2.3)

---

## 7. Sprint 20 범위 경계

- **포함**: 위 §1~§6 중 — 골격 이식, ChatMessage 타입별 렌더(user/ask/assessment/loading/error), CitationList 신규, Composer.onSend 배선, rail 1~4 동적.
- **포함(차단 요인 — I3)**: **백엔드 연동 설정**. 신규 앱엔 vite proxy·`.env` 없음. `client.ts:17` 은 `VITE_API_BASE_URL ?? 'localhost:8000/api/v1'` + `credentials:'include'`. 5173→8001(uvicorn) 교차출처. → **vite.config.ts 에 `server.proxy` 추가**(`/api`,`/static` → backend 8001, 기존 frontend 패턴 계승) 또는 `VITE_API_BASE_URL` 설정 + 백엔드 CORS origin/allow_credentials 확인. **이 설정 없으면 모든 API 실패** → Sprint 20 첫 task 에 포함.
- **제외(후속)**: OCR 업로드(`onAttach`)·건강보험 패널 = Sprint 21 / DocChecklist·Review·서류·접수 = Sprint 22 / 법적페이지·접근성 색정책 = Sprint 23.
- **DocChecklist 처리(임시)**: Sprint 20 에선 assessment 의 `next_steps` 를 단순 번호 리스트로. 구조화 서류목록은 Sprint 22 백엔드 신규 후 연결.

---

## 8. 미해결 / 설계 확인 필요
- [x] satisfied/unsatisfied → **체크리스트 행**(아이콘+텍스트, value 없음) 확정.
- [x] ChatHead title — status 매핑(단순) 확정 (§4.2).
- [x] **vite proxy 채택 (확정 2026-06-23)**: `vite.config.ts` `server.proxy` 로 `/api`·`/static` → `http://localhost:8001`(uvicorn 백엔드, PM-18 기준 포트). 기존 frontend 와 동일 방식 — `VITE_API_BASE_URL` 미사용(상대경로 유지로 CORS·쿠키 단순화). 백엔드 CORS `allow_credentials=True` 이미 설정됨(Sprint 14). → Sprint 20 첫 task.
- [ ] 단일 ChatPage 안에서 Welcome/Situation 진입을 어떻게 둘지는 Sprint 21 설계.

> **설계 단계 완료 (2026-06-23)**: 위 §1~§7 + 본 절로 Sprint 20 설계 확정. 남은 [ ] 항목은 Sprint 21 범위. 구현 진입 가능.

## 9. 교차검증 반영 (2026-06-15, design-reviewer)
판정: **조건부 가능 → 수정 반영 완료**. 적용: C1(MessageBubble name/time/role 변환 §1.1) · I1(중간=warning 3색 보존 §2.3) · I2(인용=새 탭 §3) · I3(vite proxy Sprint 20 포함 §7) · I4(onAttach 트리거 §5) · I5(reset 경로 보존 §6) · M1~M5(koTime/aria-label/useSession 추가반환/loading 단일경로/ask disable). 검증 PASS: IconName 전부 실재, useSession 계약·ChatMessage 5타입·Assessment/Ask/Citation 필드 정합.
