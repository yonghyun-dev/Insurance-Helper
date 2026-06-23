import type { ReactNode } from 'react';
import Icon, { type IconName } from '../../components/Icon/Icon';
import s from './chat.module.css';

export interface ChatHeadAction {
  icon: IconName;
  label: string;
  onClick?: () => void;
}

export interface ChatHeadProps {
  title: string;
  sub?: ReactNode;
  actions?: ChatHeadAction[];
}

export default function ChatHead({ title, sub, actions }: ChatHeadProps) {
  return (
    <header className={s['chat-head']}>
      <div>
        <div className={s['chat-head__title']}>{title}</div>
        {sub ? <div className={s['chat-head__sub']}>{sub}</div> : null}
      </div>
      {actions && actions.length > 0 ? (
        <div className={s['chat-head__actions']}>
          {actions.map((action) => (
            <button
              key={action.label}
              type="button"
              className={s['icon-btn']}
              aria-label={action.label}
              onClick={action.onClick}
            >
              <Icon name={action.icon} size={18} />
            </button>
          ))}
        </div>
      ) : null}
    </header>
  );
}
