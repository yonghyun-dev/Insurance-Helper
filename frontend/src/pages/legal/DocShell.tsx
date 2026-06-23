// 법적/안내 페이지 공통 셸 — ShellHeader + breadcrumb + title/lede/meta + TOC + 본문 + 관련 문서.
import { useEffect, useRef, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Icon } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import FontSizeToggle from './FontSizeToggle';
import s from './legal.module.css';

export interface DocShellProps {
  title: string;
  lede?: string;
  updatedAt?: string;
  badge?: string;
  toc?: { id: string; label: string }[];
  related?: { to: string; label: string }[];
  children: ReactNode;
}

export default function DocShell({ title, lede, updatedAt, badge, toc, related, children }: DocShellProps) {
  const navigate = useNavigate();
  const h1Ref = useRef<HTMLHeadingElement>(null);

  // 페이지 진입 시 제목으로 포커스 이동(스크린리더가 새 문서를 안내).
  useEffect(() => {
    h1Ref.current?.focus();
  }, [title]);

  return (
    <div className={s.shell}>
      <ShellHeader onLogoClick={() => navigate('/app')} rightSlot={<FontSizeToggle />} />
      <main className={s.main}>
        <article className={s.doc}>
          <nav className={s.breadcrumb} aria-label="페이지 위치">
            <Link to="/app">메인</Link>
            <span className={s.breadcrumbSep} aria-hidden="true">/</span>
            <span className={s.breadcrumbCurrent} aria-current="page">{title}</span>
          </nav>

          <h1 className={s.title} tabIndex={-1} ref={h1Ref}>{title}</h1>
          {lede && <p className={s.lede}>{lede}</p>}

          {(updatedAt || badge) && (
            <div className={s.meta}>
              {updatedAt && (
                <span>
                  최종 갱신: <time dateTime={updatedAt}>{updatedAt}</time>
                </span>
              )}
              {badge && <span className={s.metaBadge}>{badge}</span>}
            </div>
          )}

          {toc && toc.length > 0 && (
            <nav className={s.toc} aria-label="이 문서의 목차">
              <div className={s.tocLabel}>목차</div>
              <ol className={s.tocList}>
                {toc.map((t, i) => (
                  <li key={t.id}>
                    <a href={`#${t.id}`}>
                      <span className={s.tocNum}>{String(i + 1).padStart(2, '0')}</span>
                      {t.label}
                    </a>
                  </li>
                ))}
              </ol>
            </nav>
          )}

          {children}

          {related && related.length > 0 && (
            <div className={s.related}>
              <div className={s.relatedLabel}>관련 문서</div>
              <div className={s.relatedList}>
                {related.map((r) => (
                  <Link key={r.to} to={r.to} className={s.relatedLink}>{r.label}</Link>
                ))}
              </div>
            </div>
          )}

          <Link to="/app" className={s.back} aria-label="메인 화면으로 돌아가기">
            <Icon name="chevron-left" size={14} />
            메인으로 돌아가기
          </Link>
        </article>
      </main>
    </div>
  );
}

// 공통 note 콜아웃 (페이지 본문에서 재사용)
export function Note({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className={s.note} role="note">
      <Icon name="information" size={20} className={s.noteIcon} />
      <div>
        <div className={s.noteTitle}>{title}</div>
        <div className={s.noteBody}>{children}</div>
      </div>
    </div>
  );
}
