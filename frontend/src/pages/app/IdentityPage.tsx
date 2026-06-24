import { useState, type ReactNode } from 'react';
import clsx from 'clsx';
import { Button, Field, Icon, Tile } from '../../design-system';
import ShellHeader from '../../design-system/patterns/shell/ShellHeader';
import PreStepper from '../../design-system/patterns/onboarding/PreStepper';
import s from './IdentityPage.module.css';

export interface UserInput {
  name: string;
  dob: string;
  phone: string;
}

export interface IdentityPageProps {
  initial?: Partial<UserInput>;
  onSubmit: (user: UserInput) => void;
  onBack?: () => void;
}

export default function IdentityPage({ initial, onSubmit }: IdentityPageProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [dob, setDob] = useState(initial?.dob ?? '');
  const [phone, setPhone] = useState(initial?.phone ?? '');
  const [verified, setVerified] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [consents, setConsents] = useState({ mydata: false, privacy: false });

  const canSubmit = verified && consents.mydata && consents.privacy && name && dob && phone;

  function startVerify() {
    if (!name || !dob || !phone) return;
    setVerifying(true);
    window.setTimeout(() => {
      setVerifying(false);
      setVerified(true);
    }, 1100);
  }

  return (
    <div className={s.shell} data-screen-label="02 본인 확인 · 마이데이터 동의">
      <ShellHeader />
      <main className={s.main}>
        <div className={s.body}>
          <PreStepper current="identity" />
          <h1 className={s.title}>본인 확인이 필요합니다</h1>
          <p className={s.sub}>
            가입한 보험을 안전하게 확인하기 위해 기본 정보와 동의를 받습니다.
            입력하신 정보는 청구 안내 외 용도로 사용되지 않습니다.
          </p>

          <Tile className={s.card}>
            <div className={s.sectionTitle}>기본 정보</div>
            <div className={s.fields}>
              <Field
                label="이름"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="홍길동"
                disabled={verified}
              />
              <Field
                label="생년월일"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                placeholder="예) 1985.04.12"
                disabled={verified}
              />
              <div>
                <div className={s.fieldRow}>
                  <Field
                    label="휴대폰 번호"
                    type="tel"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder="010-0000-0000"
                    disabled={verified}
                    helper={
                      verified
                        ? '본인 명의의 휴대폰으로 인증되었습니다.'
                        : '본인 명의의 휴대폰으로 인증을 진행합니다.'
                    }
                  />
                  {verified ? (
                    <Button variant="secondary" size="lg" disabled withIcon>
                      <Icon name="checkmark" size={14} /> 인증 완료
                    </Button>
                  ) : (
                    <Button
                      variant="tertiary"
                      size="lg"
                      onClick={startVerify}
                      disabled={verifying || !phone}
                    >
                      {verifying ? '인증 중…' : '본인 인증'}
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </Tile>

          <div className={s.consents}>
            <ConsentItem
              checked={consents.mydata}
              onToggle={() => setConsents((c) => ({ ...c, mydata: !c.mydata }))}
              required
              title="마이데이터 보험 조회 동의"
              desc="가입하신 보험사 정보를 마이데이터로 안전하게 조회합니다. 본인 동의 없이는 조회되지 않습니다."
            />
            <ConsentItem
              checked={consents.privacy}
              onToggle={() => setConsents((c) => ({ ...c, privacy: !c.privacy }))}
              required
              title="개인정보 수집 및 이용 동의"
              desc="입력하신 정보는 보험 조회와 청구 안내를 위해서만 사용되며, 안내 종료 후 안전하게 폐기됩니다."
            />
          </div>

          <div className={s.ctaWrap}>
            <Button
              className={s.cta}
              variant="primary"
              size="xl"
              disabled={!canSubmit}
              onClick={() => canSubmit && onSubmit({ name, dob, phone })}
              withIcon
            >
              내 보험 조회하기
              <Icon name="arrow-right" size={18} />
            </Button>
          </div>

          <div className={s.note}>
            <Icon name="checkmark-filled" size={18} />
            <div>
              <strong>안심하셔도 됩니다.</strong>{' '}
              보험 가입 내역은 본인 동의 후에만 확인되며, 보험길잡이는 본인 확인과 상담 안내 외
              다른 용도로 정보를 사용하지 않습니다.
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

interface ConsentItemProps {
  checked: boolean;
  onToggle: () => void;
  required?: boolean;
  title: ReactNode;
  desc: ReactNode;
}

function ConsentItem({ checked, onToggle, required, title, desc }: ConsentItemProps) {
  return (
    <Tile
      clickable
      className={clsx(s.consent, checked && s['consent--checked'])}
      onClick={onToggle}
      role="checkbox"
      aria-checked={checked}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          onToggle();
        }
      }}
    >
      <span className={s.consentBox}>
        <Icon name="checkmark" size={16} />
      </span>
      <div className={s.consentText}>
        <div className={s.consentLabel}>
          {title}
          {required ? <span className={s.required}>필수</span> : null}
        </div>
        <div className={s.consentDesc}>{desc}</div>
      </div>
      <button
        type="button"
        className={s.consentDetail}
        onClick={(e) => e.stopPropagation()}
      >
        전문 보기
      </button>
    </Tile>
  );
}
