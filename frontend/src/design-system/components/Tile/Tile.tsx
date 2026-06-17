import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import s from './Tile.module.css';

export interface TileProps extends HTMLAttributes<HTMLDivElement> {
  clickable?: boolean;
  selected?: boolean;
  accent?: boolean;
  children?: ReactNode;
}

export default function Tile({
  clickable,
  selected,
  accent,
  className,
  children,
  ...rest
}: TileProps) {
  return (
    <div
      className={clsx(
        s.tile,
        clickable && s['tile--clickable'],
        selected && s['tile--selected'],
        accent && s['tile--accent'],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
