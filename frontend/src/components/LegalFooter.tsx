// 법적 고지 푸터 — 면책/개인정보/출처/접근성 페이지로 진입.
import { Link } from 'react-router-dom';
import s from './LegalFooter.module.css';

const LINKS = [
  { to: '/legal/disclaimer', label: '면책 및 이용약관' },
  { to: '/legal/privacy', label: '개인정보 처리방침' },
  { to: '/legal/sources', label: '데이터 출처' },
  { to: '/legal/accessibility', label: '접근성 안내' },
];

export default function LegalFooter() {
  return (
    <footer className={s.footer}>
      <nav className={s.links} aria-label="법적 고지">
        {LINKS.map((l) => (
          <Link key={l.to} to={l.to} className={s.link}>{l.label}</Link>
        ))}
      </nav>
      <p className={s.copy}>
        본 서비스는 청구 가능성 안내 도구이며 보험사의 최종 판단을 대체하지 않습니다. · 팀 디포커스 AI
      </p>
    </footer>
  );
}
