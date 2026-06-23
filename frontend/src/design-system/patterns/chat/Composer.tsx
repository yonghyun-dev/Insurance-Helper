import {
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import Icon from '../../components/Icon/Icon';
import { useAutoResize } from '../../hooks/useAutoResize';
import AttachChip from './AttachChip';
import s from './chat.module.css';

export interface ComposerAttachment {
  id: string;
  name: string;
}

export interface ComposerProps {
  attachments?: ComposerAttachment[];
  onRemoveAttachment?: (id: string) => void;
  onAttach?: () => void;
  onSend?: (text: string) => void;
  placeholder?: string;
  hint?: ReactNode;
  disabled?: boolean;
}

export default function Composer({
  attachments = [],
  onRemoveAttachment,
  onAttach,
  onSend,
  placeholder = '메시지를 입력해 주세요',
  hint = '답변은 참고용입니다. 정확한 청구·지급은 보험사 결정에 따릅니다.',
  disabled,
}: ComposerProps) {
  const [value, setValue] = useState('');
  const taRef = useRef<HTMLTextAreaElement>(null);
  useAutoResize(taRef, value);

  const trimmed = value.trim();
  const canSend = trimmed.length > 0 && !disabled;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    onSend?.(trimmed);
    setValue('');
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className={s['composer-zone']}>
      <form className={s.composer} onSubmit={submit}>
        <div className={s['composer__attachments']}>
          {attachments.map((attach) => (
            <AttachChip
              key={attach.id}
              name={attach.name}
              onRemove={onRemoveAttachment ? () => onRemoveAttachment(attach.id) : undefined}
            />
          ))}
        </div>
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          aria-label="메시지 입력"
        />
        <div className={s['composer__bar']}>
          <div className={s['composer__bar-left']}>
            <button
              type="button"
              className={s['icon-btn']}
              aria-label="파일 첨부"
              onClick={onAttach}
            >
              <Icon name="attachment" size={18} />
            </button>
          </div>
          <button
            type="submit"
            className={s['composer__send']}
            aria-label="전송"
            disabled={!canSend}
          >
            <Icon name="arrow-up" size={18} />
          </button>
        </div>
      </form>
      <div className={s['composer__hint']}>{hint}</div>
    </div>
  );
}
