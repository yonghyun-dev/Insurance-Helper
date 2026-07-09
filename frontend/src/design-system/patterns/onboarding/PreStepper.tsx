import { Fragment } from 'react';
import clsx from 'clsx';
import Icon from '../../components/Icon/Icon';
import s from './PreStepper.module.css';

export type PreStepId = 'identity' | 'situation' | 'analysis' | 'chat';

export interface PreStepperProps {
  current: PreStepId;
}

// Sprint 30 — 가입현황-우선 플로우: 본인 확인 → 보험 확인 → 상황 입력 → 맞춤 안내
const STEPS: { id: PreStepId; label: string }[] = [
  { id: 'identity',  label: '본인 확인' },
  { id: 'analysis',  label: '보험 확인' },
  { id: 'situation', label: '상황 입력' },
  { id: 'chat',      label: '맞춤 안내' },
];

export default function PreStepper({ current }: PreStepperProps) {
  const ix = STEPS.findIndex((step) => step.id === current);

  return (
    <div className={s.stepper} aria-label="진행 단계">
      {STEPS.map((step, i) => {
        const done = i < ix;
        const active = i === ix;
        return (
          <Fragment key={step.id}>
            <div
              className={clsx(
                s.item,
                done && s['item--done'],
                active && s['item--active'],
              )}
            >
              <span className={s.dot}>
                {done ? <Icon name="checkmark" size={12} /> : i + 1}
              </span>
              <span>{step.label}</span>
            </div>
            {i < STEPS.length - 1 ? (
              <span className={clsx(s.line, done && s['line--done'])} />
            ) : null}
          </Fragment>
        );
      })}
    </div>
  );
}
