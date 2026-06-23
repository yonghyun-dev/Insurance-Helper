import s from './chat.module.css';

export interface QuickRepliesProps {
  replies: string[];
  onSelect?: (text: string) => void;
}

export default function QuickReplies({ replies, onSelect }: QuickRepliesProps) {
  return (
    <div className={s['quick-replies']}>
      {replies.map((reply) => (
        <button
          key={reply}
          type="button"
          className={s['quick-reply']}
          onClick={() => onSelect?.(reply)}
        >
          {reply}
        </button>
      ))}
    </div>
  );
}
