import s from './chat.module.css';

export interface InfoCardRow {
  label: string;
  value: string;
}

export interface InfoCardProps {
  title: string;
  rows: InfoCardRow[];
}

export default function InfoCard({ title, rows }: InfoCardProps) {
  return (
    <div className={s['info-card']}>
      <div className={s['info-card__title']}>{title}</div>
      <dl className={s['info-card__row']}>
        {rows.map((row) => (
          <div key={row.label} style={{ display: 'contents' }}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
