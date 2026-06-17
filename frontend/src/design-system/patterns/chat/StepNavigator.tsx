import clsx from 'clsx';
import Icon from '../../components/Icon/Icon';
import s from './chat.module.css';

export type StepStatus = 'done' | 'active' | 'waiting' | 'pending';

export interface StepItem {
  id: string;
  number: number;
  label: string;
  sub?: string;
  status: StepStatus;
}

export interface StepNavigatorProps {
  title?: string;
  steps: StepItem[];
  onSelect?: (id: string) => void;
}

export default function StepNavigator({
  title = '청구 진행 단계',
  steps,
  onSelect,
}: StepNavigatorProps) {
  return (
    <nav className={s.steps}>
      <div className={s.steps__title}>{title}</div>
      <ol className={s['step-list']}>
        {steps.map((step) => (
          <li
            key={step.id}
            className={clsx(
              s.step,
              step.status === 'done' && s['step--done'],
              step.status === 'active' && s['step--active'],
              step.status === 'waiting' && s['step--waiting'],
            )}
            onClick={() => onSelect?.(step.id)}
          >
            <span className={s.step__dot}>
              {step.status === 'done' ? (
                <Icon name="checkmark" size={12} />
              ) : (
                step.number
              )}
            </span>
            <span className={s.step__label}>{step.label}</span>
            {step.sub ? <span className={s.step__sub}>{step.sub}</span> : null}
          </li>
        ))}
      </ol>
    </nav>
  );
}
