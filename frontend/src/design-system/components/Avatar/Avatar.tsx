import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import s from './Avatar.module.css';

export type AvatarKind = 'bot' | 'user';
export type AvatarSize = 'md' | 'lg';

export interface AvatarProps extends HTMLAttributes<HTMLSpanElement> {
  kind?: AvatarKind;
  size?: AvatarSize;
  children?: ReactNode;
}

export default function Avatar({
  kind = 'user',
  size = 'md',
  className,
  children,
  ...rest
}: AvatarProps) {
  return (
    <span
      className={clsx(
        s.avatar,
        kind === 'bot' ? s['avatar--bot'] : s['avatar--user'],
        size === 'lg' && s['avatar--lg'],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}
