// 글자 크기 토글 (가 가 가) — ShellHeader rightSlot 등에서 사용.
import { useFontSize, type FontSize } from '../../hooks/useFontSize';
import s from './legal.module.css';

const OPTIONS: { v: FontSize; cls: string; label: string }[] = [
  { v: 'small', cls: s.fontBtnSmall, label: '작게' },
  { v: 'medium', cls: s.fontBtnMedium, label: '보통' },
  { v: 'large', cls: s.fontBtnLarge, label: '크게' },
];

export default function FontSizeToggle() {
  const { size, setSize } = useFontSize();
  return (
    <div className={s.fontToggle} role="radiogroup" aria-label="글자 크기 조절">
      {OPTIONS.map((o) => (
        <button
          key={o.v}
          type="button"
          role="radio"
          aria-checked={size === o.v}
          aria-label={`글자 크기 ${o.label}`}
          className={`${s.fontBtn} ${o.cls} ${size === o.v ? s.fontBtnActive : ''}`}
          onClick={() => setSize(o.v)}
        >
          가
        </button>
      ))}
    </div>
  );
}
