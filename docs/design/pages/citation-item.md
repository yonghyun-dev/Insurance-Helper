# CitationItem 컴포넌트 명세서 (확장)

- 위치: `frontend/src/components/CitationItem.tsx`
- 스프린트: 8.6 (Sprint 5/7 기반 확장)
- 우선순위: ★★★ (신뢰도 핵심)
- 관련: [design-system.md § 1.3 출처 색상](../design-system.md), [ui-api-flow.md Citation TS 타입](../ui-api-flow.md)

## 1. 목적

**신뢰도 향상** — 약관 인용 시 텍스트 발췌 + 실제 PDF 페이지 캡처본을 **동시에** 표시. 사용자가 "이 답변이 실제 약관의 어디서 왔는지" 시각적으로 즉시 확인. AI 환각 우려 해소.

## 2. 현재 상태 + 문제

- 사용자 외부 작업본 (`frontend/src/components/CitationItem.tsx`) — 텍스트만 표시
- backend 응답 `Citation` 에 `page_image_url` + `pdf_url` 이미 hydrate (Sprint 5 완료 확인됨)
- → frontend 가 이 두 필드를 미활용. 캡처본 노출 안 됨

## 3. 요구사항

매 인용 카드에 다음 3요소가 함께 보여야 한다:

1. **메타** (보험사 · 상품 · 조항 · 페이지) — 기존 유지
2. **PDF 페이지 캡처본** (썸네일 — `page_image_url`)
3. **약관 텍스트 발췌** (`text` — 인용된 조항 본문)

## 4. ASCII 와이어프레임

### 4.1 데스크탑 (확장 화면)

```
┌────────────────────────────────────────────────────────────────────┐
│ ▌한화손해보험 · 개인용자동차보험 · 제24조 ③       [📄 원본 PDF 보기 ↗]│
│ ─────────────────────────────────────────────────────────────────  │
│ ┌─────────────────┐ ┌───────────────────────────────────────────┐ │
│ │                 │ │ "③ 보험회사는 피보험자가 사고가 발생한 사실을  │ │
│ │  [PDF 페이지    │ │  안 날부터 60일 이내에 회사에 통지하지 아니한 │ │
│ │   캡처 썸네일]  │ │  때에는 그로 말미암아 늘어난 손해에 대하여... │ │
│ │   p.19          │ │  보험금을 지급하지 아니합니다."              │ │
│ │  (클릭 시       │ │                                            │ │
│ │   확대)         │ │  ─ 약관 본문 발췌 (p.19)                  │ │
│ └─────────────────┘ └───────────────────────────────────────────┘ │
│ (캡처본 vs 텍스트 — 동일 페이지의 동일 조항. 사용자가 비교 가능)   │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 모바일 (≤ 480px)

```
┌────────────────────────────────┐
│ ▌한화 · 개인용자동차 · 제24조 ③ │
│ ───────────────────────────── │
│ ┌────────────────────────────┐ │
│ │   [PDF 페이지 캡처 썸네일]  │ │
│ │   p.19  (탭하면 확대)       │ │
│ └────────────────────────────┘ │
│ ┌────────────────────────────┐ │
│ │ "③ 보험회사는 피보험자가    │ │
│ │  사고 발생일로부터 60일..."  │ │
│ │  ─ 약관 본문 발췌           │ │
│ └────────────────────────────┘ │
│ [📄 원본 PDF 보기 ↗]            │
└────────────────────────────────┘
```

→ 모바일: 캡처 → 텍스트 → 원본 링크 세로 stack.

## 5. Props (변경)

```tsx
import type { FC } from 'react';
import type { Citation } from '../types/api';

type Props = { citation: Citation };

// Citation 타입 (이미 ui-api-flow.md 에 정의):
//   - chunk_id / insurer / product / version / doc_type
//   - clause / sub_no / text / page
//   - page_image_url?: string | null  ← Sprint 5 backend hydrate
//   - pdf_url?: string | null         ← Sprint 5 backend hydrate

export const CitationItem: FC<Props> = ({ citation: c }) => { ... };
```

→ Props 변경 없음. 기존 `Citation` 타입 그대로. 단 `page_image_url` 과 `pdf_url` 을 실제 렌더에 사용.

## 6. 동작 규칙

| 상태 | 표시 |
|:--|:--|
| `page_image_url` 존재 | 썸네일 표시. 클릭 시 → lightbox 모달 또는 새 탭 (`pdf_url#page={page}`) |
| `page_image_url` null | 썸네일 영역 skeleton (회색 박스 + "이미지 변환 중") 또는 영역 자체 hide |
| `pdf_url` 존재 | "📄 원본 PDF 보기 ↗" 버튼 — 새 탭 (`pdf_url#page={page}`) |
| `pdf_url` null | 버튼 hide (외부 PDF 등 — Sprint 9~10) |
| `text` 누락 | (백엔드 schema 상 필수라 발생 X) |

## 7. 시각 (design-system 기반)

- 좌측 색 라인: 출처 종류별 (현재는 약관만 → `--color-source-terms` 파랑 `#3b82f6`)
- 캡처 영역 width: 데스크탑 200px / 모바일 100%
- 캡처 영역 비율: 약관 PDF 페이지 비율 (A4 — 약 1:1.414)
- 텍스트 영역 — 인용은 `font-style: italic` + 좌측 quote 마크 (`“`)
- 캡처 hover: subtle elevation (box-shadow)
- 캡처 클릭: 확대 lightbox (`<dialog>` 또는 modal — 풀스크린)

## 8. 접근성

- 캡처 `<img>` 의 `alt`: "{insurer} {product} {clause} 약관 page {page} 캡처"
- 캡처 wrapper `<a>` (또는 `<button>`) — `aria-label` 명시
- 외부 PDF 링크: `target="_blank" rel="noopener noreferrer"` + `aria-label` "{clause} 원본 PDF 새 탭으로 열기"
- 텍스트 영역 — 발췌임을 명시 (`<blockquote>` 시멘틱 + `cite` 속성)

## 9. 구현 예시 (TSX 의사 코드)

```tsx
export const CitationItem: FC<Props> = ({ citation: c }) => {
  const pageImg = c.page_image_url;
  const pdfHref = c.pdf_url ? `${c.pdf_url}#page=${c.page}` : null;

  return (
    <div className="cite cite--source-terms">
      <div className="cite__head">
        <span className="cite__insurer">{c.insurer}</span>
        <span className="cite__sep">·</span>
        <span className="cite__product">{c.product}</span>
        <span className="cite__sep">·</span>
        <span className="cite__clause">
          {c.clause}{c.sub_no ? ` ${c.sub_no}` : ''}
        </span>
        {pdfHref && (
          <a
            className="cite__pdf-link"
            href={pdfHref}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${c.clause} 원본 PDF 새 탭으로 열기`}
          >
            📄 원본 PDF
          </a>
        )}
      </div>
      <div className="cite__body">
        {pageImg && (
          <a
            className="cite__image-link"
            href={pdfHref || pageImg}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`${c.clause} 약관 page ${c.page} 캡처 확대`}
          >
            <img
              src={pageImg}
              alt={`${c.insurer} ${c.product} ${c.clause} 약관 page ${c.page} 캡처`}
              className="cite__image"
              loading="lazy"
            />
            <span className="cite__page-badge">p.{c.page}</span>
          </a>
        )}
        <blockquote className="cite__text" cite={pdfHref || undefined}>
          {c.text}
        </blockquote>
      </div>
    </div>
  );
};
```

## 10. CSS 토큰 (design-system 활용)

```css
.cite {
  border-left: 3px solid var(--color-source-terms); /* 파랑 — Sprint 9~10 으로 확장 시 source 별 분기 */
  background: var(--color-bg-secondary);
  border-radius: 8px;
  padding: var(--space-04);
  margin-bottom: var(--space-03);
}

.cite__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-02);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-03);
}

.cite__pdf-link {
  margin-left: auto;
  /* primary 컬러 */
}

.cite__body {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: var(--space-04);
}

@media (max-width: 480px) {
  .cite__body {
    grid-template-columns: 1fr; /* 세로 stack */
  }
}

.cite__image {
  width: 100%;
  height: auto;
  border: 1px solid var(--color-border-default);
  border-radius: 4px;
  cursor: zoom-in;
  transition: box-shadow var(--motion-medium);
}

.cite__image:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.cite__page-badge {
  /* 캡처 좌하단 작은 페이지 표시 */
}

.cite__text {
  font-style: italic;
  border-left: 2px solid var(--color-border-default);
  padding-left: var(--space-03);
  color: var(--color-text-primary);
  line-height: 1.6;
  margin: 0;
}
```

## 11. 향후 (Sprint 9~10 외부 데이터 통합 시)

`Citation` 타입에 `source: 'terms' | 'law' | 'precedent' | 'standard' | 'disease' | 'calc'` 추가 → 좌측 색 라인을 source 별 분기 (design-system § 1.3).

```tsx
const sourceColor = `cite--source-${c.source ?? 'terms'}`;
return <div className={`cite ${sourceColor}`}>...</div>;
```

## 12. [확인 필요]

1. 캡처 클릭 시 — lightbox 모달 (별 dialog) vs 새 탭 (PDF 직접) — 기본 권장: 새 탭 (단순)
2. PDF 캡처 미지원 보험사 (Sprint 9~10 외부 데이터) — 텍스트만 + skeleton 영역 또는 그냥 텍스트만 표시 — PM 결정 필요
3. 캡처 영역 가로 비율 (200px) — 모바일에서 너무 작을 수 있음. CSS 미세조정 필요
