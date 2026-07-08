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

// 사람 = 우측(말풍선), Agent = 좌측(아바타 + 대화형 텍스트). ChatGPT/Claude 스타일.
export default function MessageBubble({ role, name, time, children }: MessageBubbleProps) {
  const isUser = role === 'user';
  return (
    <div className={clsx(s.bubble, isUser && s['bubble--user'])}>
      {!isUser ? (
        <div className={clsx(s.bubble__avatar, s['bubble__avatar--bot'])}>
          <Icon name="bot" size={18} />
        </div>
      ) : null}
      <div className={s.bubble__col}>
        <div className={s.bubble__head}>
          <span className={s.bubble__name}>{name}</span>
          <span className={s.bubble__time}>{time}</span>
        </div>
        <div className={s.bubble__body}>{children}</div>
      </div>
    </div>
  );
}
