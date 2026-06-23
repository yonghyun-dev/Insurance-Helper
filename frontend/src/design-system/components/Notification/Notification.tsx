import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import Icon, { type IconName } from '../Icon/Icon';
import s from './Notification.module.css';

export type NotificationKind = 'info' | 'success' | 'warning' | 'error';

export interface NotificationProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  kind?: NotificationKind;
  title?: ReactNode;
  icon?: IconName;
  onClose?: () => void;
  children?: ReactNode;
}

const kindClass: Record<NotificationKind, string> = {
  info: s['notif--info'],
  success: s['notif--success'],
  warning: s['notif--warning'],
  error: s['notif--error'],
};

const kindIcon: Record<NotificationKind, IconName> = {
  info: 'information',
  success: 'checkmark-filled',
  warning: 'warning-filled',
  error: 'error-filled',
};

export default function Notification({
  kind = 'info',
  title,
  icon,
  onClose,
  className,
  children,
  ...rest
}: NotificationProps) {
  return (
    <div role="status" className={clsx(s.notif, kindClass[kind], className)} {...rest}>
      <Icon name={icon ?? kindIcon[kind]} size={20} className={s.notif__icon} />
      <div className={s.notif__body}>
        {title ? <div className={s.notif__title}>{title}</div> : null}
        {children ? <div className={s.notif__text}>{children}</div> : null}
      </div>
      {onClose ? (
        <button type="button" className={s.notif__close} onClick={onClose} aria-label="닫기">
          <Icon name="close" size={16} />
        </button>
      ) : (
        <span />
      )}
    </div>
  );
}
