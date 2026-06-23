// Sprint 21 — 건강보험 진료 내역 패널 (더미). 🩺 클릭 → 진료 카드 → 선택 시 자연어 메시지 전송.
import { useState } from 'react';
import { IcaApiError, fetchHealthHistory } from '../api/client';
import type { TreatmentCard } from '../types/api';
import s from './HealthHistoryPanel.module.css';

interface Props {
  onSelect: (card: TreatmentCard) => void;
  pushToast: (kind: 'info' | 'warn' | 'error', text: string) => void;
}

export default function HealthHistoryPanel({ onSelect, pushToast }: Props) {
  const [treatments, setTreatments] = useState<TreatmentCard[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function handleFetch() {
    setLoading(true);
    try {
      const r = await fetchHealthHistory();
      setTreatments(r.treatments);
      setOpen(true);
      pushToast('info', `최근 진료 내역 ${r.treatments.length}건을 가져왔어요.`);
    } catch (e) {
      const msg =
        e instanceof IcaApiError && e.status === 401
          ? '로그인이 필요한 기능입니다.'
          : e instanceof IcaApiError
            ? e.message
            : '진료 내역 조회에 실패했습니다.';
      pushToast('error', msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={s.wrap}>
      <button
        type="button"
        className={s.trigger}
        onClick={open ? () => setOpen(false) : handleFetch}
        disabled={loading}
      >
        🩺 {loading ? '가져오는 중…' : open ? '진료 내역 닫기' : '최근 진료 내역 가져오기'}
      </button>

      {open && treatments && treatments.length > 0 ? (
        <ul className={s.list}>
          {treatments.map((t) => (
            <li key={t.treatment_id} className={s.card}>
              <div className={s.head}>
                <span>{t.treatment_date}</span>
                <span>
                  {t.hospital_name} · {t.department}
                </span>
              </div>
              <div className={s.diag}>{t.diagnosis_summary}</div>
              <div className={s.meta}>
                {t.is_hospitalization ? `입원 ${t.hospitalization_days}일` : `외래 ${t.outpatient_visits}회`}
                {' · '}청구가능 {t.claim_amount.toLocaleString()}원
              </div>
              <button
                type="button"
                className={s.select}
                onClick={() => {
                  onSelect(t);
                  setOpen(false);
                }}
              >
                이 진료로 청구 가능성 확인
              </button>
            </li>
          ))}
        </ul>
      ) : null}

      {open && treatments && treatments.length === 0 ? (
        <div className={s.empty}>최근 진료 내역이 없어요.</div>
      ) : null}
    </div>
  );
}
