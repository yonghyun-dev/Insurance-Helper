import { useEffect, useRef, useState, type HTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import Icon from '../Icon/Icon';
import s from './Select.module.css';

export interface SelectOption {
  value: string;
  label: ReactNode;
}

export interface SelectProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  options: SelectOption[];
  value?: string;
  placeholder?: string;
  onChange?: (value: string) => void;
}

export default function Select({
  options,
  value,
  placeholder = '선택해 주세요',
  onChange,
  className,
  ...rest
}: SelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  return (
    <div ref={rootRef} className={clsx(s.selWrap, className)} {...rest}>
      <div
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        tabIndex={0}
        className={clsx(s.sel, open && s['sel--open'])}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            setOpen((v) => !v);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
      >
        <span className={selected ? undefined : s.sel__placeholder}>
          {selected ? selected.label : placeholder}
        </span>
        <Icon name="chevron-down" size={16} className={s.sel__chevron} />
      </div>
      {open ? (
        <ul role="listbox" className={s.sel__menu}>
          {options.map((opt) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              className={clsx(s.sel__item, opt.value === value && s['sel__item--selected'])}
              onClick={() => {
                onChange?.(opt.value);
                setOpen(false);
              }}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
