// Sprint 21 — 사용자 첨부 이미지 확대 보기 (ESC/배경 클릭 닫기 + 스크롤 잠금).
import { useEffect } from 'react';
import { Icon } from '../design-system/components/Icon';
import s from './ImageLightbox.module.css';

export interface ImageLightboxProps {
  src: string;
  alt: string;
  filename?: string;
  /** 0~1 정규화 하이라이트 박스 (인용 약관 페이지 확대 시 근거 강조 유지). */
  highlights?: { x: number; y: number; w: number; h: number }[];
  onClose: () => void;
}

export default function ImageLightbox({
  src,
  alt,
  filename,
  highlights,
  onClose,
}: ImageLightboxProps) {
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
        <div className={s.imgWrap}>
          <img className={s.img} src={src} alt={alt} />
          {(highlights ?? []).map((hl, i) => (
            <span
              key={i}
              className={s.hl}
              style={{
                left: `${hl.x * 100}%`,
                top: `${hl.y * 100}%`,
                width: `${hl.w * 100}%`,
                height: `${hl.h * 100}%`,
              }}
            />
          ))}
        </div>
        {filename ? <figcaption className={s.caption}>{filename}</figcaption> : null}
      </figure>
    </div>
  );
}
