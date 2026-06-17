import type { ReactNode } from 'react';
import clsx from 'clsx';
import Icon, { type IconName } from '../../components/Icon/Icon';
import Button from '../../components/Button/Button';
import s from './DocRow.module.css';

export type DocStatus = 'required' | 'done' | 'optional' | 'review';

const STATUS_LABEL: Record<DocStatus, string> = {
  required: '필수',
  done: '제출 완료',
  optional: '선택',
  review: '확인 필요',
};

const STATUS_ICON: Record<DocStatus, IconName> = {
  required: 'document',
  done: 'checkmark',
  optional: 'document',
  review: 'warning-filled',
};

export interface DocRowProps {
  status: DocStatus;
  name: ReactNode;
  desc?: ReactNode;
  action?: string;
  onAction?: () => void;
}

export interface DocChecklistProps {
  children: ReactNode;
}

export function DocChecklist({ children }: DocChecklistProps) {
  return <div className={s.checklist}>{children}</div>;
}

export default function DocRow({
  status,
  name,
  desc,
  action,
  onAction,
}: DocRowProps) {
  return (
    <div className={clsx(s.row, s[`row--${status}`])}>
      <span className={s.ico}>
        <Icon name={STATUS_ICON[status]} size={14} />
      </span>
      <div className={s.main}>
        <div className={s.name}>{name}</div>
        {desc ? <div className={s.desc}>{desc}</div> : null}
      </div>
      <span className={clsx(s.badge, s[`badge--${status}`])}>
        {STATUS_LABEL[status]}
      </span>
      {action ? (
        <Button variant="tertiary" size="sm" onClick={onAction} withIcon>
          <Icon name="arrow-up" size={14} />
          {action}
        </Button>
      ) : (
        <span />
      )}
    </div>
  );
}
