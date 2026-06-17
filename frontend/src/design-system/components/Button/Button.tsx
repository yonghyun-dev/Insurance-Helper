import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import s from './Button.module.css';

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg' | 'xl' | '2xl';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  iconOnly?: boolean;
  withIcon?: boolean;
  children?: ReactNode;
}

const variantClass: Record<ButtonVariant, string> = {
  primary: s['btn--primary'],
  secondary: s['btn--secondary'],
  tertiary: s['btn--tertiary'],
  ghost: s['btn--ghost'],
  danger: s['btn--danger'],
};

const sizeClass: Partial<Record<ButtonSize, string>> = {
  sm: s['btn--sm'],
  md: s['btn--md'],
  xl: s['btn--xl'],
  '2xl': s['btn--2xl'],
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'lg',
    iconOnly = false,
    withIcon = false,
    className,
    type = 'button',
    children,
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={clsx(
        s.btn,
        variantClass[variant],
        sizeClass[size],
        iconOnly && s['btn--icon'],
        withIcon && s['btn--with-icon'],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

export default Button;
