import type { HTMLAttributes, ReactNode } from 'react';
import clsx from 'clsx';
import s from './chat.module.css';

export interface AppShellProps extends HTMLAttributes<HTMLDivElement> {
  sidebar: ReactNode;
  children: ReactNode;
}

export default function AppShell({ sidebar, children, className, ...rest }: AppShellProps) {
  return (
    <div className={clsx(s.app, className)} {...rest}>
      <aside className={s.app__steps}>{sidebar}</aside>
      <section className={s.app__chat}>{children}</section>
    </div>
  );
}
