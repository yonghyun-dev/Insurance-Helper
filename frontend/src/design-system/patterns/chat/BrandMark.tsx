import s from './chat.module.css';

export interface BrandMarkProps {
  logoSrc?: string;
  brand?: string;
  accent?: string;
  meta?: string;
}

export default function BrandMark({
  logoSrc = '/assets/logo-mark.png',
  brand = '보험길잡이',
  accent = '',
  meta = 'Insurance Guide',
}: BrandMarkProps) {
  return (
    <div className={s.brand}>
      <div className={s.brand__mark}>
        <img src={logoSrc} alt={brand} />
      </div>
      <div className={s.brand__word}>
        {brand}
        {accent ? <span className={s.accent}> {accent}</span> : null}
        <span className={s.meta}>{meta}</span>
      </div>
    </div>
  );
}
