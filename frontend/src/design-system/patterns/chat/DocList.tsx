import Icon, { type IconName } from '../../components/Icon/Icon';
import s from './chat.module.css';

export interface DocItem {
  id: string;
  name: string;
  meta: string;
  icon?: IconName;
  onClick?: () => void;
}

export interface DocListProps {
  items: DocItem[];
}

export default function DocList({ items }: DocListProps) {
  return (
    <div className={s['doc-list']}>
      {items.map((item) => (
        <div key={item.id} className={s['doc-item']} onClick={item.onClick}>
          <div className={s['doc-item__ico']}>
            <Icon name={item.icon ?? 'document'} size={14} />
          </div>
          <div>
            <div className={s['doc-item__name']}>{item.name}</div>
            <div className={s['doc-item__meta']}>{item.meta}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
