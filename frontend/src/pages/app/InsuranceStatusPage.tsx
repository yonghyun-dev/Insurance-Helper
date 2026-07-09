// Sprint 30 — 가입현황-우선 플로우. 본인확인 직후, 상황 입력 전에 "지금 가입한 실손"을
// 먼저 보여준다. 다중 실손이면 비례분담(이중 수령 불가) 안내 배너를 노출하고, 어떤 보험
// 기준으로 확인할지 대표 1건을 선택하게 한다(판정은 선택 1건 기준 — L1).
import { useEffect, useState } from 'react';
import { Button, Icon, Tile } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import PreStepper from '../../design-system/patterns/onboarding/PreStepper';
import { demoLogin, fetchInsurances, type EnrolledInsurance } from '../../api/client';
import s from './InsuranceStatusPage.module.css';

export interface InsuranceStatusPageProps {
  user: { name: string; phone: string };
  onConfirm: (selected: EnrolledInsurance | null, all: EnrolledInsurance[]) => void;
}

// 실손 중복가입 = 비례분담(이중 수령 불가). 환각 방지 위해 결정론 카피로 고정.
const PRORATION_COPY =
  '실손보험은 여러 개 가입해도 실제 낸 의료비 한도 안에서 나눠 지급돼요. ' +
  '이중으로 더 받지는 못하고, 여러 개 유지하면 보험료만 이중일 수 있어요. ' +
  '(진단비 같은 정액 특약은 별도로 각각 받을 수 있어요.)';

export default function InsuranceStatusPage({ user, onConfirm }: InsuranceStatusPageProps) {
  const [insurances, setInsurances] = useState<EnrolledInsurance[]>([]);
  const [selected, setSelected] = useState<string | null>(null); // policy_no
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        await demoLogin(user.name, user.phone);
        const ins = await fetchInsurances();
        if (!alive) return;
        setInsurances(ins);
        setSelected(ins[0]?.policy_no ?? null);
      } catch {
        if (alive) setFailed(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [user.name, user.phone]);

  const multi = insurances.length > 1;
  const selectedIns = insurances.find((i) => i.policy_no === selected) ?? null;

  function confirm() {
    onConfirm(selectedIns, insurances);
  }

  return (
    <div className={s.shell} data-screen-label="02 보험 확인">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          <PreStepper current="analysis" />
          <h1 className={s.title}>
            지금 가입하신 <strong>실손보험</strong>이에요
          </h1>
          <p className={s.sub}>
            마이데이터로 확인한 가입 현황입니다.<br />
            어떤 보험을 기준으로 확인할지 골라 주세요.
          </p>

          {loading ? (
            <p className={s.helper}>가입 보험을 불러오는 중…</p>
          ) : failed || insurances.length === 0 ? (
            <>
              <Tile className={s.emptyCard}>
                <Icon name="information" size={22} />
                <div>
                  <div className={s.emptyTitle}>연동된 가입 실손이 없어요</div>
                  <p className={s.emptyDesc}>
                    가입 보험 정보 없이도 상황을 입력하면 일반 실손 표준약관 기준으로 안내해 드릴 수 있어요.
                  </p>
                </div>
              </Tile>
              <div className={s.cta}>
                <Button variant="primary" size="md" onClick={() => onConfirm(null, [])} withIcon>
                  상황 입력으로 계속
                  <Icon name="arrow-right" size={16} />
                </Button>
              </div>
            </>
          ) : (
            <>
              {multi ? (
                <Tile className={s.prorationCard}>
                  <span className={s.prorationIco}>
                    <Icon name="information" size={20} />
                  </span>
                  <div>
                    <div className={s.prorationTitle}>실손 {insurances.length}건에 가입되어 있어요</div>
                    <p className={s.prorationDesc}>{PRORATION_COPY}</p>
                  </div>
                </Tile>
              ) : null}

              <Tile className={s.listCard}>
                <div className={s.listLabel}>
                  {multi ? '확인할 보험 선택' : '가입한 보험'}
                </div>
                <div role={multi ? 'radiogroup' : undefined} aria-label="가입한 실손 목록">
                  {insurances.map((p) => {
                    const on = p.policy_no === selected;
                    return (
                      <button
                        key={p.policy_no}
                        type="button"
                        role={multi ? 'radio' : undefined}
                        aria-checked={multi ? on : undefined}
                        className={`${s.policy} ${multi && on ? s.policyOn : ''} ${multi ? s.policySelectable : ''}`}
                        onClick={() => multi && setSelected(p.policy_no)}
                        disabled={!multi}
                      >
                        <span className={s.policyIco}>
                          <Icon name={on ? 'checkmark-filled' : 'document'} size={20} />
                        </span>
                        <div className={s.policyText}>
                          <div className={s.policyName}>{p.product_name}</div>
                          <div className={s.policyCo}>
                            {p.insurer_name} · 증권 {p.policy_no}
                          </div>
                        </div>
                        {multi ? <span className={s.radio} aria-hidden="true" /> : null}
                      </button>
                    );
                  })}
                </div>
              </Tile>

              <div className={s.cta}>
                <Button
                  variant="primary"
                  size="md"
                  disabled={!selectedIns}
                  onClick={confirm}
                  withIcon
                >
                  이 보험으로 상황 입력하기
                  <Icon name="arrow-right" size={16} />
                </Button>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
