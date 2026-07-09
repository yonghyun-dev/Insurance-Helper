// Sprint 30/33 — 가입현황-우선 플로우. 본인확인 직후, 상황 입력 전에 "지금 가입한 실손"을
// 먼저 보여준다. 다중 실손이면 여러 개를 골라(체크박스) 각각 판정·비교한다(L3).
// 실손은 비례분담(이중 수령 불가)이라 "더 받는 법"이 아니라 "어느 약관이 유리한지" 비교.
import { useEffect, useState } from 'react';
import { Button, Icon, Tile } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import PreStepper from '../../design-system/patterns/onboarding/PreStepper';
import { demoLogin, fetchInsurances, type EnrolledInsurance } from '../../api/client';
import s from './InsuranceStatusPage.module.css';

export interface InsuranceStatusPageProps {
  user: { name: string; phone: string };
  onConfirm: (selected: EnrolledInsurance[], all: EnrolledInsurance[]) => void;
}

// 실손 중복가입 = 비례분담(이중 수령 불가). 환각 방지 위해 결정론 카피로 고정.
const PRORATION_COPY =
  '실손은 여러 개 가입해도 실제 낸 의료비 한도 안에서 비례로 나눠 지급돼요(이중 수령 불가). ' +
  '대신 가입 세대·자기부담률이 달라 어느 약관이 이 상황에 더 유리한지 비교해 드릴게요. ' +
  '비교할 보험을 골라 주세요.';

const GEN_LABEL: Record<number, string> = { 1: '1세대', 2: '2세대', 3: '3세대', 4: '4세대' };

export default function InsuranceStatusPage({ user, onConfirm }: InsuranceStatusPageProps) {
  const [insurances, setInsurances] = useState<EnrolledInsurance[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set()); // policy_no 집합
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
        // 기본: 전체 선택 (다건이면 전부 비교, 단건이면 그 1건)
        setSelected(new Set(ins.map((i) => i.policy_no)));
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

  function toggle(policyNo: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(policyNo)) next.delete(policyNo);
      else next.add(policyNo);
      return next;
    });
  }

  function confirm() {
    onConfirm(
      insurances.filter((i) => selected.has(i.policy_no)),
      insurances,
    );
  }

  const selectedCount = selected.size;
  const ctaLabel =
    selectedCount >= 2 ? `${selectedCount}개 보험 비교하기` : '이 보험으로 상황 입력하기';

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
            {multi ? '비교할 보험을 골라 주세요(여러 개 선택 가능).' : '이 보험 기준으로 확인해 드릴게요.'}
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
                <Button variant="primary" size="md" onClick={() => onConfirm([], [])} withIcon>
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
                <div className={s.listLabel}>{multi ? '비교할 보험 선택' : '가입한 보험'}</div>
                <div role="group" aria-label="가입한 실손 목록">
                  {insurances.map((p) => {
                    const on = selected.has(p.policy_no);
                    const gen = p.generation ? GEN_LABEL[p.generation] : null;
                    return (
                      <button
                        key={p.policy_no}
                        type="button"
                        role={multi ? 'checkbox' : undefined}
                        aria-checked={multi ? on : undefined}
                        className={`${s.policy} ${multi && on ? s.policyOn : ''} ${multi ? s.policySelectable : ''}`}
                        onClick={() => multi && toggle(p.policy_no)}
                        disabled={!multi}
                      >
                        <span className={s.policyIco}>
                          <Icon name={on ? 'checkmark-filled' : 'document'} size={20} />
                        </span>
                        <div className={s.policyText}>
                          <div className={s.policyName}>
                            {p.product_name}
                            {gen ? <span className={s.genTag}>{gen}</span> : null}
                          </div>
                          <div className={s.policyCo}>
                            {p.insurer_name} · 증권 {p.policy_no}
                          </div>
                        </div>
                        {multi ? (
                          <span className={`${s.check} ${on ? s.checkOn : ''}`} aria-hidden="true">
                            {on ? <Icon name="checkmark" size={14} /> : null}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </Tile>

              <div className={s.cta}>
                <Button
                  variant="primary"
                  size="md"
                  disabled={selectedCount === 0}
                  onClick={confirm}
                  withIcon
                >
                  {ctaLabel}
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
