import { useState } from 'react';
import clsx from 'clsx';
import Icon from '../../components/Icon/Icon';
import s from './chat.module.css';

export type FeedbackValue = 'up' | 'down' | null;

export interface FeedbackRowProps {
  initial?: FeedbackValue;
  onChange?: (value: FeedbackValue) => void;
  showCopy?: boolean;
  onCopy?: () => void;
}

export default function FeedbackRow({
  initial = null,
  onChange,
  showCopy = true,
  onCopy,
}: FeedbackRowProps) {
  const [value, setValue] = useState<FeedbackValue>(initial);

  function set(next: FeedbackValue) {
    const v = value === next ? null : next;
    setValue(v);
    onChange?.(v);
  }

  return (
    <div className={s.feedback}>
      <button
        type="button"
        aria-label="좋아요"
        aria-pressed={value === 'up'}
        className={clsx(value === 'up' && s.active)}
        onClick={() => set('up')}
      >
        <Icon name="thumbs-up" size={16} />
      </button>
      <button
        type="button"
        aria-label="싫어요"
        aria-pressed={value === 'down'}
        className={clsx(value === 'down' && s.active)}
        onClick={() => set('down')}
      >
        <Icon name="thumbs-down" size={16} />
      </button>
      {showCopy ? (
        <button type="button" aria-label="복사" onClick={onCopy}>
          <Icon name="copy" size={16} />
        </button>
      ) : null}
    </div>
  );
}
