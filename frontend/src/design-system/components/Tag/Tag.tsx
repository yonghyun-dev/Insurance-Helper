import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import Icon from '../Icon/Icon';
import s from './Tag.module.css';

export type TagColor = 'gray' | 'blue' | 'green' | 'red';

export interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  color?: TagColor;
  filter?: boolean;
  onDismiss?: () => void;
  children?: ReactNode;
}

const colorClass: Record<TagColor, string | undefined> = {
  gray: s['tag--gray'],
  blue: s['tag--blue'],
  green: s['tag--green'],
  red: s['tag--red'],
};

export default function Tag({
  color = 'gray',
  filter = false,
  onDismiss,
  className,
  children,
  ...rest
}: TagProps) {
  return (
    <span
      className={clsx(s.tag, colorClass[color], filter && s['tag--filter'], className)}
      {...rest}
    >
      <span>{children}</span>
      {filter ? (
        <Icon
          name="close"
          size={16}
          onClick={onDismiss}
          style={{ cursor: 'pointer' }}
        />
      ) : null}
    </span>
  );
}
