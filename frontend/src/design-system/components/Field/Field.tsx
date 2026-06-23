import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
} from 'react';
import clsx from 'clsx';
import Icon, { type IconName } from '../Icon/Icon';
import s from './Field.module.css';

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  helper?: string;
  error?: ReactNode;
  invalid?: boolean;
  leadingIcon?: IconName;
}

const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, helper, error, invalid, leadingIcon, className, id, ...rest },
  ref,
) {
  const reactId = useId();
  const inputId = id ?? reactId;
  const isInvalid = invalid || Boolean(error);

  const inputEl = (
    <input
      ref={ref}
      id={inputId}
      className={clsx(s.field__input, leadingIcon && s['field__input--with-icon'])}
      aria-invalid={isInvalid || undefined}
      {...rest}
    />
  );

  return (
    <div className={clsx(s.field, isInvalid && s['field--invalid'], className)}>
      {label ? (
        <label className={s.field__label} htmlFor={inputId}>
          {label}
        </label>
      ) : null}
      {leadingIcon ? (
        <div className={s['field__input-wrap']}>
          <Icon name={leadingIcon} size={16} className={s.field__icon} />
          {inputEl}
        </div>
      ) : (
        inputEl
      )}
      {error ? (
        <div className={s.field__error}>
          <Icon name="warning-filled" size={16} />
          <span>{error}</span>
        </div>
      ) : helper ? (
        <div className={s.field__helper}>{helper}</div>
      ) : null}
    </div>
  );
});

export default Field;
