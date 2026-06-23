import { useEffect, type ReactNode, type MouseEvent } from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import Icon, { type IconName } from '../Icon/Icon';
import s from './Modal.module.css';

export type ModalKind = 'info' | 'danger' | 'warning';

export interface ModalProps {
  open: boolean;
  onClose?: () => void;
  kind?: ModalKind;
  icon?: IconName;
  eyebrow?: ReactNode;
  title?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  closeOnBackdrop?: boolean;
}

const kindIconClass: Record<ModalKind, string | undefined> = {
  info: undefined,
  danger: s['modal__head-icon--danger'],
  warning: s['modal__head-icon--warning'],
};

const defaultIcon: Record<ModalKind, IconName> = {
  info: 'information',
  danger: 'error-filled',
  warning: 'warning-filled',
};

export default function Modal({
  open,
  onClose,
  kind = 'info',
  icon,
  eyebrow,
  title,
  children,
  footer,
  closeOnBackdrop = true,
}: ModalProps) {
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose?.();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  function onBackdropClick(e: MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget && closeOnBackdrop) onClose?.();
  }

  const iconName = icon ?? defaultIcon[kind];

  return createPortal(
    <div
      className={s['modal-backdrop']}
      role="dialog"
      aria-modal="true"
      onClick={onBackdropClick}
    >
      <div className={s.modal}>
        <div className={s.modal__head}>
          <div>
            <div className={clsx(s['modal__head-icon'], kindIconClass[kind])}>
              <Icon name={iconName} size={20} />
            </div>
            <div className={s['modal__head-text']}>
              {eyebrow ? <div className={s.modal__eyebrow}>{eyebrow}</div> : null}
              {title ? <div className={s.modal__title}>{title}</div> : null}
            </div>
          </div>
          {onClose ? (
            <button
              type="button"
              className={s.modal__close}
              onClick={onClose}
              aria-label="닫기"
            >
              <Icon name="close" size={16} />
            </button>
          ) : null}
        </div>
        {children ? <div className={s.modal__body}>{children}</div> : null}
        {footer ? <div className={s.modal__footer}>{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
