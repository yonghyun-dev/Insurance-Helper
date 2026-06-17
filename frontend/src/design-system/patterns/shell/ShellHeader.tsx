import type { ReactNode } from 'react';
import Icon from '../../components/Icon/Icon';
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
