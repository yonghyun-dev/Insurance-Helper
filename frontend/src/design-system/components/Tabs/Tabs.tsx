import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import s from './Tabs.module.css';

export interface TabItem {
  id: string;
  label: ReactNode;
}

export interface TabsProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  items: TabItem[];
  activeId: string;
  onChange?: (id: string) => void;
}

export default function Tabs({ items, activeId, onChange, className, ...rest }: TabsProps) {
  return (
    <div role="tablist" className={clsx(s.tabs, className)} {...rest}>
      {items.map((item) => {
        const active = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            className={clsx(s.tab, active && s['tab--active'])}
            onClick={() => onChange?.(item.id)}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
