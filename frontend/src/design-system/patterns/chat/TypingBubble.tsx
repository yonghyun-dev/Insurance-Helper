import s from './chat.module.css';

export default function TypingBubble() {
  return (
    <div className={s['typing-bubble']}>
      <span className={s['typing-dot']} />
      <span className={s['typing-dot']} />
      <span className={s['typing-dot']} />
    </div>
  );
}
