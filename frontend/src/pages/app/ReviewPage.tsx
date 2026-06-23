// Sprint 22 — Review 실데이터 배선: 청구 요약(GET /summary) + 가입 보험 + 필요서류 체크리스트,
// 청구 접수(POST /submit) → 접수 완료 화면.
import { useEffect, useState } from 'react';
import { Button, Icon, Notification, Tile } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import {
  type ClaimReceipt,
  type ClaimSummary,
  type EnrolledInsurance,
  fetchClaimSummary,
  fetchInsurances,
  submitClaim,
} from '../../api/client';
import { useSession } from '../../hooks/useSession';
import s from './ReviewPage.module.css';

export interface ReviewPageProps {
  session: ReturnType<typeof useSession>;
  onBack: () => void;
}

const LIKELIHOOD_COLOR: Record<string, string> = {
  높음: '#24a148',
  중간: '#b28600',
  낮음: '#6f6f6f',
};

export default function ReviewPage({ session, onBack }: ReviewPageProps) {
  const [summary, setSummary] = useState<ClaimSummary | null>(null);
  const [insurances, setInsurances] = useState<EnrolledInsurance[]>([]);
  const [receipt, setReceipt] = useState<ClaimReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const sid = session.sessionId;
    if (!sid) {
      setLoading(false);
      return;
    }
    let alive = true;
    void (async () => {
      try {
        const [sm, ins] = await Promise.all([
          fetchClaimSummary(sid),
          fetchInsurances().catch(() => [] as EnrolledInsurance[]),
        ]);
        if (alive) {
          setSummary(sm);
          setInsurances(ins);
        }
      } catch {
        // 요약 조회 실패 — 화면은 안내만 표시
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [session.sessionId]);

  async function handleSubmit() {
    const sid = session.sessionId;
    if (!sid) return;
    setSubmitting(true);
    try {
      setReceipt(await submitClaim(sid));
    } catch {
      session.pushToast('error', '접수에 실패했어요. 잠시 후 다시 시도해주세요.');
    } finally {
      setSubmitting(false);
    }
  }

  // ── 접수 완료 화면 ──
  if (receipt) {
    return (
      <div className={s.shell} data-screen-label="08 접수 완료">
        <ShellHeader />
        <main className={s.main}>
          <div className={s.body} style={{ textAlign: 'center', maxWidth: 560 }}>
            <div style={{ color: '#24a148', marginBottom: 16 }}>
              <Icon name="checkmark-filled" size={56} />
            </div>
            <h1 className={s.title}>청구가 접수되었어요</h1>
            <p className={s.sub}>{receipt.message}</p>
            <Tile className={s.section} style={{ textAlign: 'left' }}>
              <div className={s.sectionLabel}>접수 정보</div>
              <Row label="접수번호" value={receipt.receipt_no} />
              <Row label="예상 심사 기간" value={`영업일 약 ${receipt.estimated_days}일`} />
              <Row label="상태" value={receipt.status} />
            </Tile>
            <div className={s.actions}>
              <Button variant="primary" size="xl" onClick={onBack}>
                상담으로 돌아가기
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className={s.shell} data-screen-label="07 청구 준비 화면">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          <button type="button" className={s.back} onClick={onBack}>
            <Icon name="chevron-left" size={14} />
            상담으로 돌아가기
          </button>

          <div className={s.head}>
            <h1 className={s.title}>청구 전 마지막 확인</h1>
            <p className={s.sub}>지금까지 정리된 내용을 함께 살펴봐 주세요. 아래 내용으로 청구를 진행할 수 있어요.</p>
          </div>

          {loading ? (
            <p className="ty-helper-01">청구 준비 내용을 불러오는 중…</p>
          ) : (
            <div className={s.grid}>
              {/* LEFT */}
              <div>
                <Tile className={s.section}>
                  <div className={s.sectionLabel}>청구 대상 보험</div>
                  <h2 className={s.sectionH}>가입하신 보험</h2>
                  {insurances.length === 0 ? (
                    <p className="ty-helper-01">연동된 가입 보험이 없어요.</p>
                  ) : (
                    insurances.map((p) => (
                      <div key={p.policy_no} className={s.policy}>
                        <span className={s.policyIco}>
                          <Icon name="checkmark-filled" size={20} />
                        </span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className={s.policyName}>{p.product_name}</div>
                          <div className={s.policyCo}>
                            {p.insurer_name} · 증권 {p.policy_no}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </Tile>

                <Tile className={s.section}>
                  <div className={s.sectionLabel}>청구 가능성 검토 결과</div>
                  <h2 className={s.sectionH}>
                    {summary?.likelihood ? (
                      <span style={{ color: LIKELIHOOD_COLOR[summary.likelihood] ?? '#161616' }}>
                        청구 가능성: {summary.likelihood}
                      </span>
                    ) : (
                      '검토 요약'
                    )}
                  </h2>
                  <div className={s.reasonCard}>
                    {summary?.summary ?? '아직 평가가 완료되지 않았어요. 상담을 마치면 결과가 표시됩니다.'}
                  </div>
                  {summary && summary.satisfied.length > 0 ? (
                    <CheckList title="충족 항목" items={summary.satisfied} />
                  ) : null}
                  {summary && summary.unsatisfied.length > 0 ? (
                    <CheckList title="확인 필요" items={summary.unsatisfied} />
                  ) : null}
                </Tile>
              </div>

              {/* RIGHT */}
              <div>
                <Tile className={s.section}>
                  <div className={s.sectionLabel}>필요 서류</div>
                  <h2 className={s.sectionH}>준비할 서류</h2>
                  {(summary?.checklist ?? []).map((d) => (
                    <div key={d.id} className={s.doc} title={d.reason}>
                      <span className={s.docIco}>
                        <Icon name={d.required ? 'checkmark' : 'information'} size={14} />
                      </span>
                      <span className={s.docName}>{d.label}</span>
                      <span className={s.docMeta}>{d.required ? '필수' : '선택'}</span>
                    </div>
                  ))}
                </Tile>

                {summary && summary.next_steps.length > 0 ? (
                  <Tile className={s.section}>
                    <div className={s.sectionLabel}>다음 단계</div>
                    <h2 className={s.sectionH}>이렇게 진행하세요</h2>
                    <ol style={{ margin: 0, paddingLeft: 18, lineHeight: '24px', fontSize: 14 }}>
                      {summary.next_steps.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ol>
                  </Tile>
                ) : null}

                <Notification kind="info" title="접수 전 확인해 주세요.">
                  <ul style={{ margin: '8px 0 0', paddingLeft: 18, lineHeight: '22px' }}>
                    <li>본 접수는 데모 환경의 가정 처리이며 실제 보험사로 전송되지 않습니다.</li>
                    <li>예상 결과는 약관 기반 추정이며 실제 지급 여부는 보험사 심사에 따릅니다.</li>
                  </ul>
                </Notification>
              </div>
            </div>
          )}

          <div className={s.actions}>
            <Button
              variant="primary"
              size="xl"
              onClick={handleSubmit}
              disabled={submitting || loading}
              withIcon
            >
              {submitting ? '접수 중…' : '청구 접수하기'}
              <Icon name="arrow-right" size={18} />
            </Button>
            <Button variant="tertiary" size="xl" onClick={onBack}>
              상담으로 돌아가기
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function CheckList({ title, items }: { title: string; items: string[] }) {
  return (
    <div style={{ marginTop: 12 }}>
      <strong style={{ fontSize: 13 }}>{title}</strong>
      <ul style={{ margin: '6px 0 0', paddingLeft: 18, lineHeight: '22px', fontSize: 13 }}>
        {items.map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
    </div>
  );
}
