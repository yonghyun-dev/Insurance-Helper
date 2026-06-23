import Icon from '../../components/Icon/Icon';
import s from './chat.module.css';

export interface AttachChipProps {
  name: string;
  onRemove?: () => void;
}

export default function AttachChip({ name, onRemove }: AttachChipProps) {
  return (
    <span className={s['attach-chip']}>
      <Icon name="document" size={14} />
      <span>{name}</span>
      {onRemove ? (
        <button type="button" className={s.x} aria-label={`${name} 첨부 제거`} onClick={onRemove}>
          <Icon name="close" size={12} />
        </button>
      ) : null}
    </span>
  );
}
