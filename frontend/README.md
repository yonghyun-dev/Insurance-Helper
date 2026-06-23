# 보험길잡이 — Insurance Helper React Design System

원본 `보험상담 디자인 시스템 (Carbon-based)` HTML/CSS 디자인 시스템을 React + TypeScript 로 1:1 포팅한 결과입니다.

- 토큰 (`tokens.css`) 은 원본 `colors_and_type.css` 를 한 글자도 안 바꾸고 그대로 가져왔습니다.
- 컴포넌트 클래스명은 원본 BEM (`btn--primary`, `bubble__avatar--bot`, `composer__send` 등) 을 그대로 유지하고 CSS Modules 로 스코프합니다.
- IBM Carbon Design System v11 White theme · IBM Plex Sans KR · sharp corners · 한국어 공공 서비스 톤.

---

## Quick start

```bash
npm install
npm run dev
```

기본 포트는 `http://localhost:5173`. 두 페이지가 있어요.

- `/showcase` — 전체 디자인 시스템 데모 (color, type, button, field, ...).
- `/chat` — 보험 상담 챗 화면 (스트리밍 답변, 타이핑 인디케이터, 인용 카드, 빠른 응답).

## Scripts

- `npm run dev` — Vite dev 서버
- `npm run build` — 타입체크 + 프로덕션 번들
- `npm run preview` — 빌드 결과 미리보기
- `npm run typecheck` — TS 컴파일만 (산출물 없음)

---

## 프로젝트 구조

```
src/
├── styles/                  ← 글로벌 CSS
│   ├── tokens.css           ← 원본 colors_and_type.css 의 :root 그대로
│   ├── base.css             ← reset + html/body/h1-h6/p/a/code
│   └── utilities.css        ← .ty-* 타입 유틸리티
│
├── design-system/           ← 디자인 시스템 (토큰 + 프리미티브 + 패턴)
│   ├── components/          ← 재사용 가능한 Carbon 프리미티브
│   │   ├── Icon/            ← <Icon name="send" size={16} /> SVG sprite wrapper
│   │   ├── Button/          ← btn--{primary|secondary|tertiary|ghost|danger}, btn--{sm|md|lg|xl|2xl}, btn--icon, btn--with-icon
│   │   ├── Field/           ← text input + label + helper + error
│   │   ├── Checkbox/        Radio/        Toggle/
│   │   ├── Tag/             Notification/ Tile/
│   │   ├── Accordion/       Tabs/         Select/
│   │   └── Modal/           Avatar/
│   │
│   ├── patterns/            ← 도메인 특화 합성 패턴
│   │   └── chat/            ← 보험 상담 LLM 챗 (시스템의 주 결과물)
│   │       ├── chat.module.css   ← 원본 chat.css 통째로
│   │       ├── AppShell.tsx, BrandMark.tsx, StepNavigator.tsx, UserPill.tsx
│   │       ├── ChatHead.tsx, ChatStream.tsx, MessageBubble.tsx
│   │       ├── InfoCard.tsx, DocList.tsx, QuickReplies.tsx
│   │       ├── FeedbackRow.tsx, TypingBubble.tsx, StreamingCaret.tsx
│   │       ├── AttachChip.tsx, Composer.tsx
│   │       └── mockMessages.tsx  ← 시드 대화 픽스처
│   │
│   ├── hooks/               ← 시스템 hook
│   │   ├── useStreamingText.ts   ← 18ms/char 글자 단위 스트리밍
│   │   ├── useAutoScroll.ts      ← stream 영역 자동 스크롤
│   │   └── useAutoResize.ts      ← composer textarea 자동 높이
│   │
│   └── index.ts             ← 프리미티브 배럴 export
│
├── pages/
│   ├── ShowcasePage.tsx     ← /showcase (원본 carbon-components/index.html 포팅)
│   └── ChatPage.tsx         ← /chat (원본 insurance-chat/index.html 포팅)
│
├── App.tsx                  ← 라우터 + 상단 nav
└── main.tsx                 ← 진입점 (글로벌 CSS import 순서: tokens → base → utilities)

public/
├── icons/carbon-icons.svg   ← Carbon icon sprite (29개 심볼)
└── assets/logo*.png         ← 보험길잡이 로고
```

**import 컨벤션**:
- 프리미티브: `import { Button, Field, Modal } from '@/design-system'` (배럴)
- 챗 패턴: `import Composer from '@/design-system/patterns/chat/Composer'` (직접 경로)
- 시스템 훅: `import { useStreamingText } from '@/design-system/hooks/useStreamingText'`

## 디자인 시스템 사용

```tsx
import { Button, Field, Notification, Modal } from './design-system';

<Button variant="primary" withIcon>상담 시작 <Icon name="arrow-right" size={16} /></Button>
<Field label="이름" helper="실명을 입력해 주세요." />
<Notification kind="success" title="저장되었습니다">마이페이지에서 다시 열람할 수 있습니다.</Notification>
```

토큰을 컴포넌트 외부에서 쓸 때:

```tsx
const blue60 = 'var(--blue-60)';      // CSS 변수 그대로 활용
```

## 절대 금지 (원본 디자인 가이드와 동일)

- 둥근 모서리 — 토글 트랙과 아바타 제외. `border-radius > 0` 사용 금지.
- 이모지 — 한국 공공 서비스 톤에 맞지 않음.
- Blue 60 외의 보조 브랜드 컬러 추가 금지.
- Bold 700+ 디스플레이 헤딩 — 디스플레이는 Light 300 / Regular 400.
- 인공적 그림자 — 카드는 테두리 1px 로 분리.

## 알려진 한계

- 다크 모드 미포함 (원본도 동일).
- 챗 페이지의 음성 입력 버튼은 미구현.
- 모바일 < 768px 햄버거 메뉴 미구현.
