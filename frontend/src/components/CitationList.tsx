// Sprint 20 — 약관 인용 컴포넌트 (신규, 디자인 시스템 스타일).
// 기존 frontend CitationItem/CitationList 의 로직을 새 디자인으로 재구현.
// - 헤더: 보험사 · 상품 · 조항(+sub_no) + 원본 PDF 링크(#page, 새 탭)
// - page_image_url 썸네일은 새 탭으로 열기 (라이트박스 아님 — 사용자 첨부 전용)
// - 첫 1건 펼침, 나머지 토글
import { useState } from 'react';
import { Icon } from '../design-system/components/Icon';
import type { Citation } from '../types/api';
import s from './CitationList.module.css';

// 약관 청크는 Document Parse 가 마크다운 표(| a | b |)로 파싱했는데 줄바꿈이 평탄화되어
// GFM 표로 렌더되지 않는다. 파이프/구분선을 가독 구분점으로 정리해 원본 노출을 막는다.
function cleanClauseText(t: string): string {
  return t
    .replace(/\|(?:\s*:?-{2,}:?\s*\|)+/g, ' ') // 표 구분선 셀(| --- | --- |) 제거
    .replace(/\s*\|\s*/g, ' · ') // 남은 셀 파이프 → 구분점
    .replace(/(?:\s*·\s*){2,}/g, ' · ') // 연속 구분점 축약
    .replace(/^\s*·\s*|\s*·\s*$/g, '') // 앞뒤 구분점 제거
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function CitationCard({ c, hideThumb }: { c: Citation; hideThumb?: boolean }) {
  // 조항번호(clause)가 없는 청크(별표 등)면 해당 조각을 생략해 " · " 잔존 방지.
  const clauseLabel = [c.clause, c.sub_no].filter(Boolean).join(' ');
  const sourceLabel = [c.insurer, c.product, clauseLabel].filter(Boolean).join(' · ');
  const pdfHref = c.pdf_url ? `${c.pdf_url}#page=${c.page}` : null;
  const imgHref = pdfHref ?? c.page_image_url ?? undefined;

  return (
    <li className={s.card}>
      <div className={s.head}>
        <span className={s.source}>{sourceLabel}</span>
        {pdfHref ? (
          <a className={s.pdfLink} href={pdfHref} target="_blank" rel="noopener noreferrer">
            <Icon name="document" size={14} /> 원본 PDF
          </a>
        ) : null}
      </div>

      {/* hideThumb: 메인 채팅은 왼쪽 프리뷰 패널이 원문을 크게 보여주므로 카드 썸네일 생략 */}
      {c.page_image_url && !hideThumb ? (
        <a
          className={s.thumb}
          href={imgHref}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`약관 ${c.page}페이지 원본 보기`}
        >
          <img src={c.page_image_url} alt={`약관 ${c.page}페이지`} loading="lazy" />
          <span className={s.page}>p.{c.page}</span>
        </a>
      ) : null}

      <blockquote className={s.text} cite={pdfHref ?? undefined}>
        {cleanClauseText(c.text)}
        {!c.page_image_url || hideThumb ? (
          <span className={s.pageSuffix}> p.{c.page}</span>
        ) : null}
      </blockquote>
    </li>
  );
}

// 컴팩트(대화형) 출처 링크 1건 — 박스/원문 없이 "📄 보험사·상품·조항". 원문은 왼쪽 패널.
function SourceLink({ c }: { c: Citation }) {
  const clauseLabel = [c.clause, c.sub_no].filter(Boolean).join(' ');
  const label = [c.insurer, c.product, clauseLabel].filter(Boolean).join(' · ');
  const href = c.pdf_url ? `${c.pdf_url}#page=${c.page}` : (c.page_image_url ?? undefined);
  return (
    <a
      className={s.sourceLink}
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      title="원본 PDF 보기"
    >
      <Icon name="document" size={13} />
      <span>{label}</span>
    </a>
  );
}

export default function CitationList({
  citations,
  hideThumb,
  compact,
}: {
  citations: Citation[];
  hideThumb?: boolean;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!citations || citations.length === 0) return null;
  const [first, ...rest] = citations;

  // 대화형(compact): 근거 약관을 작은 출처 링크로만. 원문·하이라이트는 왼쪽 패널이 담당.
  if (compact) {
    const shown = expanded ? citations : [first];
    return (
      <div className={s.sources}>
        <span className={s.sourcesLabel}>근거 약관</span>
        {shown.map((c) => (
          <SourceLink key={c.chunk_id} c={c} />
        ))}
        {rest.length > 0 ? (
          <button
            type="button"
            className={s.sourcesToggle}
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? '접기' : `+${rest.length}`}
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <section className={s.wrap} role="region" aria-label="약관 인용">
      <ul className={s.list}>
        <CitationCard c={first} hideThumb={hideThumb} />
        {expanded
          ? rest.map((c) => <CitationCard key={c.chunk_id} c={c} hideThumb={hideThumb} />)
          : null}
      </ul>
      {rest.length > 0 ? (
        <button
          type="button"
          className={s.toggle}
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? `인용 ${rest.length}건 접기` : `+ 인용 ${rest.length}건 더 보기`}
        </button>
      ) : null}
    </section>
  );
}
