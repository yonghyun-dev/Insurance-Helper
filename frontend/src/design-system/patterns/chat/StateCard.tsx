import type { ReactNode } from 'react';
import clsx from 'clsx';
import Icon, { type IconName } from '../../components/Icon/Icon';
import s from './StateCard.module.css';

export type StateKind = 'info' | 'warning' | 'success' | 'error';

const DEFAULT_ICON: Record<StateKind, IconName> = {
  info: 'information',
  warning: 'warning-filled',
  success: 'checkmark-filled',
  error: 'error-filled',
};

export interface StateCardProps {
  kind?: StateKind;
  icon?: IconName;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
}

export default function StateCard({
  kind = 'info',
  icon,
  title,
  children,
  actions,
}: StateCardProps) {
  return (
    <div className={s.card}>
      <div className={s.head}>
        <span className={clsx(s.ico, s[`ico--${kind}`])}>
          <Icon name={icon ?? DEFAULT_ICON[kind]} size={20} />
        </span>
        <div className={s.body}>
          <div className={s.title}>{title}</div>
          {children ? <div className={s.desc}>{children}</div> : null}
        </div>
      </div>
      {actions ? <div className={s.actions}>{actions}</div> : null}
    </div>
  );
}
