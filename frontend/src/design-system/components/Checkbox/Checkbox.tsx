import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import s from './Checkbox.module.css';

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  children?: ReactNode;
}

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { children, className, ...rest },
  ref,
) {
  return (
    <label className={clsx(s.cbx, className)}>
      <input ref={ref} type="checkbox" {...rest} />
      <span className={s.cbx__box} />
      <span>{children}</span>
    </label>
  );
});

export default Checkbox;
