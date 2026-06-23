// Sprint 21 — 사용자 첨부 이미지 확대 보기 (ESC/배경 클릭 닫기 + 스크롤 잠금).
import { useEffect } from 'react';
import { Icon } from '../design-system/components/Icon';
import s from './ImageLightbox.module.css';

export interface ImageLightboxProps {
  src: string;
  alt: string;
  filename?: string;
  onClose: () => void;
}

export default function ImageLightbox({ src, alt, filename, onClose }: ImageLightboxProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className={s.backdrop}
      role="dialog"
      aria-modal="true"
      aria-label={filename ?? '이미지 확대 보기'}
      onClick={onClose}
    >
      <figure className={s.figure} onClick={(e) => e.stopPropagation()}>
        <button type="button" className={s.close} aria-label="닫기" onClick={onClose}>
          <Icon name="close" size={20} />
        </button>
        <img className={s.img} src={src} alt={alt} />
        {filename ? <figcaption className={s.caption}>{filename}</figcaption> : null}
      </figure>
    </div>
  );
}
