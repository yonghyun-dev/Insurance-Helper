import type { ReactNode } from 'react';
import Icon from '../../components/Icon/Icon';
import FontSizeToggle from '../../../pages/legal/FontSizeToggle';
import s from './ShellHeader.module.css';

export interface ShellHeaderProps {
  onLogoClick?: () => void;
  rightSlot?: ReactNode;
  logoSrc?: string;
}

export default function ShellHeader({
  onLogoClick,
  rightSlot,
  logoSrc = '/assets/logo-mark.svg',
}: ShellHeaderProps) {
  return (
    <header className={s.head}>
      <button type="button" className={s.brand} onClick={onLogoClick}>
        <img src={logoSrc} alt="보험길잡이" />
        <span className={s.brandWord}>
          <span className={s.brandAccent}>보험</span>길잡이
        </span>
        <span className={s.brandTag}>대국민 보험 도우미</span>
      </button>
      <div className={s.right}>
        {/* Sprint 34 — 글자 크기 토글을 전 페이지 헤더에 일관 노출(노인 접근성). */}
        <FontSizeToggle />
        {rightSlot ?? (
          <>
            <button type="button" className={s.link}>
              <Icon name="information" size={14} />
              자주 묻는 질문
            </button>
            <button type="button" className={s.link}>
              <Icon name="information" size={14} />
              상담 전화 1234-5678
            </button>
          </>
        )}
      </div>
    </header>
  );
}
