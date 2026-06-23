# OptionsPanel 컴포넌트 명세서

- 위치 (신규): `frontend/src/components/OptionsPanel.tsx`
- 스프린트: 8.6 (Sprint 6 ask options 의 UX 보강)
- 우선순위: ★★★ (대국민 UX 핵심)
- 관련: [design-system.md](../design-system.md), [ui-spec.md](../ui-spec.md), [ui-states.md](../ui-states.md)

## 1. 목적

**Claude Plan 모드 패턴 도입** — ask 응답의 options 를 메시지 텍스트 블록 안 inline 으로 노출하지 않고, 화면 **하단 중앙 고정 영역** 에 큰 chip 으로 표시. 사용자가 즉시 선택 → 답변 자동 전송. 노인·장애인 포함 대다수 사용자의 선택 부담 감소.

## 2. 사용자 시나리오

1. ask 응답에 `options=['자동차', '화재', '사고질병', '모르겠습니다']` 가 포함됨
2. 메시지 버블은 **질문 텍스트만** 표시 (options 인라인 제거)
3. 화면 하단 중앙에 **`<OptionsPanel>`** 이 fixed 위치로 떠오름 — 4개 chip
4. 사용자가 chip 클릭 → 해당 옵션 텍스트가 ChatInput 에 들어감 + 자동 전송 → OptionsPanel 사라짐
5. 또는 사용자가 ChatInput 에 직접 자유 텍스트 입력해도 됨 (옵션 무시 가능)

## 3. ASCII 와이어프레임

### 3.1 데스크탑

```
┌────────────────────────────────────────────────────────────────┐
│ 보 보험청구심사 어시스턴트                       [Aa] [+ 새 대화] │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  [나]    "차 사고 났는데..."                                    │
│                                                                │
│  [보]    정확한 안내를 위해 다음 정보를 알려주실 수 있나요?      │
│           청구하시는 보험의 종류를 알려주세요.                  │
│           ↑ (메시지 버블 — options 인라인 X)                   │
│                                                                │
│                                                                │
│                                                                │
│         ┌────────────────────────────────────────────────┐     │
│         │ 선택해 주세요                                  │     │
│         │ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │     │
│         │ │ 자동차 │ │  화재  │ │사고질병│ │모르겠습니다│ │     │
│         │ └────────┘ └────────┘ └────────┘ └──────────┘ │     │
│         │            (4 chip — 가로 그리드)               │     │
│         └────────────────────────────────────────────────┘     │
│                ↑ OptionsPanel — 하단 중앙 fixed                │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│ [ 메시지를 입력하세요…                              ][전송]    │
│ 답변은 참고용입니다 · 면책 · 개인정보 · 접근성 · 데이터 출처   │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 모바일 (≤ 480px)

```
┌────────────────────────┐
│ 보 어시스턴트  [Aa] [+] │
├────────────────────────┤
│ [나] "차 사고..."      │
│                        │
│ [보] 청구하시는 보험   │
│       종류를 알려주세요│
│                        │
│                        │
│  ┌──────────────────┐  │
│  │ 선택해 주세요    │  │
│  │ ┌──────────────┐ │  │
│  │ │   자동차     │ │  │
│  │ ├──────────────┤ │  │
│  │ │    화재      │ │  │
│  │ ├──────────────┤ │  │
│  │ │  사고질병    │ │  │
│  │ ├──────────────┤ │  │
│  │ │ 모르겠습니다 │ │  │
│  │ └──────────────┘ │  │
│  └──────────────────┘  │
│  ↑ 세로 stack (모바일) │
├────────────────────────┤
│ [메시지...]      [전송]│
└────────────────────────┘
```

→ 모바일: chip 을 세로 stack. 큰 터치 영역 (최소 44px 높이).

## 4. Props

```tsx
type Props = {
  options: string[];           // backend ask 응답의 options 배열
  onSelect: (option: string) => void;  // chip 클릭 시 → ChatInput 자동 전송 콜백
  visible: boolean;            // 마지막 assistant 응답이 ask 일 때만 true
};

export const OptionsPanel: FC<Props> = ({ options, onSelect, visible }) => { ... };
```

→ **상태 관리**: `useSession` hook 이 마지막 assistant 응답의 `assistant.type === 'ask'` 일 때 `visible=true` 로 셋. 다음 user 메시지 전송 시 `visible=false`.

## 5. 동작 규칙

| 상태 | 동작 |
|:--|:--|
| 마지막 응답이 ask + options 존재 | OptionsPanel 등장 (slide-up fade-in, `--motion-medium`) |
| 마지막 응답이 assessment | OptionsPanel 없음 (visible=false) |
| 사용자가 chip 클릭 | `onSelect(option)` 호출 → ChatInput 에 텍스트 채움 + 자동 전송 + Panel 사라짐 (slide-down fade-out) |
| 사용자가 ChatInput 직접 입력 | OptionsPanel 사라짐 (옵션 무시, 자유 텍스트 응답) |
| `options.length === 0` (자유 답변만 가능) | OptionsPanel 미표시 (visible=false 강제) |
| "모르겠습니다" 클릭 | 일반 option 과 동일하게 텍스트 전송 — extract_slots 가 unknown_slots 머지 (backend) → partial 모드 자연 진입 |

## 6. 시각 (design-system 기반)

### 6.1 위치
```css
.options-panel {
  position: fixed;
  bottom: 120px;  /* ChatInput 위 마진 */
  left: 50%;
  transform: translateX(-50%);
  max-width: min(680px, calc(100vw - 32px));
  z-index: 50;
  padding: var(--space-04);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-default);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
```

### 6.2 chip
- 높이: 최소 44px (터치 친화)
- 폰트: `--text-base` + `--fw-semibold`
- 색: default `--color-bg-secondary` + 텍스트 `--color-text-primary`
- hover: `--color-brand-primary` 배경 + 흰 텍스트
- "모르겠습니다" chip: `--color-bg-warning` (#fdf6e3 노란빛) + 따뜻한 친절 톤
- focus-visible: 4.5:1 대비 ring

### 6.3 transition
- 등장: 200ms ease-out slide-up + fade-in
- 사라짐: 100ms ease-in slide-down + fade-out
- `prefers-reduced-motion: reduce` 일 때 즉시 표시/숨김

## 7. 접근성

- `role="dialog"` + `aria-labelledby="options-panel-title"` + `aria-modal="false"` (메인 화면 차단 X)
- 패널 제목 (`<h2>` 또는 시각 hidden) "선택지" + screen reader 안내
- chip 은 `<button>` 시멘틱 + `aria-label` 명시
- 키보드: Tab 으로 chip 간 이동 + Enter/Space 로 선택 + Esc 로 무시 (panel hide)
- 모바일: 큰 터치 영역 (44x44 px 최소)
- ChatInput 도 fixed 라 OptionsPanel 과 겹치지 않도록 `bottom` 위치 조정 (스크롤 영역에 padding-bottom 추가)

## 8. 컴포넌트 트리 통합

```
App
└─ ChatPage
    ├─ ChatHeader
    │   ├─ FontSizeToggle
    │   ├─ NewSessionButton
    │   └─ DisclaimerBanner
    ├─ MessageList
    │   └─ MessageBubble (ask 메시지 — options 인라인 제거)
    │       └─ AskCard (질문 텍스트만, options 미표시)
    ├─ OptionsPanel ← 신규 (조건부 fixed)
    ├─ ChatInput
    └─ ToastStack
```

→ `useSession` hook 의 `lastAsk` 상태가 `OptionsPanel` 의 `visible` + `options` 를 결정.

## 9. 구현 예시 (TSX 의사 코드)

```tsx
import type { FC } from 'react';

type Props = {
  options: string[];
  onSelect: (option: string) => void;
  visible: boolean;
};

export const OptionsPanel: FC<Props> = ({ options, onSelect, visible }) => {
  if (!visible || options.length === 0) return null;

  return (
    <div
      className="options-panel"
      role="dialog"
      aria-labelledby="options-panel-title"
      aria-modal="false"
    >
      <h2 id="options-panel-title" className="options-panel__title">
        선택해 주세요
      </h2>
      <div className="options-panel__grid">
        {options.map((opt) => {
          const isUnknown = opt === '모르겠습니다';
          return (
            <button
              key={opt}
              type="button"
              className={`options-panel__chip ${isUnknown ? 'options-panel__chip--unknown' : ''}`}
              onClick={() => onSelect(opt)}
              aria-label={`선택: ${opt}`}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
};
```

```tsx
// App.tsx / ChatPage.tsx 통합 예시
const { messages, send, lastAsk } = useSession();
const visible = lastAsk !== null;

const handleSelect = (option: string) => {
  send(option);  // ChatInput 우회 → 직접 send
};

return (
  <>
    <ChatHeader ... />
    <MessageList messages={messages} />
    <OptionsPanel options={lastAsk?.options ?? []} onSelect={handleSelect} visible={visible} />
    <ChatInput onSend={send} />
  </>
);
```

## 10. MessageBubble / AskCard 변경

기존 `AskCard` (또는 메시지 버블 안의 options inline 렌더) **에서 options 제거**. 메시지는 질문 텍스트만.

```tsx
// AskCard 또는 메시지 버블 — 변경 후
export const AskCard: FC<{ ask: AssistantAsk }> = ({ ask }) => (
  <div className="ask-card">
    <p className="ask-card__message">{ask.message}</p>
    {/* options 는 OptionsPanel 이 별도 표시 — 여기서 X */}
  </div>
);
```

→ 인라인 options 가 메시지에 노출됐던 기존 frontend 갱신 필요.

## 11. [확인 필요]

1. **OptionsPanel 위치** — bottom: 120px 가 ChatInput (현재 위치) 와 겹치지 않는지 외부 디자인에서 검증 필요
2. **scroll 영역 padding-bottom** — OptionsPanel 이 떠있을 때 MessageList 마지막 메시지가 가려지지 않게 padding 추가
3. **모바일에서 chip 세로 stack vs 가로 wrap** — 옵션 4개일 때 최적 UX 검증
4. **"모르겠습니다" chip 색상** — 노란 배경이 시각적으로 분리되어 약간 부정적 느낌일 수 있음. 운영자 결정 가능
5. **ChatInput 과의 관계** — chip 클릭 시 ChatInput 에 값 잠시 보였다 자동 전송 vs ChatInput 우회 직접 전송 (현재 권장)
