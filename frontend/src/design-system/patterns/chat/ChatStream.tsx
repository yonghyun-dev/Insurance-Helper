import {
  forwardRef,
  type HTMLAttributes,
  type ReactNode,
} from 'react';
import clsx from 'clsx';
import s from './chat.module.css';

export interface ChatStreamProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

const ChatStream = forwardRef<HTMLDivElement, ChatStreamProps>(function ChatStream(
  { children, className, ...rest },
  ref,
) {
  return (
    <div ref={ref} className={clsx(s['chat-stream'], className)} {...rest}>
      <div className={s['chat-stream__inner']}>{children}</div>
    </div>
  );
});

export default ChatStream;
