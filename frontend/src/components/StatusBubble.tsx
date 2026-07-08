// 답변 생성 대기 중 "관련 약관 찾는 중…" 처럼 상태를 혼잣말로 바꿔 보여주는 버블.
// (실제 단계 신호는 아직 없으므로 시간 기반 순환 — 체감 대기감 완화)
import { useEffect, useState } from 'react';
import s from './StatusBubble.module.css';

const STATUSES = [
  '관련 약관을 찾고 있어요',
  '약관을 꼼꼼히 살펴보고 있어요',
  '보장 여부를 검토하고 있어요',
  '답변을 정리하고 있어요',
];

export default function StatusBubble() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setI((v) => (v + 1) % STATUSES.length), 1900);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className={s.wrap} aria-live="polite">
      <span className={s.dots}>
        <span className={s.dot} />
        <span className={s.dot} />
        <span className={s.dot} />
      </span>
      <span key={i} className={s.text}>
        {STATUSES[i]}...
      </span>
    </div>
  );
}
