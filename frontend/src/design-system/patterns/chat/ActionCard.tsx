import type { ReactNode } from 'react';
import clsx from 'clsx';
import Icon, { type IconName } from '../../components/Icon/Icon';
import s from './ActionCard.module.css';

export interface ActionCardProps {
  icon: IconName;
  title: ReactNode;
  sub?: ReactNode;
  onClick?: () => void;
}

export interface ActionCardsProps {
  columns?: 1 | 2;
  children: ReactNode;
}

export function ActionCards({ columns = 1, children }: ActionCardsProps) {
  return (
    <div className={clsx(s.cards, columns === 2 && s['cards--2'])}>
      {children}
    </div>
  );
}

export default function ActionCard({ icon, title, sub, onClick }: ActionCardProps) {
  return (
    <button type="button" className={s.card} onClick={onClick}>
      <span className={s.ico}>
        <Icon name={icon} size={18} />
      </span>
      <span className={s.body}>
        <span className={s.title}>{title}</span>
        {sub ? <span className={s.sub}>{sub}</span> : null}
      </span>
      <span className={s.arrow}>
        <Icon name="chevron-right" size={16} />
      </span>
    </button>
  );
}
