# 디자인 시스템 (대국민 서비스 단계)

- 작성일: 2026-05-25
- 스프린트: 8 (PoC → 대국민 서비스 전환)
- 관련: [ui-spec.md](ui-spec.md), [ui-states.md](ui-states.md), [pages/](pages/)

## 0. 핵심 원칙

| 원칙 | 의미 |
|:--|:--|
| **신뢰성 시각화** | 출처 (약관/법령/판례/표준) 가 시각적으로 명확히 구분 |
| **친절·차분** | 보험 청구는 사용자에게 스트레스 상황 — 화려한 색·강한 대비 회피, 따뜻한 톤 |
| **접근성 우선** | WCAG AA — 노인·장애인 포함. 폰트 토글·키보드 only·스크린리더 |
| **법적 책임 명시** | 모든 화면에 면책 배너. 청구 가능성은 보험사 최종 결정 |
| **모바일 우선** | 320px ~ — 사용자 대다수 스마트폰 접근 가정 |

## 1. 컬러 토큰

### 1.1 의미 색상

| 토큰 | Light Mode | Dark Mode (Sprint 11+) | 용도 |
|:--|:--|:--|:--|
| `--color-bg-primary` | `#ffffff` | `#0f1419` | 페이지 배경 |
| `--color-bg-secondary` | `#f7f8fa` | `#1a2027` | 카드 배경 |
| `--color-bg-elevated` | `#ffffff` | `#252d3a` | 모달/드롭다운 |
| `--color-text-primary` | `#1a1a1a` | `#e6e8ec` | 본문 |
| `--color-text-secondary` | `#5a6068` | `#9aa1ab` | 보조 (날짜, 메타) |
| `--color-text-disabled` | `#a8aeb8` | `#5a6068` | 비활성 |
| `--color-border-default` | `#e5e7eb` | `#374151` | 경계선 |
| `--color-border-focus` | `#0070f3` | `#3b82f6` | 포커스 ring (키보드 only 필수) |
| `--color-brand-primary` | `#0070f3` | `#3b82f6` | 헤더 아바타·CTA |
| `--color-brand-hover` | `#0058c5` | `#2563eb` | 버튼 hover |

### 1.2 가능성 등급 색상 (assess--high/mid/low)

| 등급 | 메인 색 | 배경 | 의미 |
|:--|:--|:--|:--|
| 높음 (HIGH) | `#10a37f` (차분한 녹색) | `#e8f6f1` | 충족 조건 우세 |
| 중간 (MID) | `#f0b429` (따뜻한 주황) | `#fdf6e3` | 추가 자료 필요 |
| 낮음 (LOW) | `#9ca3af` (회색) | `#f1f2f4` | 충족 조건 미흡 — **빨강 금지 (사용자 충격 회피)** |
| 추정 (partial badge) | `#f0b429` | `#fdf6e3` | Sprint 6 — "추정" 칩 |

### 1.3 출처 색상 (Sprint 9~10 외부 데이터 등장)

각 출처에 다른 색 부여 — 사용자가 출처 종류 즉시 인지.

| 출처 | 색상 | 배경 | 아이콘 (lucide-react 추천) |
|:--|:--|:--|:--|
| 약관 (Chroma + Neo4j RAG) | `#3b82f6` 파랑 | `#eff6ff` | `FileText` |
| 법령 (법령정보센터) | `#7c3aed` 보라 | `#f5f3ff` | `Scale` |
| 판례·분쟁사례 (금감원) | `#8b5cf6` 진보라 | `#f5f3ff` | `Gavel` |
| 표준 (손보협회 과실비율) | `#06b6d4` 청록 | `#ecfeff` | `LayoutGrid` |
| 진단코드 (HIRA) | `#ec4899` 분홍 | `#fdf2f8` | `HeartPulse` |
| 계산 (deterministic) | `#64748b` 회색 | `#f1f5f9` | `Calculator` |

→ 인용 카드 (`CitationItem`) 좌측에 색 라인 (`border-left: 3px solid {color}`) 으로 구분.

### 1.4 상태 색상

| 상태 | 색상 | 배경 | 용도 |
|:--|:--|:--|:--|
| Success | `#10a37f` | `#e8f6f1` | 검증 통과 |
| Warning | `#f0b429` | `#fdf6e3` | 추정/경고 |
| Error | `#dc2626` | `#fee2e2` | 4xx/5xx (drastic 사용 금지 — toast 만) |
| Info | `#0070f3` | `#eff6ff` | 일반 안내 |

### 1.5 색 대비 (WCAG AA 검증)

- 본문 text vs bg: **4.5:1 이상**
- 큰 글씨 (18pt+): **3:1 이상**
- UI 컴포넌트 (버튼·아이콘) vs bg: **3:1 이상**
- 추정 배지 (assess--partial-badge) 의 노란색 (#f0b429) vs 본문 검정 (#1a1a1a): **5.8:1 — 통과**

## 2. 타이포그래피

### 2.1 폰트 패밀리

- 기본: `Pretendard, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- 코드/숫자: `SF Mono, Consolas, Monaco, monospace` (인용 텍스트 안 조항 번호 등)

### 2.2 폰트 크기 토큰 (사용자 토글 — 대/중/소)

| 토큰 | 소 (`fs--small`) | 중 (`fs--medium`, 기본) | 대 (`fs--large` — 노인용) |
|:--|:--|:--|:--|
| `--text-xs` | 11px | 12px | 14px |
| `--text-sm` | 13px | 14px | 16px |
| `--text-base` | 14px | 16px | 18px |
| `--text-lg` | 16px | 18px | 22px |
| `--text-xl` | 18px | 22px | 26px |
| `--text-2xl` | 22px | 26px | 32px |
| `--text-3xl` | 28px | 32px | 40px |

→ `<html class="fs--large">` 으로 토글. CSS 변수 재할당으로 전체 페이지 자동 확대.

→ **모바일 최소 16px** (iOS 자동 zoom 회피 기준).

### 2.3 폰트 굵기

| 토큰 | 값 | 용도 |
|:--|:--|:--|
| `--fw-regular` | 400 | 본문 |
| `--fw-medium` | 500 | 강조 |
| `--fw-semibold` | 600 | 헤딩, 칩 |
| `--fw-bold` | 700 | 가능성 등급 라벨 |

### 2.4 행간

- 본문: `line-height: 1.6` (한국어 가독성 — 영문 1.5 보다 약간 넓게)
- 헤딩: `line-height: 1.3`

## 3. 간격 시스템

8px 그리드 기반.

| 토큰 | 값 |
|:--|:--|
| `--space-01` | 4px |
| `--space-02` | 8px |
| `--space-03` | 12px |
| `--space-04` | 16px |
| `--space-05` | 24px |
| `--space-06` | 32px |
| `--space-07` | 48px |
| `--space-08` | 64px |

## 4. 컴포넌트 변형 (variants)

### 4.1 Button

| variant | 용도 | 색상 |
|:--|:--|:--|
| `primary` | 주요 액션 (메시지 전송) | `--color-brand-primary` |
| `secondary` | 보조 (새 대화) | 테두리만 |
| `ghost` | 액션 (디버그 토글) | 배경 없음, hover 시만 표시 |
| `danger` | 폐기·삭제 (해당 없음 — PoC) | — |

**상태**: default / hover / active / disabled / focus-visible.
**키보드**: tab 으로 focus 가능, `focus-visible` ring 4.5:1 대비.

### 4.2 Badge (Chip)

| variant | 용도 |
|:--|:--|
| `level-high` / `level-mid` / `level-low` | 가능성 등급 |
| `confidence-partial` | "추정" — Sprint 6 |
| `source-terms` / `source-law` / `source-precedent` / `source-standard` / `source-disease` / `source-calc` | Sprint 9~10 외부 출처 |
| `status-success` / `status-warning` / `status-error` / `status-info` | 일반 상태 |

### 4.3 Card

| variant | 용도 |
|:--|:--|
| `assessment` | AssessmentCard — 메인 응답 카드 |
| `citation` | CitationItem — 인용 1건 (출처별 좌측 색 라인) |
| `calculator` | CalcResultCard (Sprint 10) — 보험금 산정 표 |
| `info` | 일반 안내 박스 (P-3 접근성 페이지 등) |

### 4.4 Toast

| variant | 용도 |
|:--|:--|
| `info` | 일반 안내 |
| `success` | 완료 |
| `warning` | 추정 모드 진입 등 |
| `error` | 4xx/5xx |
| `rate-limit` | 429 — 재시도까지 카운트다운 표시 |
| `circuit-open` | 503 — "법령 데이터 일시 조회 불가, 약관 기준만 적용" 식 |

자동 사라짐: error/warning 8s / 그 외 4s. 닫기 버튼 + ARIA `role="alert"`.

### 4.5 Modal / Drawer

| variant | 용도 |
|:--|:--|
| `terms-consent` | 최초 약관 동의 (P-5, Sprint 11) |
| `font-size-toggle` | 접근성 — 폰트 크기 토글 |
| `slot-inspector` | 디버그 모드 (기존) |

## 5. 접근성 (WCAG AA)

### 5.1 의무 사항

- 모든 interactive 요소에 `aria-label`
- 모든 form 입력에 `<label>` 또는 `aria-labelledby`
- 메시지 영역에 `role="log"` + `aria-live="polite"`
- 면책 문구에 `role="note"`
- 모달은 `role="dialog"` + `aria-modal="true"` + focus trap
- `prefers-reduced-motion: reduce` 일 때 transition `none`

### 5.2 키보드

- Tab 순서: 헤더 → 메시지 영역 → 입력창 → 전송 버튼 → 보조 액션
- `Esc` 로 모달 닫기
- `Ctrl/Cmd + K` 새 대화 시작 (선택)
- 입력창 `Enter` 전송 / `Shift+Enter` 줄바꿈 (기존)

### 5.3 스크린리더

- AssessmentCard `aria-label`: 가능성 + (추정) + 충족/미충족 개수
- CitationItem `aria-label`: 출처 종류 + 보험사·상품·조항 + 페이지
- Toast `role="alert"` + `aria-live="assertive"` (error) / `"polite"` (info)

### 5.4 폰트 크기 토글 (D-3)

헤더 우측 끝에 `<FontSizeToggle>` 버튼 (3 state — 소/중/대). `localStorage["fontSize"]` 영속. 본 페이지 [legal-accessibility.md](pages/legal-accessibility.md) 에 상세 명세.

### 5.5 색 대비 자동 검증

- 빌드 시 axe-core / lighthouse CI (Sprint 11 옵션)
- 4.5:1 미달 컴포넌트 발견 시 빌드 실패

## 6. 모바일 / 반응형

| Breakpoint | 폭 | 변화 |
|:--|:--|:--|
| `--bp-sm` | 320px | 최소 폭. 모든 페이지 동작 보장 |
| `--bp-md` | 768px | 헤더에 사이드 메뉴 (선택) |
| `--bp-lg` | 1024px | 슬롯 인스펙터를 우측 사이드바로 (디버그) |
| `--bp-xl` | 1280px | 콘텐츠 영역 최대 폭 760px 중앙 정렬 |

→ Tailwind 기준 `sm: / md: / lg: / xl:` prefix 와 매칭. 또는 React 컴포넌트 자체 미디어쿼리.

## 7. 모션·트랜지션

| 토큰 | 시간 | 곡선 | 용도 |
|:--|:--|:--|:--|
| `--motion-fast` | 100ms | `ease-out` | 버튼 hover |
| `--motion-medium` | 200ms | `ease-in-out` | 카드 등장 |
| `--motion-slow` | 400ms | `ease-out` | 모달 등장 |
| `--motion-skeleton` | 1.5s | `linear infinite` | 로딩 skeleton |

`@media (prefers-reduced-motion: reduce)` 일 때 모두 `0ms`.

## 8. 반드시 따라야 할 톤·매너

| 항목 | 가이드 |
|:--|:--|
| 어조 (Sprint 7 톤 정책) | 친절체·존댓말 ("~안내드립니다" / "~드리겠습니다"). 책임 떠넘기는 명령형 금지 |
| 단어 | 보험사 정식 한글명 (한화손해보험 / 삼성화재). 영문 약자 (KB/DB) 금지 |
| 숫자·금액 | 천 단위 콤마. 금액은 "원" 명시 (예: 1,500,000원) |
| 날짜 | YYYY년 M월 D일 (한국식). ISO `YYYY-MM-DD` 는 디버그 모드만 |
| 면책 | 모든 페이지에 영구 표시. 흐릿한 회색 (`--color-text-secondary`) + 작은 글씨 |

## 9. 이 문서의 변경 책임

- PM 이 결정 → 본 문서 갱신 → ui-spec.md / pages/* 갱신 → 외부 Claude 디자인 작업 입력 자료로 사용
- 외부 디자인 결과물은 사용자가 `frontend/src/` 에 직접 배치
- design-reviewer 가 본 문서와 실제 frontend 일관성 검증
