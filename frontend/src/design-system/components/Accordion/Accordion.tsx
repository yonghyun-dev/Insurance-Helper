import { useState, type HTMLAttributes, type ReactNode } from 'react';
import clsx from 'clsx';
import Icon from '../Icon/Icon';
import s from './Accordion.module.css';

export interface AccordionItem {
  id: string;
  title: ReactNode;
  content: ReactNode;
  defaultOpen?: boolean;
}

export interface AccordionProps extends HTMLAttributes<HTMLDivElement> {
  items: AccordionItem[];
}

export default function Accordion({ items, className, ...rest }: AccordionProps) {
  const [openIds, setOpenIds] = useState<Set<string>>(
    () => new Set(items.filter((i) => i.defaultOpen).map((i) => i.id)),
  );

  function toggle(id: string) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className={clsx(s.acc, className)} {...rest}>
      {items.map((item) => {
        const open = openIds.has(item.id);
        return (
          <div key={item.id} className={clsx(s.acc__item, open && s['acc__item--open'])}>
            <button
              type="button"
              className={s.acc__header}
              aria-expanded={open}
              onClick={() => toggle(item.id)}
            >
              <span>{item.title}</span>
              <Icon name="chevron-down" size={16} />
            </button>
            <div className={s.acc__body}>{item.content}</div>
          </div>
        );
      })}
    </div>
  );
}
