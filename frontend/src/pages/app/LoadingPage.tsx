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

// Sprint 35 — 스텝 애니메이션이 끝난 뒤에도 응답 전이면 마지막 단계를 '진행 중'으로
// 유지하고 힌트를 순환시켜, 오래 걸려도 화면이 멈춰 보이지 않게 한다.
const HOLD_HINTS = [
  '약관 원문을 한 줄씩 대조하고 있어요',
  '보장 조건과 자기부담금을 계산하고 있어요',
  '근거 조항을 추려 답변을 작성하고 있어요',
];

export interface LoadingPageProps {
  onDone: () => void;
  // Sprint 21 — 실제 첫 응답이 도착했는지. 애니메이션이 끝나도 응답 전이면 마지막 단계에서 대기.
  ready: boolean;
}

export default function LoadingPage({ onDone, ready }: LoadingPageProps) {
  const [progress, setProgress] = useState(0);
  const [hint, setHint] = useState(0);

  useEffect(() => {
    if (ready) {
      // 응답 도착 — 남은 단계를 완료 표시하고 짧게 보여준 뒤 전환.
      setProgress(STEPS.length);
      const t = window.setTimeout(onDone, 400);
      return () => window.clearTimeout(t);
    }
    if (progress < STEPS.length - 1) {
      const t = window.setTimeout(() => setProgress((p) => p + 1), 900);
      return () => window.clearTimeout(t);
    }
    // 마지막 단계 유지 — 스피너가 계속 돌고 힌트가 순환한다 (정지 화면 방지).
    const t = window.setTimeout(() => setHint((h) => h + 1), 3200);
    return () => window.clearTimeout(t);
  }, [progress, ready, onDone, hint]);

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
              const active = i === progress || (i === STEPS.length - 1 && progress === STEPS.length - 1);
              return (
                <div
                  key={i}
                  className={clsx(
                    s.step,
                    done && s['step--done'],
                    !done && active && s['step--active'],
                  )}
                >
                  <span className={s.stepIcon}>
                    {done ? <Icon name="checkmark" size={12} /> : null}
                  </span>
                  <span>{label}</span>
                </div>
              );
            })}
            {!ready && progress === STEPS.length - 1 ? (
              <p key={hint} className={s.holdHint}>
                {HOLD_HINTS[hint % HOLD_HINTS.length]}…
              </p>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  );
}
