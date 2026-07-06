// Sprint 20 — 약관 인용 컴포넌트 (신규, 디자인 시스템 스타일).
// 기존 frontend CitationItem/CitationList 의 로직을 새 디자인으로 재구현.
// - 헤더: 보험사 · 상품 · 조항(+sub_no) + 원본 PDF 링크(#page, 새 탭)
// - page_image_url 썸네일은 새 탭으로 열기 (라이트박스 아님 — 사용자 첨부 전용)
// - 첫 1건 펼침, 나머지 토글
import { useState } from 'react';
import { Icon } from '../design-system/components/Icon';
import type { Citation } from '../types/api';
import s from './CitationList.module.css';

function CitationCard({ c }: { c: Citation }) {
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

      {c.page_image_url ? (
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
        {c.text}
        {!c.page_image_url ? ` — p.${c.page}` : ''}
      </blockquote>
    </li>
  );
}

export default function CitationList({ citations }: { citations: Citation[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!citations || citations.length === 0) return null;
  const [first, ...rest] = citations;

  return (
    <section className={s.wrap} role="region" aria-label="약관 인용">
      <ul className={s.list}>
        <CitationCard c={first} />
        {expanded ? rest.map((c) => <CitationCard key={c.chunk_id} c={c} />) : null}
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
