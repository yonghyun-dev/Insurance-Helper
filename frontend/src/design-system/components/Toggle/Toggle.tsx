import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import s from './Toggle.module.css';

export interface ToggleProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode;
  stateLabel?: ReactNode;
}

const Toggle = forwardRef<HTMLInputElement, ToggleProps>(function Toggle(
  { label, stateLabel, className, checked, ...rest },
  ref,
) {
  return (
    <label className={clsx(s.tog, className)}>
      <input ref={ref} type="checkbox" checked={checked} {...rest} />
      <span className={s.tog__track}>
        <span className={s.tog__handle} />
      </span>
      {(label || stateLabel) && (
        <span className={s.tog__label}>
          {label ? <span>{label}</span> : null}
          {stateLabel ? <span className={s.tog__state}>{stateLabel}</span> : null}
        </span>
      )}
    </label>
  );
});

export default Toggle;
