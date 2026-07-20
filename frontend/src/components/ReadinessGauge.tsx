import type { ReadinessScore } from '../types/api';
import s from './ReadinessGauge.module.css';

/**
 * 청구 준비도 0~100 게이지 (제안서 '준비도 스코어' — 백엔드 결정론 산출값 렌더).
 *
 * - 신호등(높음/보통/보완필요)은 색+텍스트 라벨 병행 (색 단독 전달 금지)
 * - 숫자는 지급 확률이 아니므로 caption(백엔드 고정 문구)을 반드시 함께 표시
 */
const LEVEL_LABEL: Record<ReadinessScore['level'], string> = {
  high: '준비 잘 됨',
  medium: '조금만 보완하면 돼요',
  low: '보완이 필요해요',
};

export default function ReadinessGauge({ r }: { r: ReadinessScore }) {
  return (
    <div className={s.tile} data-level={r.level}>
      <div className={s.head}>
        <span className={s.title}>청구 준비도</span>
        <span className={s.levelChip}>
          <span className={s.dot} aria-hidden />
          {LEVEL_LABEL[r.level]}
        </span>
      </div>

      <div className={s.scoreRow}>
        <strong className={s.score}>{r.score}</strong>
        <span className={s.scoreMax}>/ 100점</span>
      </div>

      <div
        className={s.track}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={r.score}
        aria-label={`청구 준비도 ${r.score}점, ${LEVEL_LABEL[r.level]}`}
      >
        <div className={s.fill} style={{ width: `${r.score}%` }} />
      </div>

      <ul className={s.factors}>
        {r.factors.map((f) => (
          <li key={f.label}>
            <span className={s.factorLabel}>{f.label}</span>
            <span className={s.factorPts}>
              {f.points}/{f.max_points}
            </span>
          </li>
        ))}
      </ul>

      <p className={s.caption}>{r.caption}</p>
    </div>
  );
}
