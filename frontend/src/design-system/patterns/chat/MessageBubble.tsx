import type { ReactNode } from 'react';
import clsx from 'clsx';
import Icon from '../../components/Icon/Icon';
import s from './chat.module.css';

export type Role = 'bot' | 'user';

export interface MessageBubbleProps {
  role: Role;
  name: string;
  time: string;
  initial?: string;
  children: ReactNode;
}

export default function MessageBubble({
  role,
  name,
  time,
  initial,
  children,
}: MessageBubbleProps) {
  return (
    <div className={s.bubble}>
      <div
        className={clsx(
          s.bubble__avatar,
          role === 'bot' ? s['bubble__avatar--bot'] : s['bubble__avatar--user'],
        )}
      >
        {role === 'bot' ? <Icon name="bot" size={18} /> : initial}
      </div>
      <div style={{ minWidth: 0 }}>
        <div className={s.bubble__head}>
          <span className={s.bubble__name}>{name}</span>
          <span className={s.bubble__time}>{time}</span>
        </div>
        <div className={s.bubble__body}>{children}</div>
      </div>
    </div>
  );
}
