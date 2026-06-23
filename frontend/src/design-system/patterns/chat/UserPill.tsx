import s from './chat.module.css';

export interface UserPillProps {
  initial: string;
  name: string;
  meta?: string;
}

export default function UserPill({ initial, name, meta }: UserPillProps) {
  return (
    <div className={s.steps__footer}>
      <div className={s['user-pill']}>{initial}</div>
      <div>
        <div className={s['user-pill__name']}>{name}</div>
        {meta ? <div className={s['user-pill__meta']}>{meta}</div> : null}
      </div>
    </div>
  );
}
