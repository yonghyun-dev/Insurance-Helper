import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import s from './Radio.module.css';

export interface RadioProps extends InputHTMLAttributes<HTMLInputElement> {
  children?: ReactNode;
}

const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { children, className, ...rest },
  ref,
) {
  return (
    <label className={clsx(s.rbx, className)}>
      <input ref={ref} type="radio" {...rest} />
      <span className={s.rbx__dot} />
      <span>{children}</span>
    </label>
  );
});

export default Radio;
