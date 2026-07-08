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
  const [dob, setDob] = useState((initial?.dob ?? '').replace(/\D/g, '').slice(0, 8));
  const [phone, setPhone] = useState(formatPhone(initial?.phone ?? ''));
  const [verified, setVerified] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [consents, setConsents] = useState({ mydata: false, privacy: false });

  // 입력 검증 — 한글/영문 이름, 8자리 생년월일, 010 휴대폰.
  const nameOk = /^[가-힣a-zA-Z][가-힣a-zA-Z\s]*$/.test(name.trim()) && name.trim().length >= 2;
  const dobOk = isValidDob(dob);
  const phoneDigits = phone.replace(/\D/g, '');
  const phoneOk = /^01[0-9]{8,9}$/.test(phoneDigits);
  const basicsOk = nameOk && dobOk && phoneOk;

  const nameError = name && !nameOk ? '이름을 한글 또는 영문으로 정확히 입력해 주세요.' : undefined;
  const dobError = dob && !dobOk ? '생년월일 8자리를 정확히 입력해 주세요. (예: 19850412)' : undefined;
  const phoneError = phone && !phoneOk ? '휴대폰 번호를 정확히 입력해 주세요. (예: 010-1234-5678)' : undefined;

  const canSubmit = verified && consents.mydata && consents.privacy && basicsOk;

  function startVerify() {
    if (!basicsOk) return;
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
            <br />
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
                error={nameError}
                autoComplete="name"
              />
              <Field
                label="생년월일"
                value={dob}
                onChange={(e) => setDob(e.target.value.replace(/\D/g, '').slice(0, 8))}
                placeholder="예) 19850412"
                helper="점(.) 없이 숫자 8자리로 입력해 주세요."
                inputMode="numeric"
                maxLength={8}
                disabled={verified}
                error={dobError}
              />
              <div>
                <div className={s.fieldRow}>
                  <Field
                    label="휴대폰 번호"
                    type="tel"
                    inputMode="numeric"
                    maxLength={13}
                    value={phone}
                    onChange={(e) => setPhone(formatPhone(e.target.value))}
                    placeholder="010-1234-5678"
                    disabled={verified}
                    error={phoneError}
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
                      disabled={verifying || !basicsOk}
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

// 휴대폰 번호 자동 하이픈 포맷 (숫자만 추출, 최대 11자리 → 010-1234-5678).
function formatPhone(v: string): string {
  const d = v.replace(/\D/g, '').slice(0, 11);
  if (d.length < 4) return d;
  if (d.length < 8) return `${d.slice(0, 3)}-${d.slice(3)}`;
  return `${d.slice(0, 3)}-${d.slice(3, 7)}-${d.slice(7)}`;
}

// 생년월일 8자리(YYYYMMDD) 검증 — 연도 1900~올해, 월 1~12, 일 1~31.
function isValidDob(s: string): boolean {
  if (!/^\d{8}$/.test(s)) return false;
  const y = Number(s.slice(0, 4));
  const m = Number(s.slice(4, 6));
  const d = Number(s.slice(6, 8));
  if (y < 1900 || y > new Date().getFullYear()) return false;
  if (m < 1 || m > 12) return false;
  if (d < 1 || d > 31) return false;
  return true;
}
