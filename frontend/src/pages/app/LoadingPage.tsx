import { useEffect, useState } from 'react';
import clsx from 'clsx';
import { Icon } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import PreStepper from '../../design-system/patterns/onboarding/PreStepper';
import s from './LoadingPage.module.css';

const STEPS = [
  '가입 보험을 확인하고 있습니다',
  '관련 약관을 불러오고 있습니다',
  '입력하신 상황과 보장 항목을 비교하고 있습니다',
  '필요한 확인 사항을 정리하고 있습니다',
];

export interface LoadingPageProps {
  onDone: () => void;
}

export default function LoadingPage({ onDone }: LoadingPageProps) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (progress >= STEPS.length) {
      const t = window.setTimeout(onDone, 600);
      return () => window.clearTimeout(t);
    }
    const t = window.setTimeout(() => setProgress((p) => p + 1), 900);
    return () => window.clearTimeout(t);
  }, [progress, onDone]);

  return (
    <div className={s.shell} data-screen-label="04 분석 중">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          <PreStepper current="analysis" />
          <div className={s.pulse}>
            <div className={s.pulseCore}>
              <Icon name="search" size={24} />
            </div>
          </div>
          <h1 className={s.title}>보험길잡이가 확인하고 있어요</h1>
          <p className={s.sub}>보통 30초 이내에 마무리됩니다. 잠시만 기다려 주세요.</p>

          <div className={s.steps}>
            {STEPS.map((label, i) => {
              const done = i < progress;
              const active = i === progress;
              return (
                <div
                  key={i}
                  className={clsx(
                    s.step,
                    done && s['step--done'],
                    active && s['step--active'],
                  )}
                >
                  <span className={s.stepIcon}>
                    {done ? <Icon name="checkmark" size={12} /> : null}
                  </span>
                  <span>{label}</span>
                </div>
              );
            })}
          </div>
        </div>
      </main>
    </div>
  );
}
